"""
遗留系统单元测试自动补全 Agent —— 主调度器

协调 AST 分析、路径枚举、LLM 推理、测试生成、执行和自我修正的完整流程。
"""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .analyzer.ast_analyzer import ASTAnalyzer, FunctionInfo
from .analyzer.path_enumerator import PathEnumerator
from .corrector.self_corrector import SelfCorrector
from .executor.coverage_collector import CoverageCollector
from .executor.test_runner import TestRunner
from .generator.llm_reasoner import LLMReasoner
from .generator.test_writer import TestWriter


@dataclass
class FunctionTestReport:
    function_name: str
    source_file: str
    paths_found: int
    test_cases_generated: int
    test_code: str
    test_file_path: str
    correction_cycles: int
    final_success: bool
    coverage_percent: float
    errors: list[str] = field(default_factory=list)


@dataclass
class AgentReport:
    total_functions: int
    success_count: int
    failure_count: int
    total_paths: int
    total_test_cases: int
    average_coverage: float
    duration_seconds: float
    function_reports: list[FunctionTestReport] = field(default_factory=list)


class LegacyTestAgent:
    def __init__(self, config_path: str | None = None):
        self.config = self._load_config(config_path)
        self._init_components()

    def _load_config(self, config_path: str | None) -> dict:
        defaults = {
            "llm": {
                "provider": "openai",
                "model": "gpt-4o",
                "api_key_env": "OPENAI_API_KEY",
                "temperature": 0.1,
                "max_tokens": 4096,
            },
            "analysis": {
                "max_path_depth": 20,
                "target_language": "python",
                "ignore_patterns": ["**/test_*.py", "**/tests/**", "**/__pycache__/**"],
            },
            "generation": {
                "test_framework": "pytest",
                "max_test_cases_per_function": 50,
                "include_edge_cases": True,
            },
            "correction": {
                "max_retries": 5,
                "retry_delay_seconds": 1,
                "fail_fast": False,
            },
            "execution": {
                "timeout_seconds": 60,
                "coverage_threshold": 80,
                "working_dir": ".test_workspace",
            },
        }

        if config_path and Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            self._deep_merge(defaults, user_config)

        return defaults

    def _deep_merge(self, base: dict, override: dict) -> None:
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _init_components(self) -> None:
        llm_cfg = self.config["llm"]
        analysis_cfg = self.config["analysis"]
        generation_cfg = self.config["generation"]
        correction_cfg = self.config["correction"]
        execution_cfg = self.config["execution"]

        self.analyzer = ASTAnalyzer(target_language=analysis_cfg["target_language"])
        self.path_enumerator = PathEnumerator(max_depth=analysis_cfg["max_path_depth"])
        self.llm_reasoner = LLMReasoner(
            model=llm_cfg["model"],
            api_key_env=llm_cfg["api_key_env"],
            temperature=llm_cfg["temperature"],
            max_tokens=llm_cfg["max_tokens"],
        )
        self.test_writer = TestWriter(framework=generation_cfg["test_framework"])
        self.test_runner = TestRunner(timeout_seconds=execution_cfg["timeout_seconds"])
        self.coverage_collector = CoverageCollector(
            threshold=execution_cfg["coverage_threshold"]
        )
        self.corrector = SelfCorrector(
            max_retries=correction_cfg["max_retries"],
            retry_delay=correction_cfg["retry_delay_seconds"],
            fail_fast=correction_cfg["fail_fast"],
            llm_reasoner=self.llm_reasoner,
        )

    def analyze_file(self, file_path: str) -> list[FunctionInfo]:
        return self.analyzer.analyze_file(file_path)

    def analyze_directory(self, directory: str) -> dict[str, list[FunctionInfo]]:
        ignore = self.config["analysis"].get("ignore_patterns", [])
        return self.analyzer.scan_directory(directory, ignore)

    def generate_tests_for_function(
        self,
        func_info: FunctionInfo,
        output_dir: str | None = None,
    ) -> FunctionTestReport:
        errors: list[str] = []

        paths = self.path_enumerator.enumerate_paths(func_info.source_code)

        test_cases = self.llm_reasoner.reason_test_cases(func_info, paths)

        max_cases = self.config["generation"]["max_test_cases_per_function"]
        if len(test_cases) > max_cases:
            test_cases = test_cases[:max_cases]

        test_code = self.test_writer.write_test_file(func_info, test_cases)

        correction_result = self.corrector.correct_and_retry(
            func_info,
            test_code,
            func_info.file_path,
        )

        test_file_path = ""
        if output_dir:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            test_file_path = str(out / f"test_{func_info.name}.py")
            Path(test_file_path).write_text(
                correction_result.final_test_code, encoding="utf-8"
            )

        return FunctionTestReport(
            function_name=func_info.name,
            source_file=func_info.file_path,
            paths_found=len(paths),
            test_cases_generated=len(test_cases),
            test_code=correction_result.final_test_code,
            test_file_path=test_file_path,
            correction_cycles=correction_result.total_attempts,
            final_success=correction_result.final_success,
            coverage_percent=correction_result.coverage_percent,
            errors=errors,
        )

    def run(
        self,
        target: str,
        output_dir: str = "tests/generated",
    ) -> AgentReport:
        start_time = time.time()
        target_path = Path(target)
        all_functions: list[FunctionInfo] = []

        if target_path.is_file():
            all_functions = self.analyzer.analyze_file(str(target_path))
        elif target_path.is_dir():
            results = self.analyze_directory(str(target_path))
            for funcs in results.values():
                all_functions.extend(funcs)
        else:
            raise ValueError(f"目标路径不存在: {target}")

        if not all_functions:
            raise ValueError(f"未在 {target} 中找到任何可分析的函数")

        reports: list[FunctionTestReport] = []
        success_count = 0
        failure_count = 0
        total_paths = 0
        total_cases = 0

        for func in all_functions:
            report = self.generate_tests_for_function(func, output_dir)
            reports.append(report)

            total_paths += report.paths_found
            total_cases += report.test_cases_generated

            if report.final_success:
                success_count += 1
            else:
                failure_count += 1

        duration = time.time() - start_time
        avg_coverage = (
            sum(r.coverage_percent for r in reports) / len(reports)
            if reports
            else 0.0
        )

        return AgentReport(
            total_functions=len(all_functions),
            success_count=success_count,
            failure_count=failure_count,
            total_paths=total_paths,
            total_test_cases=total_cases,
            average_coverage=avg_coverage,
            duration_seconds=duration,
            function_reports=reports,
        )

    def run_on_function(self, source_code: str, function_name: str) -> FunctionTestReport:
        func_info = FunctionInfo(
            name=function_name,
            module="__main__",
            file_path="<string>",
            line_start=1,
            line_end=len(source_code.splitlines()),
            args=[],
            return_type_hint=None,
            docstring=None,
            complexity=1,
            dependencies=[],
            source_code=source_code,
        )

        return self.generate_tests_for_function(func_info)

    def export_report(self, report: AgentReport, output_path: str) -> None:
        data = {
            "summary": {
                "total_functions": report.total_functions,
                "success_count": report.success_count,
                "failure_count": report.failure_count,
                "total_paths": report.total_paths,
                "total_test_cases": report.total_test_cases,
                "average_coverage": report.average_coverage,
                "duration_seconds": report.duration_seconds,
            },
            "details": [
                {
                    "function_name": r.function_name,
                    "source_file": r.source_file,
                    "paths_found": r.paths_found,
                    "test_cases_generated": r.test_cases_generated,
                    "correction_cycles": r.correction_cycles,
                    "final_success": r.final_success,
                    "coverage_percent": r.coverage_percent,
                    "test_file": r.test_file_path,
                    "errors": r.errors,
                }
                for r in report.function_reports
            ],
        }

        Path(output_path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
