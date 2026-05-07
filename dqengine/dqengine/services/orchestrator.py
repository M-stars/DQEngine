"""清洗编排器 - 协调所有清洗步骤的执行."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pandas as pd

from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.models.schemas import (
    AppConfig,
    CleaningConfig,
    OutlierRecord,
    QualityScore,
    RepairResult,
)
from dqengine.repair.date_standardizer import DateStandardizer
from dqengine.repair.duplicate import DuplicateCleaner
from dqengine.repair.missing_value import MissingValueCleaner
from dqengine.repair.outlier import OutlierDetector
from dqengine.report.generator import ReportGenerator
from dqengine.rules.validator import RuleValidator
from dqengine.utils.logger import get_logger

logger = get_logger(__name__)


class CleaningOrchestrator:
    """数据清洗编排器.

    按照配置顺序执行:
        1. 数据加载
        2. 分析画像
        3. 重复值移除
        4. 缺失值填充
        5. 日期标准化
        6. 异常值检测
        7. 规则验证 (可选)
        8. 评分
        9. 报告生成

    使用方式:
        orchestrator = CleaningOrchestrator(config)
        result = orchestrator.run("data.csv")
    """

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        """初始化编排器.

        Args:
            config: AppConfig 配置, 为 None 时使用默认配置.
        """
        self.config = config or AppConfig()
        self.loader = DataLoader()
        self.profiler = Profiler()
        self.scorer = QualityScorer()

        self.dup_cleaner = DuplicateCleaner()
        self.mv_cleaner = MissingValueCleaner()
        self.date_std = DateStandardizer()
        self.outlier_detector = OutlierDetector()
        self.rule_validator = RuleValidator()
        self.report_gen = ReportGenerator()

    def run(
        self,
        file_path: "str | Path",
        output_path: "str | Path" = "cleaned_data.csv",
        report_path: "str | Path" = "report.html",
        rules_path: Optional["str | Path"] = None,
    ) -> dict:
        """执行完整的数据清洗流程.

        Args:
            file_path: 输入文件路径.
            output_path: 清洗后数据输出路径.
            report_path: 报告输出路径.
            rules_path: 可选的验证规则文件路径.

        Returns:
            包含清洗结果的字典.
        """
        path = Path(file_path)
        cleaning = self.config.cleaning

        # Step 1: 数据加载
        logger.info("Step 1: 加载数据 %s", path.name)
        df = self.loader.load(path)
        original_rows = len(df)
        repairs: List[RepairResult] = []

        # Step 2: 清洗前画像
        logger.info("Step 2: 清洗前数据分析")
        profile_before = self.profiler.profile(df, file_path=str(path))
        score_before = self.scorer.score(df, profile_before)
        logger.info("  清洗前质量评分: %.1f (%s)", score_before.overall_score, score_before.grade)

        # Step 3: 重复值移除
        if cleaning.duplicate.enabled:
            logger.info("Step 3: 移除重复行")
            df, dup_result = self.dup_cleaner.clean(df, keep=cleaning.duplicate.keep)
            repairs.append(dup_result)
            logger.info("  已移除 %d 个重复行", dup_result.changes_made)

        # Step 4: 缺失值填充
        if cleaning.missing.enabled:
            logger.info("Step 4: 填充缺失值 (策略: %s)", cleaning.missing.strategy)
            df, mv_result = self.mv_cleaner.clean(df)
            repairs.append(mv_result)
            logger.info("  已填充 %d 个缺失值", mv_result.changes_made)

        # Step 5: 日期标准化
        if cleaning.date.enabled:
            logger.info("Step 5: 日期标准化")
            df, date_result = self.date_std.standardize(df, target_format=cleaning.date.target_format)
            repairs.append(date_result)
            if date_result.columns_affected > 0:
                logger.info("  已标准化 %d 个日期列", date_result.columns_affected)

        # Step 6: 异常值检测
        outliers: List[OutlierRecord] = []
        if cleaning.outlier.action in ("flag", "remove"):
            logger.info("Step 6: 异常值检测 (方法: %s)", cleaning.outlier.method)
            outliers = self.outlier_detector.detect(df)
            if cleaning.outlier.action == "remove" and outliers:
                df = self.outlier_detector.remove_outliers(df, outliers)
                logger.info("  已移除 %d 个异常值行", len(outliers))
            else:
                logger.info("  检测到 %d 个异常值", len(outliers))

        # Step 7: 规则验证 (可选)
        validation_result = None
        if rules_path:
            logger.info("Step 7: 规则验证")
            validation_result = self.rule_validator.validate(df, rules_path)
            logger.info(
                "  结果: %s (%d/%d 通过)",
                "PASSED" if validation_result.passed else "FAILED",
                validation_result.passed_rules,
                validation_result.total_rules,
            )

        # Step 8: 清洗后画像
        logger.info("Step 8: 清洗后数据分析")
        profile_after = self.profiler.profile(df, file_path=str(path))
        score_after = self.scorer.score(df, profile_after)
        logger.info("  清洗后质量评分: %.1f (%s)", score_after.overall_score, score_after.grade)

        # Step 9: 保存清洗数据
        out_path = Path(output_path)
        if out_path.suffix.lower() == ".xlsx":
            df.to_excel(out_path, index=False)
        elif out_path.suffix.lower() == ".parquet":
            df.to_parquet(out_path, index=False)
        elif out_path.suffix.lower() == ".json":
            df.to_json(out_path, orient="records", force_ascii=False)
        else:
            df.to_csv(out_path, index=False, encoding="utf-8")
        logger.info("数据已保存: %s", out_path)

        # Step 10: 生成报告
        logger.info("Step 10: 生成报告")
        report_output = self.report_gen.generate(
            profile=profile_after,
            score=score_after,
            repairs=repairs,
            outliers=outliers,
            output_path=str(report_path),
        )
        logger.info("报告已生成: %s", report_output)

        return {
            "file": str(path),
            "rows_before": original_rows,
            "rows_after": len(df),
            "score_before": score_before,
            "score_after": score_after,
            "repairs": repairs,
            "outliers_count": len(outliers),
            "validation": validation_result,
            "output_file": str(out_path),
            "report_file": str(report_output),
        }
