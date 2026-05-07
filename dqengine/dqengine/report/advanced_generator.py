"""高级报告生成器 - 支持 JSON / Markdown / HTML (Plotly图表)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from dqengine.models.schemas import (
    ProfileResult,
    QualityScore,
    RepairResult,
    OutlierRecord,
    ReportFormat,
)
from dqengine.utils.logger import get_logger

logger = get_logger(__name__)


class AdvancedReportGenerator:
    """高级报告生成器.

    支持格式:
        - JSON: 结构化机器可读报告
        - Markdown: 文档化报告
        - HTML: 包含 Plotly 交互图表的可视化报告
    """

    def __init__(self, output_dir: "str | Path" = "reports") -> None:
        """初始化报告生成器.

        Args:
            output_dir: 报告输出目录.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        profile: ProfileResult,
        score: QualityScore,
        repairs: List[RepairResult],
        outliers: List[OutlierRecord],
        df: Optional[pd.DataFrame] = None,
        formats: Optional[List[ReportFormat]] = None,
    ) -> List[Path]:
        """生成多种格式的报告.

        Args:
            profile: 数据画像结果.
            score: 质量评分.
            repairs: 修复记录.
            outliers: 异常值记录.
            df: 清洗后的 DataFrame (用于生成图表).
            formats: 报告格式列表, 默认为所有格式.

        Returns:
            生成的报告文件路径列表.
        """
        if formats is None:
            formats = [ReportFormat.HTML, ReportFormat.JSON, ReportFormat.MARKDOWN]

        generated: List[Path] = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for fmt in formats:
            if fmt == ReportFormat.HTML:
                path = self._generate_html(profile, score, repairs, outliers, df, timestamp)
            elif fmt == ReportFormat.JSON:
                path = self._generate_json(profile, score, repairs, outliers, timestamp)
            elif fmt == ReportFormat.MARKDOWN:
                path = self._generate_markdown(profile, score, repairs, outliers, timestamp)
            else:
                continue
            generated.append(path)

        return generated

    def _generate_html(
        self,
        profile: ProfileResult,
        score: QualityScore,
        repairs: List[RepairResult],
        outliers: List[OutlierRecord],
        df: Optional[pd.DataFrame],
        timestamp: str,
    ) -> Path:
        """生成增强版 HTML 报告 (包含 Plotly 图表).

        Args:
            profile: 数据画像.
            score: 质量评分.
            repairs: 修复记录.
            outliers: 异常值.
            df: DataFrame.
            timestamp: 时间戳.

        Returns:
            HTML 文件路径.
        """
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            charts_html = self._generate_plotly_charts(profile, score, outliers, df)
        except ImportError:
            logger.warning("Plotly 未安装, 跳过图表生成")
            charts_html = "<p>图表不可用 (需安装 plotly)</p>"

        # 异常值汇总
        outlier_summary: Dict[str, Dict[str, int]] = {}
        for o in outliers:
            if o.column not in outlier_summary:
                outlier_summary[o.column] = {"mild": 0, "extreme": 0}
            outlier_summary[o.column][o.severity] += 1

        html_content = self._render_html_template(
            profile=profile,
            score=score,
            repairs=repairs,
            outliers=outliers,
            outlier_summary=outlier_summary,
            charts_html=charts_html,
            timestamp=timestamp,
        )

        output_path = self.output_dir / f"quality_report_{timestamp}.html"
        output_path.write_text(html_content, encoding="utf-8")
        logger.info("HTML 报告已生成: %s", output_path)

        return output_path

    def _generate_plotly_charts(
        self,
        profile: ProfileResult,
        score: QualityScore,
        outliers: List[OutlierRecord],
        df: Optional[pd.DataFrame],
    ) -> str:
        """生成 Plotly 图表的 HTML.

        Args:
            profile: 数据画像.
            score: 质量评分.
            outliers: 异常值.
            df: DataFrame.

        Returns:
            图表 HTML 字符串.
        """
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        charts = []

        # 1. 质量评分仪表盘
        gauge = go.Figure(
            go.Indicator(
                mode="gauge+number+delta",
                value=score.overall_score,
                title={"text": f"数据质量评分 - 等级: {score.grade}"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": self._score_color(score.overall_score)},
                    "steps": [
                        {"range": [0, 40], "color": "#ffdddd"},
                        {"range": [40, 60], "color": "#ffffcc"},
                        {"range": [60, 80], "color": "#ccffcc"},
                        {"range": [80, 100], "color": "#ccffcc"},
                    ],
                    "threshold": {
                        "line": {"color": "red", "width": 4},
                        "thickness": 0.75,
                        "value": score.overall_score,
                    },
                },
            )
        )
        gauge.update_layout(height=300)
        charts.append(gauge.to_html(full_html=False, include_plotlyjs="cdn"))

        # 2. 缺失值分布图
        if profile.columns:
            col_names = [c.column_name for c in profile.columns]
            null_rates = [c.null_rate * 100 for c in profile.columns]

            missing_fig = go.Figure(
                go.Bar(
                    x=col_names,
                    y=null_rates,
                    marker_color=[
                        "red" if r > 50 else "orange" if r > 20 else "green"
                        for r in null_rates
                    ],
                    text=[f"{r:.1f}%" for r in null_rates],
                    textposition="auto",
                )
            )
            missing_fig.update_layout(
                title="各字段缺失值比例",
                xaxis_title="字段",
                yaxis_title="缺失率 (%)",
                height=400,
            )
            charts.append(missing_fig.to_html(full_html=False, include_plotlyjs="cdn"))

        # 3. 异常值柱状图
        if outliers:
            outlier_summary: Dict[str, Dict[str, int]] = {}
            for o in outliers:
                if o.column not in outlier_summary:
                    outlier_summary[o.column] = {"mild": 0, "extreme": 0}
                outlier_summary[o.column][o.severity] += 1

            out_cols = list(outlier_summary.keys())
            mild_vals = [outlier_summary[c]["mild"] for c in out_cols]
            extreme_vals = [outlier_summary[c]["extreme"] for c in out_cols]

            outlier_fig = go.Figure()
            outlier_fig.add_trace(
                go.Bar(name="轻微异常", x=out_cols, y=mild_vals, marker_color="#f39c12")
            )
            outlier_fig.add_trace(
                go.Bar(name="严重异常", x=out_cols, y=extreme_vals, marker_color="#e74c3c")
            )
            outlier_fig.update_layout(
                title="异常值分布",
                xaxis_title="字段",
                yaxis_title="异常值数量",
                barmode="group",
                height=400,
            )
            charts.append(outlier_fig.to_html(full_html=False, include_plotlyjs="cdn"))

        # 4. 数值字段分布图 (使用清洗后数据)
        if df is not None:
            numeric_cols = df.select_dtypes(include=["number"]).columns
            for col in list(numeric_cols)[:4]:  # 最多4个
                hist_fig = go.Figure()
                hist_fig.add_trace(
                    go.Histogram(x=df[col].dropna(), name=col, nbinsx=30)
                )
                hist_fig.update_layout(
                    title=f"{col} 分布",
                    xaxis_title=col,
                    yaxis_title="频数",
                    height=300,
                )
                charts.append(hist_fig.to_html(full_html=False, include_plotlyjs="cdn"))

        return "\n".join(charts)

    def _generate_json(
        self,
        profile: ProfileResult,
        score: QualityScore,
        repairs: List[RepairResult],
        outliers: List[OutlierRecord],
        timestamp: str,
    ) -> Path:
        """生成 JSON 格式报告.

        Args:
            profile: 数据画像.
            score: 质量评分.
            repairs: 修复记录.
            outliers: 异常值.
            timestamp: 时间戳.

        Returns:
            JSON 文件路径.
        """
        report_data = {
            "title": "DQEngine Data Quality Report",
            "generated_at": datetime.now().isoformat(),
            "file_path": profile.file_path,
            "overview": {
                "row_count": profile.row_count,
                "column_count": profile.column_count,
                "total_cells": profile.total_cells,
                "duplicate_row_count": profile.duplicate_row_count,
                "duplicate_rate": profile.duplicate_row_rate,
                "memory_usage_mb": profile.memory_usage_mb,
            },
            "quality_score": {
                "overall": score.overall_score,
                "grade": score.grade,
                "dimensions": [
                    {
                        "name": d.name,
                        "score": d.score,
                        "weight": d.weight,
                        "description": d.description,
                    }
                    for d in score.dimensions
                ],
            },
            "column_statistics": [
                c.model_dump() for c in profile.columns
            ],
            "repairs": [
                {
                    "operation": r.operation,
                    "rows_before": r.rows_before,
                    "rows_after": r.rows_after,
                    "columns_affected": r.columns_affected,
                    "changes_made": r.changes_made,
                    "details": r.details,
                }
                for r in repairs
            ],
            "outliers": {
                "total": len(outliers),
                "records": [o.model_dump() for o in outliers[:100]],  # 最多100条
            },
        }

        output_path = self.output_dir / f"quality_report_{timestamp}.json"
        output_path.write_text(
            json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("JSON 报告已生成: %s", output_path)

        return output_path

    def _generate_markdown(
        self,
        profile: ProfileResult,
        score: QualityScore,
        repairs: List[RepairResult],
        outliers: List[OutlierRecord],
        timestamp: str,
    ) -> Path:
        """生成 Markdown 格式报告.

        Args:
            profile: 数据画像.
            score: 质量评分.
            repairs: 修复记录.
            outliers: 异常值.
            timestamp: 时间戳.

        Returns:
            Markdown 文件路径.
        """
        lines = []
        lines.append("# DQEngine Data Quality Report")
        lines.append("")
        lines.append(f"**生成时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**数据文件:** `{profile.file_path}`")
        lines.append("")
        lines.append("---")
        lines.append("")

        # 质量评分
        lines.append("## 数据质量评分")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|----|")
        lines.append(f"| **总分** | **{score.overall_score:.1f} / 100** |")
        lines.append(f"| **等级** | **{score.grade}** |")
        for d in score.dimensions:
            lines.append(f"| {d.name} | {d.score:.1f} (权重: {d.weight:.0%}) |")
        lines.append("")

        # 数据概览
        lines.append("## 数据概览")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|----|")
        lines.append(f"| 总行数 | {profile.row_count} |")
        lines.append(f"| 总列数 | {profile.column_count} |")
        lines.append(f"| 总单元格 | {profile.total_cells} |")
        lines.append(f"| 重复行 | {profile.duplicate_row_count} ({profile.duplicate_row_rate:.2%}) |")
        lines.append(f"| 内存使用 | {profile.memory_usage_mb:.2f} MB |")
        lines.append("")

        # 字段统计
        lines.append("## 字段统计")
        lines.append("")
        lines.append("| 字段 | 类型 | 非空 | 空值率 | 唯一值 | 均值 | 最小 | 最大 |")
        lines.append("|------|------|------|--------|--------|------|------|------|")
        for c in profile.columns:
            mean_str = f"{c.mean:.2f}" if c.mean is not None else "-"
            min_str = f"{c.min_val:.2f}" if c.min_val is not None else "-"
            max_str = f"{c.max_val:.2f}" if c.max_val is not None else "-"
            lines.append(
                f"| {c.column_name} | {c.dtype} | {c.non_null_count} | "
                f"{c.null_rate:.1%} | {c.unique_count} | {mean_str} | {min_str} | {max_str} |"
            )
        lines.append("")

        # 修复操作
        if repairs:
            lines.append("## 修复操作")
            lines.append("")
            lines.append("| 操作 | 前行数 | 后行数 | 变更数 | 影响列 |")
            lines.append("|------|--------|--------|--------|--------|")
            for r in repairs:
                lines.append(
                    f"| {r.operation} | {r.rows_before} | {r.rows_after} | "
                    f"{r.changes_made} | {r.columns_affected} |"
                )
            lines.append("")

        # 异常值
        if outliers:
            lines.append(f"## 异常值检测 ({len(outliers)} 个)")
            lines.append("")
            lines.append("| 字段 | 行索引 | 值 | 严重度 |")
            lines.append("|------|--------|------|--------|")
            for o in outliers[:20]:
                lines.append(f"| {o.column} | {o.row_index} | {o.value:.4f} | {o.severity} |")
            if len(outliers) > 20:
                lines.append(f"| ... | ... | ... | ... |")
                lines.append(f"| *共 {len(outliers)} 条, 仅显示前20条* |")
            lines.append("")

        lines.append("---")
        lines.append("*Powered by DQEngine — Data Quality Governance Framework*")

        output_path = self.output_dir / f"quality_report_{timestamp}.md"
        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Markdown 报告已生成: %s", output_path)

        return output_path

    @staticmethod
    def _score_color(score: float) -> str:
        """根据评分返回颜色."""
        if score >= 80:
            return "#27ae60"
        elif score >= 60:
            return "#f39c12"
        elif score >= 40:
            return "#e67e22"
        else:
            return "#e74c3c"

    @staticmethod
    def _render_html_template(
        profile: ProfileResult,
        score: QualityScore,
        repairs: List[RepairResult],
        outliers: List[OutlierRecord],
        outlier_summary: Dict[str, Dict[str, int]],
        charts_html: str,
        timestamp: str,
    ) -> str:
        """渲染增强版HTML报告模板.

        Returns:
            HTML字符串.
        """
        score_color = AdvancedReportGenerator._score_color(score.overall_score)

        # 生成维度条
        dim_bars = ""
        for dim in score.dimensions:
            dim_bars += f"""
            <div class="dimension-bar">
                <span class="dimension-name">{dim.name}</span>
                <div style="flex:1; background:#ecf0f1; border-radius:11px;">
                    <div class="dimension-fill" style="width:{dim.score}%; background:{score_color};"></div>
                </div>
                <span class="dimension-score">{dim.score}/100</span>
            </div>"""

        # 生成异常值行
        outlier_rows = ""
        for col, counts in outlier_summary.items():
            outlier_rows += f"""
            <tr>
                <td><strong>{col}</strong></td>
                <td><span class="badge badge-mild">{counts['mild']}</span></td>
                <td><span class="badge badge-extreme">{counts['extreme']}</span></td>
            </tr>"""

        # 生成修复行
        repair_rows = ""
        for r in repairs:
            repair_rows += f"""
            <tr>
                <td><strong>{r.operation}</strong></td>
                <td>{r.rows_before}</td>
                <td>{r.rows_after}</td>
                <td>{r.changes_made}</td>
                <td>{r.columns_affected}</td>
            </tr>"""

        # 生成字段行
        col_rows = ""
        for col in profile.columns:
            mean_str = f"{col.mean:.2f}" if col.mean is not None else "-"
            min_str = f"{col.min_val:.2f}" if col.min_val is not None else "-"
            max_str = f"{col.max_val:.2f}" if col.max_val is not None else "-"
            col_rows += f"""
            <tr>
                <td><strong>{col.column_name}</strong></td>
                <td>{col.dtype}</td>
                <td>{col.non_null_count}/{col.total_count}</td>
                <td>{(col.null_rate * 100):.1f}%</td>
                <td>{col.unique_count}</td>
                <td>{mean_str}</td>
                <td>{min_str}</td>
                <td>{max_str}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DQEngine Data Quality Report</title>
    <style>
        :root {{
            --bg: #f5f7fa;
            --card-bg: #ffffff;
            --text: #2c3e50;
            --text-secondary: #7f8c8d;
            --border: #e1e8ed;
            --accent: #3498db;
            --success: #27ae60;
            --warning: #f39c12;
            --danger: #e74c3c;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; padding: 20px; }}
        header {{
            background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
            color: white;
            padding: 40px 20px;
            text-align: center;
        }}
        header h1 {{ font-size: 2.2rem; font-weight: 700; margin-bottom: 8px; }}
        header .subtitle {{ opacity: 0.85; font-size: 0.95rem; }}
        .card {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 24px;
            margin: 16px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        .card h2 {{
            font-size: 1.3rem;
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 2px solid var(--border);
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
        }}
        .metric {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }}
        .metric-value {{ font-size: 1.6rem; font-weight: 700; color: var(--accent); }}
        .metric-label {{ font-size: 0.82rem; color: var(--text-secondary); margin-top: 4px; }}
        .dimension-bar {{
            display: flex;
            align-items: center;
            margin: 10px 0;
        }}
        .dimension-name {{ width: 160px; font-size: 0.9rem; font-weight: 500; }}
        .dimension-fill {{
            height: 22px;
            border-radius: 11px;
            transition: width 0.5s ease;
        }}
        .dimension-score {{ margin-left: 12px; font-weight: 600; font-size: 0.9rem; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        th, td {{
            padding: 10px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{ background: #f8f9fa; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; font-size: 0.78rem; }}
        tr:hover {{ background: #f8f9fa; }}
        .badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.78rem;
            font-weight: 600;
        }}
        .badge-mild {{ background: #fef3cd; color: #856404; }}
        .badge-extreme {{ background: #f8d7da; color: #721c24; }}
        .score-card {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 30px;
            margin: 20px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            text-align: center;
        }}
        .score-number {{ font-size: 3rem; font-weight: 800; color: {score_color}; }}
        .score-grade {{ font-size: 1.2rem; color: var(--text-secondary); }}
        footer {{
            text-align: center;
            padding: 30px;
            color: var(--text-secondary);
            font-size: 0.85rem;
        }}
    </style>
</head>
<body>
    <header>
        <h1>DQEngine Data Quality Report</h1>
        <div class="subtitle">Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Source: {profile.file_path}</div>
    </header>

    <div class="container">
        <div class="score-card">
            <h2>Overall Quality Score</h2>
            <div class="score-number">{score.overall_score:.1f}</div>
            <div class="score-grade">Grade: {score.grade}</div>
        </div>

        <div class="card">
            <h2>Data Overview</h2>
            <div class="metric-grid">
                <div class="metric">
                    <div class="metric-value">{profile.row_count}</div>
                    <div class="metric-label">Total Rows</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{profile.column_count}</div>
                    <div class="metric-label">Total Columns</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{profile.total_cells}</div>
                    <div class="metric-label">Total Cells</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{profile.duplicate_row_count}</div>
                    <div class="metric-label">Duplicate Rows</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{profile.memory_usage_mb:.2f} MB</div>
                    <div class="metric-label">Memory Usage</div>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>Quality Dimensions</h2>
            {dim_bars}
        </div>

        <div class="card">
            <h2>Interactive Charts</h2>
            {charts_html}
        </div>

        <div class="card">
            <h2>Column Statistics</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Column</th><th>Type</th><th>Non-Null</th>
                            <th>Null Rate</th><th>Unique</th>
                            <th>Mean</th><th>Min</th><th>Max</th>
                        </tr>
                    </thead>
                    <tbody>{col_rows}</tbody>
                </table>
            </div>
        </div>

        {"<div class='card'><h2>Outlier Summary</h2><table><thead><tr><th>Column</th><th>Mild</th><th>Extreme</th></tr></thead><tbody>" + outlier_rows + "</tbody></table></div>" if outliers else ""}

        {"<div class='card'><h2>Repair Operations</h2><table><thead><tr><th>Operation</th><th>Rows Before</th><th>Rows After</th><th>Changes</th><th>Columns Affected</th></tr></thead><tbody>" + repair_rows + "</tbody></table></div>" if repairs else ""}
    </div>

    <footer>
        Powered by <strong>DQEngine</strong> v0.2.0 &mdash; Data Quality Governance Framework
    </footer>
</body>
</html>"""
