"""
CLI 入口 —— 提供命令行接口，支持单文件、目录和交互式三种使用模式。
"""
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.tree import Tree

from .agent import LegacyTestAgent
from .analyzer.ast_analyzer import ASTAnalyzer
from .analyzer.path_enumerator import PathEnumerator

console = Console()


@click.group()
@click.version_option(version="1.0.0", prog_name="legacy-test-agent")
def cli():
    """遗留系统自动化单元测试补全 Agent

    基于 AST 分析与 LLM 推理，自动为遗留代码生成高覆盖率的单元测试。
    """
    pass


@cli.command()
@click.argument("target", type=click.Path(exists=True))
@click.option(
    "-o",
    "--output",
    default="tests/generated",
    help="测试文件输出目录",
    type=click.Path(),
)
@click.option(
    "-c",
    "--config",
    default=None,
    help="配置文件路径",
    type=click.Path(exists=True),
)
@click.option(
    "--max-retries",
    default=5,
    help="最大修正重试次数",
    type=int,
)
@click.option(
    "--coverage-threshold",
    default=80.0,
    help="目标覆盖率阈值",
    type=float,
)
@click.option(
    "--report",
    default=None,
    help="导出 JSON 报告路径",
    type=click.Path(),
)
def generate(target, output, config, max_retries, coverage_threshold, report):
    """为目标文件或目录生成单元测试"""
    console.print(
        Panel.fit(
            "[bold cyan]遗留系统单元测试自动补全 Agent[/bold cyan]\n"
            "[dim]基于 AST 分析与 LLM 推理的智能测试生成[/dim]",
            border_style="cyan",
        )
    )

    try:
        agent = LegacyTestAgent(config_path=config)
    except Exception as e:
        console.print(f"[red]初始化失败: {e}[/red]")
        sys.exit(1)

    agent.config["correction"]["max_retries"] = max_retries
    agent.config["execution"]["coverage_threshold"] = coverage_threshold

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]分析代码并生成测试...", total=None)

        try:
            result = agent.run(target, output_dir=output)
        except ValueError as e:
            progress.stop()
            console.print(f"[yellow]{e}[/yellow]")
            return
        except Exception as e:
            progress.stop()
            console.print(f"[red]运行失败: {e}[/red]")
            sys.exit(1)

        progress.update(task, completed=True)

    _display_report(result)

    if report:
        agent.export_report(result, report)
        console.print(f"\n[green]报告已导出到: {report}[/green]")


@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
def analyze(file_path):
    """分析目标文件的代码结构与执行路径"""
    console.print(
        Panel.fit(
            f"[bold cyan]代码分析: {file_path}[/bold cyan]",
            border_style="cyan",
        )
    )

    analyzer = ASTAnalyzer()
    functions = analyzer.analyze_file(file_path)

    if not functions:
        console.print("[yellow]未找到任何函数[/yellow]")
        return

    enumerator = PathEnumerator()

    for func in functions:
        tree = Tree(f"[bold green]{func.name}[/bold green]")
        tree.add(f"文件: {func.file_path}")
        tree.add(f"行数: {func.line_start}-{func.line_end}")
        tree.add(f"参数: {', '.join(func.args) if func.args else '无'}")
        tree.add(f"圈复杂度: {func.complexity}")
        tree.add(f"依赖: {', '.join(func.dependencies) if func.dependencies else '无'}")

        if func.docstring:
            tree.add(f"文档: {func.docstring[:80]}...")

        paths = enumerator.enumerate_paths(func.source_code)
        paths_node = tree.add(f"[yellow]执行路径 ({len(paths)} 条)[/yellow]")

        for p in paths[:10]:
            icon = "❌" if p.is_error_path else "✅"
            paths_node.add(f"{icon} [{p.path_id}] {p.description}")

        if len(paths) > 10:
            paths_node.add(f"... 还有 {len(paths) - 10} 条路径")

        console.print(tree)
        console.print("")


