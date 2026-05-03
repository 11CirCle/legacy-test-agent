"""
LLM 推理器 —— 针对每条执行路径，利用大语言模型链式推理出输入参数与预期输出。
"""
import json
import os
import re
from dataclasses import dataclass
from typing import Any

from ..analyzer.path_enumerator import ExecutionPath
from ..analyzer.ast_analyzer import FunctionInfo


@dataclass
class GeneratedTestCase:
    test_name: str
    description: str
    path_id: int
    setup_code: str
    input_params: dict[str, Any]
    expected_result: Any
    expected_exception: str | None
    assertion_code: str


class LLMReasoner:
    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ):
        self.model = model
        self.api_key = api_key or os.getenv(api_key_env)
        self.temperature = temperature
        self.max_tokens = max_tokens

    def reason_test_cases(
        self,
        func_info: FunctionInfo,
        paths: list[ExecutionPath],
    ) -> list[GeneratedTestCase]:
        test_cases: list[GeneratedTestCase] = []

        for path in paths:
            tc = self._reason_single_path(func_info, path)
            if tc:
                test_cases.append(tc)

        return test_cases

    def _reason_single_path(
        self,
        func_info: FunctionInfo,
        path: ExecutionPath,
    ) -> GeneratedTestCase | None:
        prompt = self._build_prompt(func_info, path)

        if self.api_key:
            response = self._call_llm(prompt)
            return self._parse_llm_response(response, func_info, path)
        else:
            return self._heuristic_generate(func_info, path)

    def _build_prompt(self, func_info: FunctionInfo, path: ExecutionPath) -> str:
        prompt = f"""你是一个单元测试专家。请为以下 Python 函数生成一个测试用例。

## 函数信息
函数名: {func_info.name}
模块: {func_info.module}
参数: {', '.join(func_info.args)}
复杂度: {func_info.complexity}
文档字符串: {func_info.docstring or '无'}

## 函数源代码
```python
{func_info.source_code}
```

## 执行路径
路径ID: {path.path_id}
条件: {', '.join(path.conditions) if path.conditions else '无特殊条件'}
描述: {path.description}
预期行为: {path.expected_behavior}
是否为错误路径: {path.is_error_path}

## 输入提示
{json.dumps(path.input_hints, ensure_ascii=False) if path.input_hints else '无特殊提示'}

## 输出提示
{path.output_hint}

请以 JSON 格式返回测试用例，格式如下：
```json
{{
    "test_name": "test_{{function_name}}_{{path_id}}_{{scenario}}",
    "description": "测试场景描述",
    "input_params": {{"param1": value1, "param2": value2}},
    "expected_result": null 或 预期返回值,
    "expected_exception": null 或 "ExceptionType",
    "assertion_code": "assert 语句的代码"
}}
```

注意：
1. 如果是错误路径，expected_exception 应填写预期的异常类型
2. input_params 中使用 Python 语法表示值（如 None, True, "string", [1,2,3]）
3. 请确保生成的测试输入是合理且能触发该路径的
"""
        return prompt.strip()

    def _call_llm(self, prompt: str) -> str:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的单元测试生成专家。请严格按照 JSON 格式返回结果。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise RuntimeError(f"LLM 调用失败: {e}")

    def _parse_llm_response(
        self,
        response: str,
        func_info: FunctionInfo,
        path: ExecutionPath,
    ) -> GeneratedTestCase | None:
        try:
            json_match = re.search(r"\{[\s\S]*\}", response)
            if not json_match:
                return None
            data = json.loads(json_match.group(0))

            return GeneratedTestCase(
                test_name=data.get("test_name", f"test_{func_info.name}_{path.path_id}"),
                description=data.get("description", path.description),
                path_id=path.path_id,
                setup_code="",
                input_params=data.get("input_params", {}),
                expected_result=data.get("expected_result"),
                expected_exception=data.get("expected_exception"),
                assertion_code=data.get("assertion_code", ""),
            )
        except (json.JSONDecodeError, KeyError):
            return self._heuristic_generate(func_info, path)

    def _heuristic_generate(
        self,
        func_info: FunctionInfo,
        path: ExecutionPath,
    ) -> GeneratedTestCase:
        params: dict[str, Any] = {}
        for arg in func_info.args:
            params[arg] = self._infer_default_value(arg, path)

        for hint_key, hint_val in path.input_hints.items():
            if hint_key in params:
                params[hint_key] = self._resolve_hint_value(hint_val)

        return GeneratedTestCase(
            test_name=f"test_{func_info.name}_path_{path.path_id}",
            description=path.description,
            path_id=path.path_id,
            setup_code="",
            input_params=params,
            expected_result=None,
            expected_exception="Exception" if path.is_error_path else None,
            assertion_code="",
        )

    def _infer_default_value(self, arg_name: str, path: ExecutionPath) -> Any:
        name_lower = arg_name.lower()
        if any(kw in name_lower for kw in ["list", "items", "data", "values", "arr"]):
            return [1, 2, 3]
        if any(kw in name_lower for kw in ["dict", "map", "config", "kwargs"]):
            return {"key": "value"}
        if any(kw in name_lower for kw in ["str", "text", "name", "path", "file"]):
            return "test_value"
        if any(kw in name_lower for kw in ["int", "num", "count", "size", "len"]):
            return 0
        if any(kw in name_lower for kw in ["bool", "flag", "enable"]):
            return False
        if any(kw in name_lower for kw in ["float", "ratio", "percent"]):
            return 0.0
        if any(kw in name_lower for kw in ["none", "null", "optional"]):
            return None
        return None

    def _resolve_hint_value(self, hint: str) -> Any:
        hint_lower = hint.lower()
        if hint_lower == "none":
            return None
        if hint_lower == "empty":
            return []
        if hint_lower == "non-empty":
            return [1, 2, 3]
        if hint_lower == "true":
            return True
        if hint_lower == "false":
            return False
        return hint
