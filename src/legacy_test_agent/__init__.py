"""
遗留系统自动化单元测试补全 Agent

一个基于 AST 分析与 LLM 推理的智能测试生成工具，
能够自动为遗留代码生成高覆盖率的单元测试。
"""

__version__ = "1.0.0"
__all__ = [
    "ASTAnalyzer",
    "PathEnumerator",
    "ExecutionPath",
    "LLMReasoner",
    "TestWriter",
    "TestRunner",
    "CoverageCollector",
    "SelfCorrector",
    "LegacyTestAgent",
]
