"""Rich-powered console utilities for DQEngine CLI output."""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

console = Console()


def create_table(title: str, columns: list[str], rows: list[list[str]]) -> Table:
    """Create a Rich table with standard styling."""
    table = Table(title=title, title_style="bold cyan", header_style="bold white")
    for col in columns:
        table.add_column(col, style="green")
    for row in rows:
        table.add_row(*[str(c) for c in row])
    return table


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold green][OK][/bold green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold red][ERROR][/bold red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow][WARN][/bold yellow] {message}")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[bold blue][INFO][/bold blue] {message}")


def render_score_gauge(score: float, title: str = "Data Quality Score") -> Panel:
    """Render a visual score gauge using ASCII characters."""
    if score >= 80:
        color = "green"
        grade = "A"
    elif score >= 60:
        color = "yellow"
        grade = "B"
    elif score >= 40:
        color = "orange1"
        grade = "C"
    elif score >= 20:
        color = "red"
        grade = "D"
    else:
        color = "red"
        grade = "F"

    bar_width = 40
    filled = int(score / 100 * bar_width)
    bar = f"[{color}]" + "#" * filled + "[dim]" + "-" * (bar_width - filled)

    text = Text()
    text.append(f"\n{title}\n\n", style="bold")
    text.append(f"{bar}\n\n")
    text.append(f"Score: {score:.1f}/100  ", style=f"bold {color}")
    text.append(f"Grade: {grade}", style=f"bold {color}")

    return Panel(text, border_style=color)
