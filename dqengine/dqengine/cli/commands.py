"""DQEngine CLI — Typer-powered command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel

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
    help="DQEngine — A lightweight data quality governance framework.",
    add_completion=False,
    no_args_is_help=True,
)


@app.callback()
def callback() -> None:
    """DQEngine: Data Quality Governance Framework."""


@app.command()
def version() -> None:
    """Show DQEngine version."""
    console.print(f"[bold cyan]DQEngine[/bold cyan] v{__version__}")


@app.command()
def profile(
    file: str = typer.Argument(..., help="Path to CSV or Excel file"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save profile as JSON"),
) -> None:
    """Profile a dataset and display column statistics."""
    path = Path(file)
    if not path.exists():
        print_error(f"File not found: {file}")
        raise typer.Exit(code=1)

    console.print()
    console.print(Panel.fit(f"[bold]Profiling:[/bold] {path.name}", border_style="cyan"))

    loader = DataLoader()
    profiler = Profiler()
    scorer = QualityScorer()

    try:
        df = loader.load(path)
    except Exception as e:
        print_error(f"Failed to load file: {e}")
        raise typer.Exit(code=1)

    profile_result = profiler.profile(df, file_path=str(path))
    quality_score = scorer.score(df, profile_result)

    # Overview table
    overview_rows = [
        ["Rows", str(profile_result.row_count)],
        ["Columns", str(profile_result.column_count)],
        ["Total Cells", str(profile_result.total_cells)],
        ["Duplicate Rows", f"{profile_result.duplicate_row_count} ({profile_result.duplicate_row_rate:.2%})"],
        ["Memory Usage", f"{profile_result.memory_usage_mb:.2f} MB"],
    ]
    console.print(create_table("Data Overview", ["Metric", "Value"], overview_rows))
    console.print()

    # Column profile table
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
            "Column Statistics",
            ["Column", "Type", "Non-Null", "Null Rate", "Unique", "Mean", "Min", "Max"],
            col_rows,
        )
    )
    console.print()

    # Quality score
    console.print(render_score_gauge(quality_score.overall_score, "Data Quality Score"))

    # Dimension breakdown
    dim_rows = [[d.name, f"{d.score:.1f}/100", f"{d.weight:.0%}"] for d in quality_score.dimensions]
    console.print()
    console.print(create_table("Quality Dimensions", ["Dimension", "Score", "Weight"], dim_rows))

    if output:
        import json
        out_path = Path(output)
        out_path.write_text(profile_result.model_dump_json(indent=2), encoding="utf-8")
        print_success(f"Profile saved to {out_path}")

    console.print()


@app.command()
def auto(
    file: str = typer.Argument(..., help="Path to CSV or Excel file"),
    output: str = typer.Option("cleaned_data.csv", "--output", "-o", help="Output file path"),
    report: str = typer.Option("report.html", "--report", "-r", help="Report output path"),
    no_outlier_removal: bool = typer.Option(False, "--no-outlier-removal", help="Skip outlier removal"),
) -> None:
    """Auto-detect and fix data quality issues: nulls, duplicates, dates, outliers."""
    path = Path(file)
    if not path.exists():
        print_error(f"File not found: {file}")
        raise typer.Exit(code=1)

    console.print()
    console.print(Panel.fit(f"[bold]Auto-Cleaning:[/bold] {path.name}", border_style="cyan"))

    loader = DataLoader()
    profiler = Profiler()
    scorer = QualityScorer()

    try:
        df = loader.load(path)
    except Exception as e:
        print_error(f"Failed to load file: {e}")
        raise typer.Exit(code=1)

    original_rows = len(df)
    repairs = []

    # Step 1: Profile before cleaning
    console.print("\n[bold]Step 1:[/bold] Profiling original data...")
    profile_before = profiler.profile(df, file_path=str(path))
    score_before = scorer.score(df, profile_before)
    console.print(f"  Quality score before: [yellow]{score_before.overall_score:.1f}[/yellow]")

    # Step 2: Remove duplicates
    console.print("\n[bold]Step 2:[/bold] Removing duplicate rows...")
    dup_cleaner = DuplicateCleaner()
    df, dup_result = dup_cleaner.clean(df)
    repairs.append(dup_result)
    print_success(f"  Removed {dup_result.changes_made} duplicate rows")

    # Step 3: Fill missing values
    console.print("\n[bold]Step 3:[/bold] Filling missing values...")
    mv_cleaner = MissingValueCleaner()
    df, mv_result = mv_cleaner.clean(df)
    repairs.append(mv_result)
    print_success(
        f"  Filled {mv_result.changes_made} missing values in {mv_result.columns_affected} columns"
    )

    # Step 4: Standardize dates
    console.print("\n[bold]Step 4:[/bold] Standardizing dates...")
    date_std = DateStandardizer()
    df, date_result = date_std.standardize(df)
    repairs.append(date_result)
    if date_result.columns_affected > 0:
        print_success(f"  Standardized {date_result.columns_affected} date columns")
    else:
        print_info("  No date columns detected")

    # Step 5: Detect outliers
    outliers = []
    if not no_outlier_removal:
        console.print("\n[bold]Step 5:[/bold] Detecting outliers (IQR method)...")
        outlier_detector = OutlierDetector()
        outliers = outlier_detector.detect(df)
        summary = outlier_detector.summary(outliers)
        if summary:
            for col, counts in summary.items():
                console.print(
                    f"  {col}: [yellow]{counts['mild']} mild[/yellow], "
                    f"[red]{counts['extreme']} extreme[/red]"
                )
        else:
            print_info("  No outliers detected")
    else:
        console.print("\n[bold]Step 5:[/bold] Outlier detection [dim](skipped)[/dim]")

    # Step 6: Profile after cleaning
    console.print("\n[bold]Step 6:[/bold] Profiling cleaned data...")
    profile_after = profiler.profile(df, file_path=str(path))
    score_after = scorer.score(df, profile_after)
    console.print(f"  Quality score after: [green]{score_after.overall_score:.1f}[/green]")

    # Save cleaned data
    out_path = Path(output)
    if out_path.suffix.lower() == ".xlsx":
        df.to_excel(out_path, index=False)
    else:
        df.to_csv(out_path, index=False, encoding="utf-8")
    print_success(f"\nCleaned data saved to: {out_path}")

    # Generate report
    report_gen = ReportGenerator()
    report_path = report_gen.generate(
        profile=profile_after,
        score=score_after,
        repairs=repairs,
        outliers=outliers,
        output_path=report,
    )
    print_success(f"Report saved to: {report_path}")

    # Summary
    console.print()
    console.print(Panel.fit(
        f"Rows: {original_rows} → {len(df)}  |  "
        f"Score: {score_before.overall_score:.1f} → [bold green]{score_after.overall_score:.1f}[/bold green]  |  "
        f"Grade: [bold]{score_after.grade}[/bold]",
        title="Cleaning Summary",
        border_style="green",
    ))
    console.print()


@app.command()
def validate(
    file: str = typer.Argument(..., help="Path to CSV or Excel file"),
    rules: str = typer.Option(..., "--rules", "-r", help="Path to YAML rules file"),
) -> None:
    """Validate data against YAML-defined rules."""
    path = Path(file)
    rules_path = Path(rules)

    if not path.exists():
        print_error(f"File not found: {file}")
        raise typer.Exit(code=1)
    if not rules_path.exists():
        print_error(f"Rules file not found: {rules}")
        raise typer.Exit(code=1)

    console.print()
    console.print(
        Panel.fit(
            f"[bold]Validating:[/bold] {path.name}  [dim]against[/dim]  [bold]{rules_path.name}[/bold]",
            border_style="cyan",
        )
    )

    loader = DataLoader()
    validator = RuleValidator()

    try:
        df = loader.load(path)
    except Exception as e:
        print_error(f"Failed to load file: {e}")
        raise typer.Exit(code=1)

    result = validator.validate(df, rules)

    # Summary
    status_style = "green" if result.passed else "red"
    status_text = "PASSED" if result.passed else "FAILED"
    console.print()
    console.print(
        Panel.fit(
            f"Status: [bold {status_style}]{status_text}[/bold {status_style}]\n"
            f"Rules: {result.total_rules} total, "
            f"[green]{result.passed_rules} passed[/green], "
            f"[red]{result.failed_rules} failed[/red]\n"
            f"Violations: {result.total_violations}",
            border_style=status_style,
        )
    )

    # Violations detail
    if result.violations:
        console.print()
        violation_rows = [
            [v.column, v.rule_type, str(v.row_index), str(v.value), v.message]
            for v in result.violations[:50]
        ]
        console.print(
            create_table(
                f"Violations (showing {min(len(result.violations), 50)} of {len(result.violations)})",
                ["Column", "Rule", "Row", "Value", "Message"],
                violation_rows,
            )
        )

    if not result.passed:
        raise typer.Exit(code=1)
    console.print()


def main() -> None:
    """Entry point for console_scripts."""
    app()


if __name__ == "__main__":
    app()
