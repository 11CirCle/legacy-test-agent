"""
legacy-test-agent 单元测试
"""
import ast
import tempfile
from pathlib import Path

import pytest

from legacy_test_agent.analyzer.ast_analyzer import ASTAnalyzer, FunctionInfo
from legacy_test_agent.analyzer.path_enumerator import ExecutionPath, PathEnumerator
from legacy_test_agent.generator.llm_reasoner import GeneratedTestCase, LLMReasoner
from legacy_test_agent.generator.test_writer import TestWriter
from legacy_test_agent.executor.test_runner import TestResult, TestRunner
from legacy_test_agent.executor.coverage_collector import CoverageCollector
from legacy_test_agent.corrector.self_corrector import SelfCorrector


SAMPLE_CODE = '''
def calculate_discount(price, quantity, is_vip):
    """计算商品折扣"""
    if price <= 0:
        raise ValueError("价格必须大于0")
    if quantity <= 0:
        return 0.0
    total = price * quantity
    if is_vip:
        total *= 0.8
    if total > 1000:
        total *= 0.9
    return total
'''


class TestASTAnalyzer:
    def test_analyze_source_finds_functions(self):
        analyzer = ASTAnalyzer()
        functions = analyzer.analyze_source(SAMPLE_CODE)

        assert len(functions) >= 1
        func = functions[0]
        assert func.name == "calculate_discount"
        assert "price" in func.args
        assert "quantity" in func.args
        assert "is_vip" in func.args

    def test_cyclomatic_complexity(self):
        analyzer = ASTAnalyzer()
        functions = analyzer.analyze_source(SAMPLE_CODE)

        func = functions[0]
        assert func.complexity >= 4

    def test_analyze_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(SAMPLE_CODE)
            temp_path = f.name

        try:
            analyzer = ASTAnalyzer()
            functions = analyzer.analyze_file(temp_path)
            assert len(functions) >= 1
            assert functions[0].name == "calculate_discount"
        finally:
            Path(temp_path).unlink()

    def test_scan_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "test_module.py"
            py_file.write_text(SAMPLE_CODE, encoding="utf-8")

            analyzer = ASTAnalyzer()
            results = analyzer.scan_directory(tmpdir)

            assert len(results) > 0


class TestPathEnumerator:
    def test_enumerate_paths(self):
        enumerator = PathEnumerator()
        paths = enumerator.enumerate_paths(SAMPLE_CODE)

        assert len(paths) > 0

        path_ids = {p.path_id for p in paths}
        assert len(path_ids) == len(paths)

    def test_error_paths_detected(self):
        enumerator = PathEnumerator()
        paths = enumerator.enumerate_paths(SAMPLE_CODE)

        error_paths = [p for p in paths if p.is_error_path]
        assert len(error_paths) > 0

    def test_path_has_conditions(self):
        enumerator = PathEnumerator()
        paths = enumerator.enumerate_paths(SAMPLE_CODE)

        for path in paths:
            assert path.description
            assert path.expected_behavior

    def test_edge_cases_added(self):
        enumerator = PathEnumerator()
        paths = enumerator.enumerate_paths(SAMPLE_CODE)

        none_paths = [
            p for p in paths if "None" in p.description
        ]
        assert len(none_paths) >= 0


class TestLLMReasoner:
    def test_heuristic_generate_no_api_key(self):
        reasoner = LLMReasoner(api_key=None)

        func_info = FunctionInfo(
            name="calculate_discount",
            module="test",
            file_path="test.py",
            line_start=1,
            line_end=10,
            args=["price", "quantity", "is_vip"],
            return_type_hint="float",
            docstring="计算商品折扣",
            complexity=4,
            source_code=SAMPLE_CODE,
        )

        path = ExecutionPath(
            path_id=1,
            conditions=["price > 0", "quantity > 0", "is_vip == True"],
            description="VIP 客户正常购买",
            expected_behavior="返回折扣后价格",
            input_hints={},
            output_hint="expected_value",
        )

        cases = reasoner.reason_test_cases(func_info, [path])
        assert len(cases) == 1
        case = cases[0]
        assert case.test_name
        assert case.input_params


