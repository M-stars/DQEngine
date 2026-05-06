"""HTML report generation using Jinja2 templates."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from dqengine.models.schemas import (
    ProfileResult,
    QualityScore,
    RepairResult,
    OutlierRecord,
)

TEMPLATE_DIR = Path(__file__).parent / "templates"


class ReportGenerator:
    """Generate an HTML quality report from profiling, scoring, and repair results.

    Usage:
        gen = ReportGenerator()
        gen.generate(profile, score, repairs, outliers, output_path="report.html")
    """

    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def generate(
        self,
        profile: ProfileResult,
        score: QualityScore,
        repairs: list[RepairResult],
        outliers: list[OutlierRecord],
        output_path: "str | Path" = "report.html",
    ) -> Path:
        """Render the HTML report and write to disk.

        Args:
            profile: Profiling result.
            score: Quality score.
            repairs: List of repair results.
            outliers: List of detected outliers.
            output_path: Output HTML file path.

        Returns:
            Path to the generated report.
        """
        template = self.env.get_template("report.html")

        outlier_summary: dict[str, dict[str, int]] = {}
        for o in outliers:
            if o.column not in outlier_summary:
                outlier_summary[o.column] = {"mild": 0, "extreme": 0}
            outlier_summary[o.column][o.severity] += 1

        html = template.render(
            title="DQEngine Data Quality Report",
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            profile=profile,
            score=score,
            repairs=repairs,
            outliers=outliers,
            outlier_summary=outlier_summary,
            outlier_count=len(outliers),
            score_color=self._score_color(score.overall_score),
        )

        output = Path(output_path)
        output.write_text(html, encoding="utf-8")
        return output

    @staticmethod
    def _score_color(score: float) -> str:
        if score >= 80:
            return "#27ae60"
        elif score >= 60:
            return "#f39c12"
        elif score >= 40:
            return "#e67e22"
        else:
            return "#e74c3c"
