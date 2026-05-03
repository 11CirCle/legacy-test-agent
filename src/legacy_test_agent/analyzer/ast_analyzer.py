"""
AST 分析器 —— 扫描目标函数，利用抽象语法树分析代码结构、复杂度与依赖关系。
"""
import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FunctionInfo:
    name: str
    module: str
    file_path: str
    line_start: int
    line_end: int
    args: list[str]
    return_type_hint: str | None
    docstring: str | None
    complexity: int
    dependencies: list[str] = field(default_factory=list)
    source_code: str = ""


@dataclass
class BranchNode:
    type: str
    line: int
    condition: str
    true_branch: list["BranchNode"] = field(default_factory=list)
    false_branch: list["BranchNode"] = field(default_factory=list)
    parent: "BranchNode | None" = None


class ASTAnalyzer:
    def __init__(self, target_language: str = "python"):
        self.target_language = target_language

    def analyze_file(self, file_path: str) -> list[FunctionInfo]:
        path = Path(file_path)
        source = path.read_text(encoding="utf-8")
        return self.analyze_source(source, str(path))

    def analyze_source(self, source_code: str, file_path: str = "<string>") -> list[FunctionInfo]:
        tree = ast.parse(source_code)
        module_name = Path(file_path).stem
        functions: list[FunctionInfo] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_info = self._extract_function_info(
                    node, source_code, module_name, file_path
                )
                functions.append(func_info)

        self._resolve_dependencies(functions, tree)
        return functions

    def _extract_function_info(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        source_code: str,
        module_name: str,
        file_path: str,
    ) -> FunctionInfo:
        args = [arg.arg for arg in node.args.args]
        return_type = (
            ast.unparse(node.returns) if hasattr(node, "returns") and node.returns else None
        )
        docstring = ast.get_docstring(node)
        complexity = self._compute_cyclomatic_complexity(node)
        func_source = ast.get_source_segment(source_code, node) or ""

        called_funcs = self._extract_called_functions(node)

        return FunctionInfo(
            name=node.name,
            module=module_name,
            file_path=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            args=args,
            return_type_hint=return_type,
            docstring=docstring,
            complexity=complexity,
            dependencies=called_funcs,
            source_code=func_source,
        )

    def _compute_cyclomatic_complexity(self, node: ast.AST) -> int:
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            elif isinstance(child, (ast.ExceptHandler, ast.With, ast.AsyncWith)):
                complexity += 1
        return complexity

    def _extract_called_functions(self, node: ast.AST) -> list[str]:
        called: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    called.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    called.append(ast.unparse(child.func))
        return list(set(called))

    def _resolve_dependencies(
        self, functions: list[FunctionInfo], tree: ast.AST
    ) -> None:
        all_names = {f.name for f in functions}
        for func in functions:
            func.dependencies = [d for d in func.dependencies if d in all_names]

    def scan_directory(self, directory: str, ignore_patterns: list[str] | None = None) -> dict[str, list[FunctionInfo]]:
        results: dict[str, list[FunctionInfo]] = {}
        base = Path(directory)
        ignore = ignore_patterns or []

        py_files = list(base.rglob("*.py"))
        for py_file in py_files:
            relative = str(py_file)
            if any(Path(relative).match(p) for p in ignore):
                continue
            try:
                funcs = self.analyze_file(str(py_file))
                if funcs:
                    results[str(py_file)] = funcs
            except SyntaxError:
                continue

        return results
