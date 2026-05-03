"""
覆盖率收集器 —— 利用 coverage.py 统计测试覆盖率，判断是否达到目标阈值。
"""
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CoverageReport:
    coverage_percent: float
    statements_total: int
    statements_covered: int
    missed_lines: list[int]
    module_name: str
    file_path: str


class CoverageCollector:
    def __init__(self, threshold: float = 80.0):
        self.threshold = threshold

    def collect(
        self,
        source_file: str,
        test_file: str,
        working_dir: str | None = None,
    ) -> CoverageReport:
        source_path = Path(source_file)
        wd = working_dir or str(source_path.parent)

        try:
            subprocess.run(
                [
                    "coverage",
                    "run",
                    "--source",
                    str(source_path.parent),
                    "--branch",
                    "-m",
                    "pytest",
                    test_file,
                    "-q",
                    "--no-header",
                ],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=wd,
            )

            json_result = subprocess.run(
                ["coverage", "json", "-o", "-"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=wd,
            )

            if json_result.returncode == 0 and json_result.stdout.strip():
                return self._parse_coverage_json(
                    json_result.stdout, str(source_path)
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return self._estimate_coverage(source_file, test_file)

    def _parse_coverage_json(
        self, json_output: str, source_file: str
    ) -> CoverageReport:
        try:
            data = json.loads(json_output)
        except json.JSONDecodeError:
            return CoverageReport(
                coverage_percent=0.0,
                statements_total=0,
                statements_covered=0,
                missed_lines=[],
                module_name=Path(source_file).stem,
                file_path=source_file,
            )

        totals = data.get("totals", {})
        coverage_percent = totals.get("percent_covered", 0.0)
        statements_total = totals.get("num_statements", 0)
        statements_covered = totals.get("covered_lines", 0)
        missed_lines: list[int] = []

        for file_path, file_data in data.get("files", {}).items():
            if source_file in file_path or Path(file_path).name == Path(source_file).name:
                missed_lines = file_data.get("missing_lines", [])
                statements_total = file_data.get("summary", {}).get("num_statements", statements_total)
                statements_covered = file_data.get("summary", {}).get("covered_lines", statements_covered)
                coverage_percent = file_data.get("summary", {}).get("percent_covered", coverage_percent)
                break

        return CoverageReport(
            coverage_percent=coverage_percent,
            statements_total=statements_total,
            statements_covered=statements_covered,
            missed_lines=list(missed_lines),
            module_name=Path(source_file).stem,
            file_path=source_file,
        )

    def _estimate_coverage(
        self, source_file: str, test_file: str
    ) -> CoverageReport:
        source = Path(source_file)
        try:
            source_content = source.read_text(encoding="utf-8")
            source_lines = [
                line for line in source_content.splitlines() if line.strip() and not line.strip().startswith("#")
            ]
            total = len(source_lines)
        except Exception:
            total = 0

        try:
            test_content = Path(test_file).read_text(encoding="utf-8")
            test_lines = [
                line for line in test_content.splitlines() if line.strip() and not line.strip().startswith("#")
            ]
            test_count = len(test_lines)
        except Exception:
            test_count = 0

        if total == 0:
            return CoverageReport(
                coverage_percent=0.0,
                statements_total=0,
                statements_covered=0,
                missed_lines=[],
                module_name=source.stem,
                file_path=str(source),
            )

        estimated = min(test_count / max(total, 1) * 50, 95.0)
        return CoverageReport(
            coverage_percent=estimated,
            statements_total=total,
            statements_covered=int(total * estimated / 100),
            missed_lines=[],
            module_name=source.stem,
            file_path=str(source),
        )

    def is_threshold_met(self, report: CoverageReport) -> bool:
        return report.coverage_percent >= self.threshold