@cli.command()
@click.argument("source_code", type=str)
def test_one(source_code):
    """对一段代码片段快速生成测试"""
    console.print(
        Panel.fit(
            "[bold cyan]快速测试生成[/bold cyan]",
            border_style="cyan",
        )
    )

    agent = LegacyTestAgent()
    try:
        report = agent.run_on_function(source_code, "target_function")
    except Exception as e:
        console.print(f"[red]生成失败: {e}[/red]")
        sys.exit(1)

    console.print("\n[bold]生成的测试代码:[/bold]")
    console.print(
        Panel(report.test_code, title="测试代码", border_style="green")
    )

    if report.final_success:
        console.print("[green]✅ 测试通过[/green]")
    else:
        console.print(f"[red]❌ 测试失败 (修正 {report.correction_cycles} 次后)[/red]")

    console.print(f"覆盖率: {report.coverage_percent:.1f}%")


@cli.command()
@click.argument("test_file", type=click.Path(exists=True))
@click.option(
    "-s",
    "--source",
    default=None,
    help="关联的源文件（用于覆盖率统计）",
    type=click.Path(exists=True),
)
def verify(test_file, source):
    """验证生成的测试文件"""
    from .executor.test_runner import TestRunner
    from .executor.coverage_collector import CoverageCollector

    console.print(
        Panel.fit(
            f"[bold cyan]验证测试: {test_file}[/bold cyan]",
            border_style="cyan",
        )
    )

    runner = TestRunner()
    result = runner.run_test_file(test_file)

    table = Table(title="测试结果")
    table.add_column("指标", style="cyan")
    table.add_column("值", style="green")

    table.add_row("总计", str(result.total))
    table.add_row("通过", str(result.passed))
    table.add_row("失败", str(result.failed))
    table.add_row("错误", str(result.errors))
    table.add_row("耗时", f"{result.duration_seconds:.2f}s")

    console.print(table)

    if result.failure_details:
        console.print("\n[bold red]失败详情:[/bold red]")
        for failure in result.failure_details[:5]:
            console.print(
                Panel(
                    failure.get("error_message", "")[:500],
                    title=failure.get("test_name", "unknown"),
                    border_style="red",
                )
            )

    if source:
        collector = CoverageCollector()
        cov = collector.collect(source, test_file)
        console.print(f"\n覆盖率: [bold]{cov.coverage_percent:.1f}%[/bold]")
        if cov.missed_lines:
            console.print(f"未覆盖行: {cov.missed_lines}")


def _display_report(result):
    table = Table(title="生成报告", show_header=True, header_style="bold cyan")
    table.add_column("指标", style="cyan")
    table.add_column("值", style="green")

    table.add_row("总函数数", str(result.total_functions))
    table.add_row("成功生成", str(result.success_count))
    table.add_row("生成失败", str(result.failure_count))
    table.add_row("总路径数", str(result.total_paths))
    table.add_row("总测试用例数", str(result.total_test_cases))
    table.add_row("平均覆盖率", f"{result.average_coverage:.1f}%")
    table.add_row("总耗时", f"{result.duration_seconds:.2f}s")

    console.print(table)

    if result.function_reports:
        detail_table = Table(title="函数详情", show_header=True)
        detail_table.add_column("函数名")
        detail_table.add_column("路径数")
        detail_table.add_column("用例数")
        detail_table.add_column("修正次数")
        detail_table.add_column("覆盖率")
        detail_table.add_column("状态")

        for r in result.function_reports:
            status = "[green]✅[/green]" if r.final_success else "[red]❌[/red]"
            detail_table.add_row(
                r.function_name,
                str(r.paths_found),
                str(r.test_cases_generated),
                str(r.correction_cycles),
                f"{r.coverage_percent:.1f}%",
                status,
            )

        console.print(detail_table)


if __name__ == "__main__":
    cli()
