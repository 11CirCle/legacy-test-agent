"""
测试执行器 —— 运行生成的测试代码，收集执行结果与错误日志。
"""
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TestResult:
    success: bool
    total: int
    passed: int
    failed: int
    errors: int
    stdout: str
    stderr: str
    duration_seconds: float
    failure_details: list[dict] = field(default_factory=list)
    coverage_percent: float = 0.0


class TestRunner:
    def __init__(
        self,
        timeout_seconds: int = 60,
        working_dir: str | None = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.working_dir = working_dir

    def run_test_file(self, test_file_path: str) -> TestResult:
        path = Path(test_file_path)
        if not path.exists():
            return TestResult(
                success=False,
                total=0,
                passed=0,
                failed=1,
                errors=0,
                stdout="",
                stderr=f"测试文件不存在: {test_file_path}",
                duration_seconds=0,
            )

        start_time = time.time()

        try:
            result = subprocess.run(
                ["pytest", str(path), "-v", "--tb=short", "--no-header"],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=self.working_dir or str(path.parent),
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return TestResult(
                success=False,
                total=0,
                passed=0,
                failed=1,
                errors=0,
                stdout="",
                stderr="测试执行超时",
                duration_seconds=duration,
            )

        duration = time.time() - start_time
        output = result.stdout + result.stderr
        parsed = self._parse_pytest_output(output)

        return TestResult(
            success=result.returncode == 0,
            total=parsed.get("total", 0),
            passed=parsed.get("passed", 0),
            failed=parsed.get("failed", 0),
            errors=parsed.get("errors", 0),
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=duration,
            failure_details=parsed.get("failures", []),
        )

    def run_test_code(self, test_code: str, source_file: str) -> TestResult:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            prefix="test_",
            delete=False,
            encoding="utf-8",
        ) as f:
            test_path = f.name
            f.write(test_code)

        try:
            return self.run_test_file(test_path)
        finally:
            try:
                Path(test_path).unlink()
            except OSError:
                pass

    def _parse_pytest_output(self, output: str) -> dict:
        import re

        result: dict = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "failures": []}

        summary_match = re.search(
            r"(\d+)\s+passed[,.]?\s*(\d+)\s+failed[,.]?\s*(\d+)\s+error",
            output,
        )
        if not summary_match:
            summary_match = re.search(r"(\d+) passed[,.]?\s*(\d+) failed", output)

        if summary_match:
            result["passed"] = int(summary_match.group(1))
            result["failed"] = int(summary_match.group(2))
            if len(summary_match.groups()) >= 3:
                result["errors"] = int(summary_match.group(3))
            result["total"] = result["passed"] + result["failed"] + result["errors"]
        else:
            no_tests = re.search(r"no tests ran", output, re.IGNORECASE)
            if no_tests:
                return result
            single_passed = re.search(r"(\d+) passed", output)
            if single_passed:
                result["passed"] = int(single_passed.group(1))
                result["total"] = result["passed"]
            single_failed = re.search(r"(\d+) failed", output)
            if single_failed:
                result["failed"] = int(single_failed.group(1))
                result["total"] += result["failed"]

        failure_blocks = re.findall(
            r"FAILED.*?\n(.*?)(?=\n\n|\n={3,}|\Z)", output, re.DOTALL
        )
        for block in failure_blocks:
            result["failures"].append(
                {
                    "test_name": self._extract_test_name(block),
                    "error_message": block.strip()[:500],
                }
            )

        return result

    def _extract_test_name(self, block: str) -> str:
        import re

        match = re.search(r"test_\w+", block)
        return match.group(0) if match else "unknown"
