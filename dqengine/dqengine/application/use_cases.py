"""Application 用例层 - 业务用例编排."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.domain.entities import AnomalyReport, RiskAssessment, RiskLevel
from dqengine.drift.detector import DriftDetector
from dqengine.models.schemas import AIRuleSet, DriftReport, QualityTrend
from dqengine.repair.date_standardizer import DateStandardizer
from dqengine.repair.duplicate import DuplicateCleaner
from dqengine.repair.missing_value import MissingValueCleaner
from dqengine.repair.outlier import OutlierDetector


class AutoCleanUseCase:
    """自动清洗用例."""

    def __init__(self) -> None:
        self.loader = DataLoader()
        self.profiler = Profiler()
        self.scorer = QualityScorer()

    def execute(self, file_path: str) -> Dict[str, Any]:
        df = self.loader.load(Path(file_path))
        rows_before = len(df)
        profile_before = self.profiler.profile(df)
        score_before = self.scorer.score(df, profile_before)

        df, r1 = MissingValueCleaner().clean(df)
        df, r2 = DuplicateCleaner().clean(df)
        df, r3 = DateStandardizer().standardize(df)
        outliers = OutlierDetector().detect(df)

        profile_after = self.profiler.profile(df)
        score_after = self.scorer.score(df, profile_after)

        return {
            "rows_before": rows_before,
            "rows_after": len(df),
            "score_before": score_before,
            "score_after": score_after,
            "repairs": [r1, r2, r3],
            "outliers": len(outliers),
            "dataframe": df,
        }


class DriftDetectionUseCase:
    """漂移检测用例."""

    def __init__(self) -> None:
        self.detector = DriftDetector()

    def execute(self, baseline_path: str, current_path: str) -> DriftReport:
        return self.detector.detect(baseline_path, current_path)


class QualityMonitorUseCase:
    """质量监控用例."""

    def __init__(self) -> None:
        self.loader = DataLoader()
        self.profiler = Profiler()
        self.scorer = QualityScorer()

    def execute_single(self, file_path: str) -> QualityTrend:
        df = self.loader.load(Path(file_path))
        profile = self.profiler.profile(df, file_path=file_path)
        score = self.scorer.score(df, profile)
        null_rates = [c.null_rate for c in profile.columns]

        from datetime import datetime

        return QualityTrend(
            timestamp=datetime.now().isoformat(),
            file_name=Path(file_path).name,
            overall_score=score.overall_score,
            row_count=profile.row_count,
            null_rate=sum(null_rates) / max(len(null_rates), 1),
            duplicate_rate=profile.duplicate_row_rate,
        )

    def assess_risk(self, df: pd.DataFrame, profile: Any, score: Any) -> RiskAssessment:
        """评估数据质量风险."""
        assessment = RiskAssessment(dataset_id="temp")

        # 空值风险
        high_null_cols = [c for c in profile.columns if c.null_rate > 0.3]
        if high_null_cols:
            assessment.add_factor(
                "high_null_rate",
                RiskLevel.HIGH,
                f"以下字段空值率>30%: {', '.join(c.column_name for c in high_null_cols)}",
            )

        # 低评分风险
        if score.overall_score < 50:
            assessment.add_factor("low_quality_score", RiskLevel.CRITICAL, f"综合评分仅 {score.overall_score:.1f}")
        elif score.overall_score < 70:
            assessment.add_factor("medium_quality_score", RiskLevel.MEDIUM, f"综合评分偏低: {score.overall_score:.1f}")

        # 高重复率风险
        if profile.duplicate_row_rate > 0.2:
            assessment.add_factor(
                "high_duplicates",
                RiskLevel.HIGH,
                f"重复行率 {profile.duplicate_row_rate:.1%}",
            )

        if not assessment.factors:
            assessment.add_factor("clean_data", RiskLevel.LOW, "未发现明显数据质量问题")

        return assessment

    def detect_anomalies(self, df: pd.DataFrame, profile: Any) -> AnomalyReport:
        """自动检测数据异常."""
        report = AnomalyReport(id="auto", dataset_id="temp")

        for col_profile in profile.columns:
            col = col_profile.column_name
            series = df[col]

            # 类型冲突检测
            if str(series.dtype) == "object":
                numeric_count = pd.to_numeric(series, errors="coerce").notna().sum()
                total = len(series.dropna())
                if total > 0 and 0.3 < numeric_count / total < 0.7:
                    report.add_pattern(
                        "field_conflict",
                        col,
                        f"字段 '{col}' 同时包含数值和文本 ({numeric_count}/{total} 数值)",
                        "建议检查并统一字段数据类型",
                    )

            # 高缺失字段
            if col_profile.null_rate > 0.5:
                report.add_pattern(
                    "high_null",
                    col,
                    f"字段 '{col}' 空值率 {col_profile.null_rate:.1%}",
                    "建议评估该字段必要性，或进行缺失值填充",
                )

            # 异常值模式
            if col_profile.unique_rate == 1.0 and col_profile.total_count > 100:
                report.add_pattern(
                    "all_unique",
                    col,
                    f"字段 '{col}' 所有值唯一 (可能是ID)",
                    "建议标记为唯一标识字段",
                )

        risk_map = {"field_conflict": RiskLevel.HIGH, "high_null": RiskLevel.MEDIUM, "all_unique": RiskLevel.LOW}
        for p in report.patterns:
            risk = risk_map.get(p["pattern_type"], RiskLevel.LOW)
            if risk.value in ("high", "critical"):
                report.risk_level = RiskLevel.HIGH
                break

        return report


class RuleGenerationUseCase:
    """规则生成用例."""

    def __init__(self) -> None:
        from dqengine.ai.generator import HeuristicRuleGenerator
        self.generator = HeuristicRuleGenerator()

    def execute(self, df: pd.DataFrame) -> AIRuleSet:
        return self.generator.generate(df)