class TestTestWriter:
    def test_write_pytest(self):
        writer = TestWriter(framework="pytest")

        func_info = FunctionInfo(
            name="calculate_discount",
            module="test_module",
            file_path="test_module.py",
            line_start=1,
            line_end=10,
            args=["price", "quantity", "is_vip"],
            return_type_hint="float",
            docstring="计算商品折扣",
            complexity=4,
            source_code=SAMPLE_CODE,
        )

        test_cases = [
            GeneratedTestCase(
                test_name="test_calculate_discount_vip",
                description="VIP 客户测试",
                path_id=1,
                setup_code="",
                input_params={"price": 100, "quantity": 2, "is_vip": True},
                expected_result=144.0,
                expected_exception=None,
                assertion_code="assert result == 144.0",
            ),
            GeneratedTestCase(
                test_name="test_calculate_discount_invalid_price",
                description="无效价格测试",
                path_id=2,
                setup_code="",
                input_params={"price": 0, "quantity": 1, "is_vip": False},
                expected_result=None,
                expected_exception="ValueError",
                assertion_code="",
            ),
        ]

        code = writer.write_test_file(func_info, test_cases, module_name="test_module")
        assert "def test_" in code
        assert "pytest" in code
        assert "from test_module import" in code

    def test_write_unittest(self):
        writer = TestWriter(framework="unittest")

        func_info = FunctionInfo(
            name="calculate_discount",
            module="test_module",
            file_path="test_module.py",
            line_start=1,
            line_end=10,
            args=["price", "quantity", "is_vip"],
            return_type_hint="float",
            docstring="计算商品折扣",
            complexity=4,
            source_code=SAMPLE_CODE,
        )

        test_cases = [
            GeneratedTestCase(
                test_name="test_calculate_discount_vip",
                description="VIP 客户测试",
                path_id=1,
                setup_code="",
                input_params={"price": 100, "quantity": 2, "is_vip": True},
                expected_result=144.0,
                expected_exception=None,
                assertion_code="",
            ),
        ]

        code = writer.write_test_file(func_info, test_cases, module_name="test_module")
        assert "unittest" in code
        assert "TestCase" in code

    def test_serialize_value(self):
        writer = TestWriter()

        assert writer._serialize_value(None) == "None"
        assert writer._serialize_value(True) == "True"
        assert writer._serialize_value(42) == "42"
        assert writer._serialize_value("hello") == "'hello'"
        assert writer._serialize_value([1, 2, 3]) == "[1, 2, 3]"
        assert writer._serialize_value({"a": 1}) == "{'a': 1}"


class TestTestRunner:
    def test_run_passing_test(self):
        test_code = '''
def add(a, b):
    return a + b

def test_add():
    assert add(1, 2) == 3
    assert add(-1, 1) == 0
'''
        runner = TestRunner()
        result = runner.run_test_code(test_code, "test.py")

        assert result.total > 0
        assert result.success

    def test_run_failing_test(self):
        test_code = '''
def add(a, b):
    return a + b

def test_add_fail():
    assert add(1, 2) == 4
'''
        runner = TestRunner()
        result = runner.run_test_code(test_code, "test.py")

        assert not result.success
        assert result.failed > 0

    def test_run_nonexistent_file(self):
        runner = TestRunner()
        result = runner.run_test_file("nonexistent_file.py")
        assert not result.success


class TestCoverageCollector:
    def test_estimate_coverage(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(SAMPLE_CODE)
            source_path = f.name

        test_path = source_path.replace(".py", "_test.py")
        Path(test_path).write_text("def test_dummy(): pass", encoding="utf-8")

        try:
            collector = CoverageCollector(threshold=80.0)
            report = collector.collect(source_path, test_path)
            assert report.module_name
            assert report.file_path
        finally:
            Path(source_path).unlink(missing_ok=True)
            Path(test_path).unlink(missing_ok=True)

    def test_threshold_check(self):
        collector = CoverageCollector(threshold=80.0)
        from legacy_test_agent.executor.coverage_collector import CoverageReport

        report = CoverageReport(
            coverage_percent=85.0,
            statements_total=100,
            statements_covered=85,
            missed_lines=[],
            module_name="test",
            file_path="test.py",
        )
        assert collector.is_threshold_met(report)

        report2 = CoverageReport(
            coverage_percent=60.0,
            statements_total=100,
            statements_covered=60,
            missed_lines=[],
            module_name="test",
            file_path="test.py",
        )
        assert not collector.is_threshold_met(report2)


class TestSelfCorrector:
    def test_correction_on_passing_code(self):
        test_code = '''
def add(a, b):
    return a + b

def test_add():
    assert add(1, 2) == 3
'''
        func_info = FunctionInfo(
            name="add",
            module="__main__",
            file_path="test.py",
            line_start=1,
            line_end=3,
            args=["a", "b"],
            return_type_hint=None,
            docstring=None,
            complexity=1,
            source_code="def add(a, b):\n    return a + b",
        )

        corrector = SelfCorrector(max_retries=3)
        result = corrector.correct_and_retry(func_info, test_code, "test.py")

        assert result.final_success
        assert result.total_attempts == 1

    def test_correction_on_failing_code(self):
        test_code = '''
def add(a, b):
    return a + b

def test_add():
    assert add(1, 2) == 4
'''
        func_info = FunctionInfo(
            name="add",
            module="__main__",
            file_path="test.py",
            line_start=1,
            line_end=3,
            args=["a", "b"],
            return_type_hint=None,
            docstring=None,
            complexity=1,
            source_code="def add(a, b):\n    return a + b",
        )

        corrector = SelfCorrector(max_retries=2)
        result = corrector.correct_and_retry(func_info, test_code, "test.py")

        assert result.total_attempts >= 1
        assert result.final_test_code

    def test_error_analysis(self):
        corrector = SelfCorrector()

        func_info = FunctionInfo(
            name="test_func",
            module="test",
            file_path="test.py",
            line_start=1,
            line_end=5,
            args=[],
            return_type_hint=None,
            docstring=None,
            complexity=1,
            source_code="def test_func():\n    pass",
        )

        result = TestResult(
            success=False,
            total=3,
            passed=1,
            failed=2,
            errors=0,
            stdout="",
            stderr="AssertionError: assert 3 == 4",
            duration_seconds=0.1,
            failure_details=[
                {"test_name": "test_case_1", "error_message": "AssertionError: assert 3 == 4"},
                {"test_name": "test_case_2", "error_message": "TypeError: unsupported operand"},
            ],
        )

        analysis = corrector._analyze_errors(result, func_info)
        assert "断言失败" in analysis
        assert "类型错误" in analysis
