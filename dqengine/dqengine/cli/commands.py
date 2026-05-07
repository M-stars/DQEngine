"""DQEngine CLI — 第二阶段增强版."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table as RichTable

from dqengine import __version__
from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.repair.missing_value import MissingValueCleaner
from dqengine.repair.duplicate import DuplicateCleaner
from dqengine.repair.date_standardizer import DateStandardizer
from dqengine.repair.outlier import OutlierDetector
from dqengine.rules.validator import RuleValidator
from dqengine.report.generator import ReportGenerator
# 第二阶段模块 — 延迟导入以支持可选依赖
from dqengine.models.schemas import (
    SemanticType,
    DoctorResult,
    PluginType,
    AppConfig,
    ReportFormat,
)
from dqengine.utils.console import (
    console,
    create_table,
    print_success,
    print_error,
    print_warning,
    print_info,
    render_score_gauge,
)

app = typer.Typer(
    name="dq",
    help="DQEngine — 轻量级数据质量治理框架 v2.0",
    add_completion=False,
    no_args_is_help=True,
)


@app.callback()
def callback(
    ctx: typer.Context,
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="配置文件路径 (YAML)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="详细输出"
    ),
) -> None:
    """DQEngine: Data Quality Governance Framework.

    示例:
        dq profile data.csv
        dq auto data.csv --config configs/default.yaml
        dq semantic data.csv
        dq batch ./datasets
        dq pipeline data.csv
        dq plugins
        dq doctor
    """
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    ctx.obj["verbose"] = verbose


# ============================================================================
# 第一阶段命令 (保持向后兼容)
# ============================================================================


@app.command()
def version() -> None:
    """显示 DQEngine 版本信息."""
    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]DQEngine[/bold cyan] v{__version__}\n"
            "Data Quality Governance Framework\n"
            "https://github.com/M-stars/DQEngine",
            title="版本信息",
            border_style="cyan",
        )
    )
    console.print()


@app.command()
def profile(
    file: str = typer.Argument(..., help="数据文件路径 (CSV/Excel/JSON/Parquet)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="保存画像为 JSON"),
) -> None:
    """分析数据集并显示字段统计信息."""
    path = Path(file)
    if not path.exists():
        print_error(f"文件未找到: {file}")
        raise typer.Exit(code=1)

    console.print()
    console.print(Panel.fit(f"[bold]数据分析:[/bold] {path.name}", border_style="cyan"))

    loader = DataLoader()
    profiler = Profiler()
    scorer = QualityScorer()

    try:
        df = loader.load(path)
    except Exception as e:
        print_error(f"加载文件失败: {e}")
        raise typer.Exit(code=1)

    profile_result = profiler.profile(df, file_path=str(path))
    quality_score = scorer.score(df, profile_result)

    # 概览表
    overview_rows = [
        ["行数", str(profile_result.row_count)],
        ["列数", str(profile_result.column_count)],
        ["总单元格", str(profile_result.total_cells)],
        ["重复行", f"{profile_result.duplicate_row_count} ({profile_result.duplicate_row_rate:.2%})"],
        ["内存使用", f"{profile_result.memory_usage_mb:.2f} MB"],
    ]
    console.print(create_table("数据概览", ["指标", "值"], overview_rows))
    console.print()

    # 字段统计表
    col_rows = []
    for c in profile_result.columns:
        col_rows.append([
            c.column_name,
            c.dtype,
            str(c.non_null_count),
            f"{c.null_rate:.2%}",
            str(c.unique_count),
            f"{c.mean:.2f}" if c.mean is not None else "-",
            f"{c.min_val:.2f}" if c.min_val is not None else "-",
            f"{c.max_val:.2f}" if c.max_val is not None else "-",
        ])

    console.print(
        create_table(
            "字段统计",
            ["字段", "类型", "非空数", "空值率", "唯一值", "均值", "最小", "最大"],
            col_rows,
        )
    )
    console.print()

    # 质量评分
    console.print(render_score_gauge(quality_score.overall_score, "数据质量评分"))

    # 维度分解
    dim_rows = [[d.name, f"{d.score:.1f}/100", f"{d.weight:.0%}"] for d in quality_score.dimensions]
    console.print()
    console.print(create_table("质量维度", ["维度", "评分", "权重"], dim_rows))

    if output:
        import json
        out_path = Path(output)
        out_path.write_text(profile_result.model_dump_json(indent=2, encoding="utf-8"))
        print_success(f"画像已保存至: {out_path}")

    console.print()


@app.command()
def auto(
    file: str = typer.Argument(..., help="数据文件路径 (CSV/Excel/JSON/Parquet)"),
    output: str = typer.Option("cleaned_data.csv", "--output", "-o", help="输出文件路径"),
    report: str = typer.Option("report.html", "--report", "-r", help="报告输出路径"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    no_outlier_removal: bool = typer.Option(False, "--no-outlier-removal", help="跳过异常值移除"),
) -> None:
    """自动检测并修复数据质量问题: 空值、重复、日期、异常值."""
    path = Path(file)
    if not path.exists():
        print_error(f"文件未找到: {file}")
        raise typer.Exit(code=1)

    # 加载配置
    app_config = AppConfig()
    if config:
        from dqengine.services.config_manager import ConfigManager
        cm = ConfigManager()
        app_config = cm.load(config)

    console.print()
    console.print(Panel.fit(f"[bold]自动清洗:[/bold] {path.name}", border_style="cyan"))

    # 使用编排器
    from dqengine.services.orchestrator import CleaningOrchestrator
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]清洗进行中...", total=None)

        orchestrator = CleaningOrchestrator(app_config)
        result = orchestrator.run(
            file_path=file,
            output_path=output,
            report_path=report,
        )

        progress.update(task, completed=True, description="[green]清洗完成!")

    # 显示汇总
    console.print()
    score_before = result["score_before"]
    score_after = result["score_after"]
    console.print(Panel.fit(
        f"行数: {result['rows_before']} → {result['rows_after']}  |  "
        f"评分: {score_before.overall_score:.1f} → [bold green]{score_after.overall_score:.1f}[/bold green]  |  "
        f"等级: [bold]{score_after.grade}[/bold]",
        title="清洗汇总",
        border_style="green",
    ))
    console.print()


@app.command()
def validate(
    file: str = typer.Argument(..., help="数据文件路径"),
    rules: str = typer.Option(..., "--rules", "-r", help="YAML 规则文件路径"),
) -> None:
    """根据 YAML 规则验证数据."""
    path = Path(file)
    rules_path = Path(rules)

    if not path.exists():
        print_error(f"文件未找到: {file}")
        raise typer.Exit(code=1)
    if not rules_path.exists():
        print_error(f"规则文件未找到: {rules}")
        raise typer.Exit(code=1)

    console.print()
    console.print(
        Panel.fit(
            f"[bold]规则验证:[/bold] {path.name}  [dim]检测规则[/dim]  [bold]{rules_path.name}[/bold]",
            border_style="cyan",
        )
    )

    loader = DataLoader()
    validator = RuleValidator()

    try:
        df = loader.load(path)
    except Exception as e:
        print_error(f"加载文件失败: {e}")
        raise typer.Exit(code=1)

    result = validator.validate(df, rules)

    status_style = "green" if result.passed else "red"
    status_text = "通过" if result.passed else "未通过"
    console.print()
    console.print(
        Panel.fit(
            f"状态: [bold {status_style}]{status_text}[/bold {status_style}]\n"
            f"规则: {result.total_rules} 总计, "
            f"[green]{result.passed_rules} 通过[/green], "
            f"[red]{result.failed_rules} 未通过[/red]\n"
            f"违规: {result.total_violations} 条",
            border_style=status_style,
        )
    )

    if result.violations:
        console.print()
        violation_rows = [
            [v.column, v.rule_type, str(v.row_index), str(v.value), v.message]
            for v in result.violations[:50]
        ]
        console.print(
            create_table(
                f"违规记录 (显示 {min(len(result.violations), 50)} / {len(result.violations)})",
                ["字段", "规则", "行", "值", "消息"],
                violation_rows,
            )
        )

    if not result.passed:
        raise typer.Exit(code=1)
    console.print()


# ============================================================================
# 第二阶段新增命令
# ============================================================================


@app.command()
def semantic(
    file: str = typer.Argument(..., help="数据文件路径"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="保存结果为 JSON"),
) -> None:
    """自动识别数据字段的语义类型.

    示例:
        dq semantic examples/sample.csv
        dq semantic data.json -o semantic_result.json
    """
    path = Path(file)
    if not path.exists():
        print_error(f"文件未找到: {file}")
        raise typer.Exit(code=1)

    from dqengine.semantic import SemanticDetector

    console.print()
    console.print(Panel.fit(f"[bold]语义识别:[/bold] {path.name}", border_style="cyan"))

    loader = DataLoader()
    detector = SemanticDetector()

    try:
        df = loader.load(path)
    except Exception as e:
        print_error(f"加载文件失败: {e}")
        raise typer.Exit(code=1)

    result = detector.detect(df, file_path=str(path))

    # 显示结果
    recognized = [f for f in result.fields if f.detected_type != SemanticType.UNKNOWN]
    unknown = [f for f in result.fields if f.detected_type == SemanticType.UNKNOWN]

    print_success(f"识别完成: {len(recognized)}/{result.total_columns} 个字段已识别")
    console.print()

    # 已识别字段表格
    if recognized:
        rec_rows = []
        for f in recognized:
            conf_color = "green" if f.confidence >= 0.8 else "yellow" if f.confidence >= 0.5 else "red"
            rec_rows.append([
                f.column_name,
                f"[bold]{f.detected_type.value}[/bold]",
                f"[{conf_color}]{f.confidence:.1%}[/{conf_color}]",
                f.matched_patterns[0] if f.matched_patterns else "-",
                ", ".join(str(v) for v in f.sample_values[:3]),
            ])
        console.print(
            create_table(
                f"已识别字段 ({len(recognized)})",
                ["字段名", "语义类型", "置信度", "匹配模式", "样例值"],
                rec_rows,
            )
        )
        console.print()

    # 未识别字段
    if unknown:
        unk_rows = [[f.column_name, ", ".join(str(v) for v in f.sample_values[:3])] for f in unknown]
        console.print(
            create_table(
                f"未识别字段 ({len(unknown)})",
                ["字段名", "样例值"],
                unk_rows,
            )
        )
        console.print()

    if output:
        out_path = Path(output)
        out_path.write_text(result.model_dump_json(indent=2, encoding="utf-8"))
        print_success(f"语义分析结果已保存: {out_path}")

    console.print()


@app.command()
def batch(
    directory: str = typer.Argument(..., help="数据目录路径"),
    output_dir: str = typer.Option("batch_output", "--output", "-o", help="输出目录"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    workers: int = typer.Option(4, "--workers", "-w", help="并发处理数"),
) -> None:
    """批量处理目录中的所有数据文件.

    自动遍历目录中的 CSV/Excel/JSON/Parquet 文件,
    执行清洗、评分并生成报告.

    示例:
        dq batch ./datasets
        dq batch ./datasets -o ./results -w 8
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        print_error(f"目录不存在: {directory}")
        raise typer.Exit(code=1)

    # 加载配置
    app_config = AppConfig()
    if config:
        from dqengine.services.config_manager import ConfigManager
        cm = ConfigManager()
        app_config = cm.load(config)

    console.print()
    console.print(
        Panel.fit(f"[bold]批量处理:[/bold] {dir_path}", border_style="cyan")
    )

    from dqengine.batch import BatchProcessor
    processor = BatchProcessor(config=app_config, max_workers=workers)
    summary = processor.process(directory, output_dir=output_dir)

    # 显示汇总
    console.print()
    console.print(
        Panel.fit(
            f"文件: {summary.total_files} 总计, "
            f"[green]{summary.succeeded} 成功[/green], "
            f"[red]{summary.failed} 失败[/red]\n"
            f"行数: {summary.total_rows_before} → {summary.total_rows_after}\n"
            f"评分: {summary.average_score_before:.1f} → "
            f"[bold green]{summary.average_score_after:.1f}[/bold green]",
            title="批量处理汇总",
            border_style="green",
        )
    )

    # 显示各文件结果
    if summary.files:
        file_rows = []
        for f in summary.files:
            if f.success:
                file_rows.append([
                    Path(f.file_path).name,
                    "[green]成功[/green]",
                    str(f.rows_before),
                    str(f.rows_after),
                    f"{f.score_before:.1f} → {f.score_after:.1f}",
                ])
            else:
                file_rows.append([
                    Path(f.file_path).name,
                    "[red]失败[/red]",
                    "-", "-", "-",
                    f.error or "未知错误",
                ])

        console.print()
        console.print(
            create_table(
                "文件处理详情",
                ["文件名", "状态", "前行数", "后行数", "评分变化"],
                file_rows,
            )
        )

    console.print()


