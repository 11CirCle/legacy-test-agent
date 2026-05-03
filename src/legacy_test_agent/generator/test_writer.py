"""
测试代码生成器 —— 将推理出的测试用例输出为符合测试框架格式的测试代码。
"""
from typing import Any

from ..analyzer.ast_analyzer import FunctionInfo
from .llm_reasoner import GeneratedTestCase


class TestWriter:
    def __init__(self, framework: str = "pytest"):
        self.framework = framework.lower()

    def write_test_file(
        self,
        func_info: FunctionInfo,
        test_cases: list[GeneratedTestCase],
        module_name: str | None = None,
    ) -> str:
        if self.framework == "pytest":
            return self._write_pytest(func_info, test_cases, module_name)
        elif self.framework == "unittest":
            return self._write_unittest(func_info, test_cases, module_name)
        else:
            raise ValueError(f"不支持的测试框架: {self.framework}")

    def _write_pytest(
        self,
        func_info: FunctionInfo,
        test_cases: list[GeneratedTestCase],
        module_name: str | None = None,
    ) -> str:
        module = module_name or func_info.module
        lines: list[str] = []

        lines.append('"""')
        lines.append(f"自动生成的测试用例 - {func_info.name}")
        lines.append(f"源模块: {module}")
        lines.append(f"生成路径数: {len(test_cases)}")
        lines.append('"""')
        lines.append("")
        lines.append("import pytest")
        lines.append("")

        import_stmt = f"from {module} import {func_info.name}"
        if func_info.file_path:
            lines.append(f"# 源文件: {func_info.file_path}")
        lines.append(import_stmt)
        lines.append("")

        has_params = any(tc.input_params for tc in test_cases)

        if has_params and len(test_cases) > 1:
            lines.append(self._generate_parametrize_decorator(func_info, test_cases))
            lines.append(f"def test_{func_info.name}(test_input, expected, expect_exception):")
            lines.append(f'    """参数化测试 - {func_info.docstring or func_info.name}"""')
            lines.append("    if expect_exception:")
            lines.append("        with pytest.raises(expect_exception):")
            lines.append(f"            {func_info.name}(**test_input)")
            lines.append("    else:")
            lines.append(f"        result = {func_info.name}(**test_input)")
            lines.append("        assert result == expected")
        else:
            for tc in test_cases:
                lines.append("")
                lines.append(f"def {self._sanitize_test_name(tc.test_name)}():")
                lines.append(f'    """{tc.description}"""')
                for key, val in tc.input_params.items():
                    lines.append(f"    {key} = {self._serialize_value(val)}")
                args_str = ", ".join(f"{k}={k}" for k in tc.input_params)

                if tc.expected_exception:
                    lines.append(f"    with pytest.raises({tc.expected_exception}):")
                    lines.append(f"        {func_info.name}({args_str})")
                elif tc.assertion_code:
                    lines.append(f"    result = {func_info.name}({args_str})")
                    for assertion_line in tc.assertion_code.strip().split("\n"):
                        if assertion_line.strip():
                            lines.append(f"    {assertion_line.strip()}")
                else:
                    lines.append(f"    result = {func_info.name}({args_str})")
                    lines.append(
                        f"    assert result == {self._serialize_value(tc.expected_result)}"
                    )

        return "\n".join(lines) + "\n"

    def _generate_parametrize_decorator(
        self,
        func_info: FunctionInfo,
        test_cases: list[GeneratedTestCase],
    ) -> str:
        lines: list[str] = []
        lines.append("@pytest.mark.parametrize(")
        lines.append('    "test_input, expected, expect_exception",')
        lines.append("    [")

        for i, tc in enumerate(test_cases):
            input_dict = self._serialize_value(tc.input_params)
            expected = self._serialize_value(tc.expected_result)
            exception = f"{tc.expected_exception}" if tc.expected_exception else "None"
            comma = "," if i < len(test_cases) - 1 else ","
            lines.append(f"        ({input_dict}, {expected}, {exception}){comma}")

        lines.append("    ]")
        lines.append(")")
        return "\n".join(lines)

    def _write_unittest(
        self,
        func_info: FunctionInfo,
        test_cases: list[GeneratedTestCase],
        module_name: str | None = None,
    ) -> str:
        module = module_name or func_info.module
        lines: list[str] = []
        lines.append('"""')
        lines.append(f"自动生成的测试用例 - {func_info.name}")
        lines.append('"""')
        lines.append("import unittest")
        lines.append(f"from {module} import {func_info.name}")
        lines.append("")
        lines.append(f"class Test{func_info.name.capitalize()}(unittest.TestCase):")

        for tc in test_cases:
            lines.append("")
            lines.append(f"    def {self._sanitize_test_name(tc.test_name)}(self):")
            lines.append(f'        """{tc.description}"""')
            for key, val in tc.input_params.items():
                lines.append(f"        {key} = {self._serialize_value(val)}")
            args_str = ", ".join(f"{k}={k}" for k in tc.input_params)

            if tc.expected_exception:
                lines.append(
                    f"        with self.assertRaises({tc.expected_exception}):"
                )
                lines.append(f"            {func_info.name}({args_str})")
            else:
                lines.append(f"        result = {func_info.name}({args_str})")
                lines.append(
                    f"        self.assertEqual(result, {self._serialize_value(tc.expected_result)})"
                )

        lines.append("")
        lines.append("if __name__ == '__main__':")
        lines.append("    unittest.main()")
        return "\n".join(lines) + "\n"

    def _sanitize_test_name(self, name: str) -> str:
        sanitized = name.replace("-", "_").replace(" ", "_")
        sanitized = "".join(c for c in sanitized if c.isalnum() or c == "_")
        if sanitized and sanitized[0].isdigit():
            sanitized = "t_" + sanitized
        return sanitized or "test_case"

    def _serialize_value(self, value: Any) -> str:
        if value is None:
            return "None"
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, str):
            return repr(value)
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            items = ", ".join(self._serialize_value(v) for v in value)
            return f"[{items}]"
        if isinstance(value, dict):
            items = ", ".join(
                f"{self._serialize_value(k)}: {self._serialize_value(v)}"
                for k, v in value.items()
            )
            return f"{{{items}}}"
        if isinstance(value, tuple):
            items = ", ".join(self._serialize_value(v) for v in value)
            return f"({items})"
        return str(value)
