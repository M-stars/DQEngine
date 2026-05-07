"""数据漂移检测器 - KS Test, PSI, 分布比较."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.models.schemas import (
    ColumnDriftResult,
    DriftReport,
    DriftSeverity,
    DriftType,
)


class DriftDetector:
    """数据漂移检测器.

    检测四类漂移:
    - Schema Drift: 列增删、类型变化
    - Distribution Drift: KS Test / PSI 数值分布变化
    - Null Drift: 空值率变化
    - Category Drift: 分类值分布变化

    Usage:
        detector = DriftDetector()
        report = detector.detect("baseline.csv", "current.csv")
    """

    # 阈值配置
    KS_THRESHOLD: Dict[str, float] = {"low": 0.1, "medium": 0.2, "high": 0.3}
    PSI_THRESHOLD: Dict[str, float] = {"low": 0.1, "medium": 0.2, "high": 0.3}
    NULL_CHANGE_THRESHOLD: Dict[str, float] = {"low": 0.05, "medium": 0.15, "high": 0.30}
    CATEGORY_CHANGE_THRESHOLD: Dict[str, float] = {"low": 0.05, "medium": 0.15, "high": 0.30}

    def __init__(self) -> None:
        self.loader = DataLoader()
        self.profiler = Profiler()

    def detect(
        self,
        baseline_path: str,
        current_path: str,
        output_json: Optional[str] = None,
        output_html: Optional[str] = None,
    ) -> DriftReport:
        """执行完整漂移检测."""
        baseline_df = self.loader.load(Path(baseline_path))
        current_df = self.loader.load(Path(current_path))

        baseline_profile = self.profiler.profile(baseline_df, file_path=baseline_path)
        current_profile = self.profiler.profile(current_df, file_path=current_path)

        schema_drift = self._detect_schema_drift(baseline_df, current_df)
        distribution_drift = self._detect_distribution_drift(baseline_df, current_df)
        null_drift = self._detect_null_drift(baseline_profile, current_profile)
        category_drift = self._detect_category_drift(baseline_df, current_df)

        all_drifts = schema_drift + distribution_drift + null_drift + category_drift

        return DriftReport(
            baseline_file=baseline_path,
            current_file=current_path,
            total_columns=max(len(baseline_df.columns), len(current_df.columns)),
            drifted_columns=len(set(d.column_name for d in all_drifts if d.severity != DriftSeverity.NONE)),
            overall_severity=self._compute_overall_severity(all_drifts),
            schema_drift=schema_drift,
            distribution_drift=distribution_drift,
            null_drift=null_drift,
            category_drift=category_drift,
        )

    def _detect_schema_drift(
        self, baseline_df: pd.DataFrame, current_df: pd.DataFrame
    ) -> List[ColumnDriftResult]:
        """检测 Schema 漂移."""
        results: List[ColumnDriftResult] = []
        baseline_cols = set(baseline_df.columns)
        current_cols = set(current_df.columns)

        # 新增列
        for col in current_cols - baseline_cols:
            results.append(
                ColumnDriftResult(
                    column_name=col,
                    drift_type=DriftType.SCHEMA,
                    severity=DriftSeverity.MEDIUM,
                    description=f"新增列: {col} (类型: {current_df[col].dtype})",
                )
            )

        # 删除列
        for col in baseline_cols - current_cols:
            results.append(
                ColumnDriftResult(
                    column_name=col,
                    drift_type=DriftType.SCHEMA,
                    severity=DriftSeverity.HIGH,
                    description=f"列已删除: {col}",
                )
            )

        # 类型变化
        for col in baseline_cols & current_cols:
            if str(baseline_df[col].dtype) != str(current_df[col].dtype):
                results.append(
                    ColumnDriftResult(
                        column_name=col,
                        drift_type=DriftType.SCHEMA,
                        severity=DriftSeverity.HIGH,
                        description=f"类型变化: {baseline_df[col].dtype} → {current_df[col].dtype}",
                    )
                )

        return results

    def _detect_distribution_drift(
        self, baseline_df: pd.DataFrame, current_df: pd.DataFrame
    ) -> List[ColumnDriftResult]:
        """检测数值列分布漂移 (KS Test)."""
        results: List[ColumnDriftResult] = []
        common_cols = set(baseline_df.columns) & set(current_df.columns)

        for col in common_cols:
            if not pd.api.types.is_numeric_dtype(baseline_df[col]):
                continue

            b_data = baseline_df[col].dropna().values
            c_data = current_df[col].dropna().values

            if len(b_data) < 10 or len(c_data) < 10:
                continue

            try:
                ks_stat, ks_pvalue = stats.ks_2samp(b_data, c_data)
            except Exception:
                continue

            severity = self._ks_severity(ks_stat)
            if severity != DriftSeverity.NONE:
                results.append(
                    ColumnDriftResult(
                        column_name=col,
                        drift_type=DriftType.DISTRIBUTION,
                        severity=severity,
                        statistic_name="KS",
                        statistic_value=round(float(ks_stat), 4),
                        threshold=self.KS_THRESHOLD["low"],
                        description=f"KS={ks_stat:.4f}, p={ks_pvalue:.4f}",
                    )
                )

        return results

    def _detect_null_drift(
        self,
        baseline_profile: Any,
        current_profile: Any,
    ) -> List[ColumnDriftResult]:
        """检测空值率漂移."""
        results: List[ColumnDriftResult] = []
        baseline_map = {c.column_name: c.null_rate for c in baseline_profile.columns}
        current_map = {c.column_name: c.null_rate for c in current_profile.columns}

        for col in set(baseline_map.keys()) & set(current_map.keys()):
            change = abs(current_map[col] - baseline_map[col])
            severity = self._null_change_severity(change)

            if severity != DriftSeverity.NONE:
                results.append(
                    ColumnDriftResult(
                        column_name=col,
                        drift_type=DriftType.NULL,
                        severity=severity,
                        statistic_name="null_rate_change",
                        statistic_value=round(change, 4),
                        baseline_value=round(baseline_map[col], 4),
                        current_value=round(current_map[col], 4),
                        description=f"空值率: {baseline_map[col]:.2%} → {current_map[col]:.2%} (Δ={change:.2%})",
                    )
                )

        return results

    def _detect_category_drift(
        self, baseline_df: pd.DataFrame, current_df: pd.DataFrame
    ) -> List[ColumnDriftResult]:
        """检测分类列分布漂移 (PSI)."""
        results: List[ColumnDriftResult] = []
        common_cols = set(baseline_df.columns) & set(current_df.columns)

        for col in common_cols:
            if pd.api.types.is_numeric_dtype(baseline_df[col]):
                continue

            b_counts = baseline_df[col].value_counts(normalize=True)
            c_counts = current_df[col].value_counts(normalize=True)

            # PSI 计算
            all_cats = set(b_counts.index) | set(c_counts.index)
            if len(all_cats) > 50:  # 高基数跳过
                continue

            psi = 0.0
            for cat in all_cats:
                b_p = b_counts.get(cat, 0.001)  # 平滑处理
                c_p = c_counts.get(cat, 0.001)
                psi += (c_p - b_p) * np.log(c_p / b_p)

            severity = self._psi_severity(abs(psi))
            if severity != DriftSeverity.NONE:
                new_cats = set(c_counts.index) - set(b_counts.index)
                missing_cats = set(b_counts.index) - set(c_counts.index)
                desc = f"PSI={psi:.4f}"
                if new_cats:
                    desc += f", 新增类别: {new_cats}"
                if missing_cats:
                    desc += f", 消失类别: {missing_cats}"

                results.append(
                    ColumnDriftResult(
                        column_name=col,
                        drift_type=DriftType.CATEGORY,
                        severity=severity,
                        statistic_name="PSI",
                        statistic_value=round(abs(psi), 4),
                        threshold=self.PSI_THRESHOLD["low"],
                        description=desc,
                    )
                )

        return results

    def _ks_severity(self, ks_stat: float) -> DriftSeverity:
        if ks_stat >= self.KS_THRESHOLD["high"]:
            return DriftSeverity.CRITICAL
        elif ks_stat >= self.KS_THRESHOLD["medium"]:
            return DriftSeverity.HIGH
        elif ks_stat >= self.KS_THRESHOLD["low"]:
            return DriftSeverity.MEDIUM
        return DriftSeverity.LOW

    def _psi_severity(self, psi: float) -> DriftSeverity:
        if psi >= self.PSI_THRESHOLD["high"]:
            return DriftSeverity.CRITICAL
        elif psi >= self.PSI_THRESHOLD["medium"]:
            return DriftSeverity.HIGH
        elif psi >= self.PSI_THRESHOLD["low"]:
            return DriftSeverity.MEDIUM
        return DriftSeverity.LOW

    def _null_change_severity(self, change: float) -> DriftSeverity:
        if change >= self.NULL_CHANGE_THRESHOLD["high"]:
            return DriftSeverity.CRITICAL
        elif change >= self.NULL_CHANGE_THRESHOLD["medium"]:
            return DriftSeverity.HIGH
        elif change >= self.NULL_CHANGE_THRESHOLD["low"]:
            return DriftSeverity.MEDIUM
        return DriftSeverity.LOW

    def _compute_overall_severity(
        self, drifts: List[ColumnDriftResult]
    ) -> DriftSeverity:
        """计算整体漂移严重程度."""
        severity_order = [
            DriftSeverity.NONE,
            DriftSeverity.LOW,
            DriftSeverity.MEDIUM,
            DriftSeverity.HIGH,
            DriftSeverity.CRITICAL,
        ]
        max_sev = DriftSeverity.NONE
        for d in drifts:
            if severity_order.index(d.severity) > severity_order.index(max_sev):
                max_sev = d.severity
        return max_sev

    def generate_html_report(self, report: DriftReport, output_path: str) -> str:
        """生成漂移检测 HTML 报告."""
        severity_colors = {
            "none": "#27ae60",
            "low": "#2ecc71",
            "medium": "#f39c12",
            "high": "#e74c3c",
            "critical": "#c0392b",
        }

        def _drift_rows(drifts: List[ColumnDriftResult]) -> str:
            rows = ""
            for d in drifts:
                color = severity_colors.get(d.severity.value, "#95a5a6")
                rows += f"""
                <tr>
                    <td>{d.column_name}</td>
                    <td style="color:{color};font-weight:bold">{d.severity.value.upper()}</td>
                    <td>{d.statistic_name}</td>
                    <td>{d.statistic_value:.4f}</td>
                    <td>{d.description}</td>
                </tr>"""
            return rows

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>DQEngine 数据漂移报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
        .header {{ text-align: center; margin-bottom: 2rem; }}
        .header h1 {{ color: #38bdf8; font-size: 2rem; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }}
        .card h2 {{ color: #38bdf8; margin-bottom: 1rem; border-bottom: 2px solid #334155; padding-bottom: 0.5rem; }}
        .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2rem; }}
        .summary-item {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; text-align: center; }}
        .summary-item .value {{ font-size: 2rem; font-weight: bold; color: #38bdf8; }}
        .summary-item .label {{ color: #94a3b8; font-size: 0.85rem; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ color: #94a3b8; font-weight: 600; }}
        tr:hover {{ background: #334155; }}
        .severity-{report.overall_severity.value} {{ color: {severity_colors.get(report.overall_severity.value, '#95a5a6')}; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>DQEngine 数据漂移检测报告</h1>
        <p>{report.baseline_file} → {report.current_file}</p>
    </div>
    <div class="summary">
        <div class="summary-item">
            <div class="value">{report.total_columns}</div>
            <div class="label">总列数</div>
        </div>
        <div class="summary-item">
            <div class="value">{report.drifted_columns}</div>
            <div class="label">漂移列数</div>
        </div>
        <div class="summary-item">
            <div class="value severity-{report.overall_severity.value}">{report.overall_severity.value.upper()}</div>
            <div class="label">整体严重度</div>
        </div>
        <div class="summary-item">
            <div class="value">{report.detected_at[:19]}</div>
            <div class="label">检测时间</div>
        </div>
    </div>
"""

        sections = [
            ("Schema 漂移", report.schema_drift),
            ("分布漂移 (KS Test)", report.distribution_drift),
            ("空值率漂移", report.null_drift),
            ("分类漂移 (PSI)", report.category_drift),
        ]

        for title, drifts in sections:
            if drifts:
                html += f"""
    <div class="card">
        <h2>{title} ({len(drifts)})</h2>
        <table>
            <tr><th>列名</th><th>严重度</th><th>统计量</th><th>统计值</th><th>描述</th></tr>
            {_drift_rows(drifts)}
        </table>
    </div>"""

        html += """
</body>
</html>"""

        path = Path(output_path)
        path.write_text(html, encoding="utf-8")
        return str(path)

    def save_summary_json(self, report: DriftReport, output_path: str) -> str:
        """保存漂移摘要 JSON."""
        path = Path(output_path)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return str(path)