@app.command()
def pipeline(
    file: str = typer.Argument(..., help="数据文件路径"),
    output: str = typer.Option("generated_pipeline.py", "--output", "-o", help="输出脚本路径"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """根据数据特征自动生成可重复执行的数据治理 Pipeline.

    生成的 Python 脚本包含完整的清洗、验证、评分流程.

    示例:
        dq pipeline data.csv
        dq pipeline data.csv -o my_pipeline.py
    """
    path = Path(file)
    if not path.exists():
        print_error(f"文件未找到: {file}")
        raise typer.Exit(code=1)

    # 加载配置
    app_config = AppConfig()
    if config:
        from dqengine.services.config_manager import ConfigManager
        cm = ConfigManager()
        app_config = cm.load(config)

    console.print()
    console.print(Panel.fit(f"[bold]生成 Pipeline:[/bold] {path.name}", border_style="cyan"))

    from dqengine.pipeline import PipelineGenerator
    generator = PipelineGenerator(app_config)
    output_path = generator.generate(file, output)

    print_success(f"Pipeline 已生成: {output_path}")
    console.print()
    console.print(f"[dim]运行方式:[/dim] python {output_path.name} {path.name}")
    console.print()


@app.command()
def plugins(
    plugin_type: Optional[str] = typer.Option(None, "--type", "-t", help="插件类型: validator, cleaner, scorer"),
) -> None:
    """列出所有已加载的插件.

    示例:
        dq plugins
        dq plugins --type validator
    """
    from dqengine.registry.plugin_registry import get_plugin_registry

    console.print()
    console.print(Panel.fit("[bold]插件列表[/bold]", border_style="cyan"))

    registry = get_plugin_registry()

    # 自动发现 plugins/ 目录下的插件
    plugins_dir = Path("plugins")
    if not plugins_dir.exists():
        plugins_dir = Path(__file__).parent.parent / "plugins"
    registry.discover(plugins_dir)

    pt = None
    if plugin_type:
        try:
            pt = PluginType(plugin_type)
        except ValueError:
            print_error(f"未知插件类型: {plugin_type}")
            print_info(f"可用类型: {[t.value for t in PluginType]}")
            raise typer.Exit(code=1)

    all_plugins = registry.list_plugins(pt)

    if not all_plugins:
        console.print("[dim]未加载任何插件[/dim]")
        console.print()
        console.print(f"[dim]将自定义插件放入 plugins/ 目录即可自动加载[/dim]")
    else:
        plugin_rows = []
        for p in all_plugins:
            status = "[green]启用[/green]" if p.enabled else "[red]禁用[/red]"
            plugin_rows.append([
                p.name,
                p.plugin_type.value,
                p.version,
                status,
                p.description,
            ])
        console.print(
            create_table(
                f"已加载插件 ({len(all_plugins)})",
                ["名称", "类型", "版本", "状态", "描述"],
                plugin_rows,
            )
        )

    console.print()


@app.command()
def doctor() -> None:
    """环境诊断: 检查 Python、依赖、配置、插件状态.

    示例:
        dq doctor
    """
    console.print()
    console.print(Panel.fit("[bold]DQEngine 环境诊断[/bold]", border_style="cyan"))

    # 构建诊断结果
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    issues: list[str] = []
    suggestions: list[str] = []
    deps: dict[str, str] = {}

    # 检查核心依赖
    core_deps = {
        "typer": "CLI框架",
        "rich": "终端美化",
        "pandas": "数据处理",
        "pydantic": "数据验证",
        "pyyaml": "YAML解析",
        "jinja2": "模板引擎",
        "openpyxl": "Excel支持",
        "pyarrow": "Parquet支持",
        "plotly": "图表生成",
        "tqdm": "进度条",
    }

    for dep, desc in core_deps.items():
        try:
            mod = __import__(dep)
            version = getattr(mod, "__version__", "已安装")
            deps[dep] = f"[green]{version}[/green] ({desc})"
        except ImportError:
            deps[dep] = f"[red]未安装[/red] ({desc})"
            issues.append(f"缺少依赖: {dep} ({desc})")

    # 检查插件
    from dqengine.registry.plugin_registry import get_plugin_registry
    registry = get_plugin_registry()
    plugins_dir = Path("plugins")
    if not plugins_dir.exists():
        plugins_dir = Path(__file__).parent.parent / "plugins"
    loaded_plugins = registry.discover(plugins_dir)
    plugin_names = [p.name for p in loaded_plugins]

    # 检查配置文件
    config_found = Path("configs/default.yaml").exists()

    if not config_found:
        suggestions.append("建议创建 configs/default.yaml 配置文件")

    if not loaded_plugins:
        suggestions.append("建议将自定义插件放入 plugins/ 目录")

    # 显示诊断信息
    # Python版本
    python_status = "[green]正常[/green]" if sys.version_info >= (3, 9) else "[red]需要>=3.9[/red]"
    info_rows = [
        ["Python 版本", f"{python_version} {python_status}"],
        ["DQEngine 版本", f"v{__version__}"],
        ["配置文件", f"[green]已找到[/green]" if config_found else "[yellow]未找到[/yellow]"],
        ["已加载插件", f"{len(loaded_plugins)} 个"],
    ]
    console.print(create_table("环境信息", ["项目", "状态"], info_rows))
    console.print()

    # 依赖检查
    dep_rows = [[dep, status] for dep, status in deps.items()]
    console.print(create_table("依赖检查", ["依赖包", "状态"], dep_rows))
    console.print()

    # 问题和建议
    if issues:
        console.print("[bold red]发现的问题:[/bold red]")
        for issue in issues:
            console.print(f"  [red]X[/red] {issue}")
        console.print()

    if suggestions:
        console.print("[bold yellow]建议:[/bold yellow]")
        for sug in suggestions:
            console.print(f"  [yellow]>>[/yellow] {sug}")
        console.print()

    all_ok = len(issues) == 0
    if all_ok:
        print_success("环境诊断通过, 一切正常!")
    else:
        print_warning(f"环境诊断完成, 发现 {len(issues)} 个问题")

    console.print()


def main() -> None:
    """入口函数."""
    app()


if __name__ == "__main__":
    app()
