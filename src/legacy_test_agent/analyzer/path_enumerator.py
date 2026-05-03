"""
执行路径枚举器 —— 基于 AST 分析所有可能的代码执行路径，包括边缘情况。
"""
import ast
from dataclasses import dataclass

_TRY_TYPES = (ast.Try, ast.TryStar) if hasattr(ast, "TryStar") else (ast.Try,)


@dataclass
class ExecutionPath:
    path_id: int
    conditions: list[str]
    description: str
    expected_behavior: str
    input_hints: dict[str, str]
    output_hint: str
    is_error_path: bool = False


@dataclass
class PathContext:
    conditions: list[str]
    negated_conditions: list[str]


class PathEnumerator:
    def __init__(self, max_depth: int = 20):
        self.max_depth = max_depth
        self._path_counter: int = 0

    def enumerate_paths(self, func_source: str) -> list[ExecutionPath]:
        self._path_counter = 0
        try:
            tree = ast.parse(func_source)
        except SyntaxError:
            return []

        func_node = self._find_function_node(tree)
        if func_node is None:
            return []

        paths: list[ExecutionPath] = []
        self._traverse(func_node, PathContext([], []), paths, depth=0)

        self._add_edge_cases(func_node, paths)
        return paths

    def _find_function_node(self, tree: ast.AST) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node
        return None

    def _traverse(
        self,
        node: ast.AST,
        context: PathContext,
        paths: list[ExecutionPath],
        depth: int,
    ) -> None:
        if depth > self.max_depth:
            return
        if self._path_counter > 200:
            return

        if isinstance(node, ast.If):
            condition_text = ast.unparse(node.test) if hasattr(ast, "unparse") else "unknown"

            true_ctx = PathContext(
                conditions=context.conditions + [condition_text],
                negated_conditions=context.negated_conditions.copy(),
            )
            false_ctx = PathContext(
                conditions=context.conditions.copy(),
                negated_conditions=context.negated_conditions + [condition_text],
            )

            for stmt in node.body:
                self._traverse(stmt, true_ctx, paths, depth + 1)
            for stmt in node.orelse:
                self._traverse(stmt, false_ctx, paths, depth + 1)

            if not node.body or self._is_terminal(node.body):
                self._emit_path(true_ctx, paths)
            if not node.orelse or self._is_terminal(node.orelse):
                self._emit_path(false_ctx, paths)

        elif isinstance(node, _TRY_TYPES):
            for stmt in node.body:
                self._traverse(stmt, context, paths, depth + 1)

            for handler in node.handlers:
                exc_type = ast.unparse(handler.type) if handler.type else "Exception"
                error_ctx = PathContext(
                    conditions=context.conditions + [f"raises {exc_type}"],
                    negated_conditions=context.negated_conditions.copy(),
                )
                self._emit_path(error_ctx, paths, is_error=True)

        elif isinstance(node, ast.For):
            empty_ctx = PathContext(
                conditions=context.conditions + ["empty_iterable"],
                negated_conditions=context.negated_conditions.copy(),
            )
            self._emit_path(empty_ctx, paths)

            non_empty_ctx = PathContext(
                conditions=context.conditions + ["non_empty_iterable"],
                negated_conditions=context.negated_conditions.copy(),
            )
            for stmt in node.body:
                self._traverse(stmt, non_empty_ctx, paths, depth + 1)

        elif isinstance(node, ast.While):
            true_ctx = PathContext(
                conditions=context.conditions + ["while_condition_true"],
                negated_conditions=context.negated_conditions.copy(),
            )
            false_ctx = PathContext(
                conditions=context.conditions + ["while_condition_false"],
                negated_conditions=context.negated_conditions.copy(),
            )
            for stmt in node.body:
                self._traverse(stmt, true_ctx, paths, depth + 1)
            self._emit_path(false_ctx, paths)

        elif isinstance(node, ast.Raise):
            self._emit_path(context, paths, is_error=True)

        elif isinstance(node, ast.Return):
            self._emit_path(context, paths)

        elif hasattr(node, "body"):
            for child in node.body:
                self._traverse(child, context, paths, depth)

    def _is_terminal(self, stmts: list[ast.stmt]) -> bool:
        if not stmts:
            return True
        last = stmts[-1]
        return isinstance(last, (ast.Return, ast.Raise))

    def _emit_path(
        self,
        context: PathContext,
        paths: list[ExecutionPath],
        is_error: bool = False,
    ) -> None:
        self._path_counter += 1
        all_conditions = context.conditions + [
            f"NOT ({c})" for c in context.negated_conditions
        ]

        description = self._build_description(all_conditions)
        expected = self._infer_expected_behavior(all_conditions, is_error)

        paths.append(
            ExecutionPath(
                path_id=self._path_counter,
                conditions=all_conditions,
                description=description,
                expected_behavior=expected,
                input_hints=self._derive_input_hints(all_conditions),
                output_hint=self._derive_output_hint(all_conditions),
                is_error_path=is_error,
            )
        )

    def _build_description(self, conditions: list[str]) -> str:
        if not conditions:
            return "默认路径，无特殊条件"
        return "当 " + " 且 ".join(conditions) + " 时"

    def _infer_expected_behavior(self, conditions: list[str], is_error: bool) -> str:
        if is_error:
            return "函数应抛出异常"
        if not conditions:
            return "正常返回预期结果"
        return "在满足条件时返回对应结果"

    def _derive_input_hints(self, conditions: list[str]) -> dict[str, str]:
        hints: dict[str, str] = {}
        for cond in conditions:
            cond_clean = cond.replace("NOT (", "").replace(")", "")
            if "raises" in cond_clean:
                continue
            if "empty" in cond_clean.lower():
                hints["_iterable"] = "empty"
            elif "non_empty" in cond_clean.lower():
                hints["_iterable"] = "non-empty"
        return hints

    def _derive_output_hint(self, conditions: list[str]) -> str:
        if any("raises" in c for c in conditions):
            return "exception"
        if any("empty" in c.lower() for c in conditions):
            return "empty_result_or_default"
        return "expected_value"

    def _add_edge_cases(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef, paths: list[ExecutionPath]) -> None:
        args = func_node.args
        arg_names = [arg.arg for arg in args.args]

        if arg_names:
            has_defaults = args.defaults
            num_no_default = len(arg_names) - len(has_defaults) if has_defaults else len(arg_names)

            for i, name in enumerate(arg_names):
                if i < num_no_default:
                    paths.append(
                        ExecutionPath(
                            path_id=self._path_counter + 1,
                            conditions=[],
                            description=f"边缘情况：参数 {name} 为 None",
                            expected_behavior="根据实现可能抛出异常或处理 None",
                            input_hints={name: "None"},
                            output_hint="exception_or_default",
                            is_error_path=True,
                        )
                    )
                    self._path_counter += 1

        if args.vararg:
            paths.append(
                ExecutionPath(
                    path_id=self._path_counter + 1,
                    conditions=[],
                    description="边缘情况：无额外可变参数传入",
                    expected_behavior="函数正常处理",
                    input_hints={"*args": "empty"},
                    output_hint="expected_value",
                )
            )
            self._path_counter += 1

        if args.kwarg:
            paths.append(
                ExecutionPath(
                    path_id=self._path_counter + 1,
                    conditions=[],
                    description="边缘情况：无额外关键字参数传入",
                    expected_behavior="函数正常处理",
                    input_hints={"**kwargs": "empty"},
                    output_hint="expected_value",
                )
            )
            self._path_counter += 1
