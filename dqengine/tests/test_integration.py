"""集成测试 - 端到端数据治理流程."""

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.repair.missing_value import MissingValueCleaner
from dqengine.repair.duplicate import DuplicateCleaner
from dqengine.repair.date_standardizer import DateStandardizer
from dqengine.repair.outlier import OutlierDetector
from dqengine.rules.validator import RuleValidator
from dqengine.semantic import SemanticDetector
from dqengine.pipeline import PipelineGenerator
from dqengine.batch import BatchProcessor
from dqengine.services.orchestrator import CleaningOrchestrator
from dqengine.models.schemas import (
    AppConfig,
    ProfileResult,
    QualityScore,
    RepairResult,
)


class TestIntegrationFullPipeline:
    """端到端全流程集成测试."""

    @pytest.fixture
    def sample_df(self):
        """创建包含各种问题的样本数据."""
        return pd.DataFrame({
            "name": ["Alice", "Bob", "Alice", None, "Charlie"],
            "age": [30, 25, 30, None, 35],
            "email": [
                "alice@test.com",
                "bob@test.com",
                "alice@test.com",
                None,
                "charlie@test.com",
            ],
            "salary": [50000, 60000, 50000, 45000, 9999999],
            "join_date": [
                "2024-01-15",
                "2024-02-20",
                "2024-01-15",
                "2024-03-10",
                "2024-04-05",
            ],
        })

    def test_full_cleaning_pipeline(self, sample_df):
        """测试完整清洗流程."""
        original_rows = len(sample_df)

        # 重复值
        dup = DuplicateCleaner()
        df, dup_result = dup.clean(sample_df)
        assert dup_result.operation == "duplicate_removal"

        # 缺失值
        mv = MissingValueCleaner()
        df, mv_result = mv.clean(df)
        assert mv_result.operation == "missing_value_fill"
        assert df["name"].isna().sum() == 0
        assert df["age"].isna().sum() == 0

        # 日期标准化
        date_std = DateStandardizer()
        df, date_result = date_std.standardize(df)
        assert date_result.operation == "date_standardization"

        # 异常值检测
        outlier_det = OutlierDetector()
        outliers = outlier_det.detect(df)
        assert len(outliers) > 0  # salary有极端异常值

        # 评分
        profiler = Profiler()
        profile = profiler.profile(df)
        scorer = QualityScorer()
        score = scorer.score(df, profile)
        assert score.overall_score > 0
        assert score.grade in ("A", "B", "C", "D", "F")

    def test_semantic_then_cleaning(self, sample_df):
        """测试先语义识别, 再清洗."""
        detector = SemanticDetector()
        result = detector.detect(sample_df)
        assert result.total_columns == len(sample_df.columns)

        # 清洗仍然正常工作
        dup = DuplicateCleaner()
        df, _ = dup.clean(sample_df)
        assert len(df) <= len(sample_df)


class TestOrchestratorIntegration:
    """编排器集成测试."""

    @pytest.fixture
    def temp_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,age,email\nAlice,30,alice@test.com\nBob,25,bob@test.com\nBob,25,bob@test.com\n")
            csv_path = f.name

        yield csv_path
        os.unlink(csv_path)

    def test_orchestrator_run(self, temp_csv):
        """测试编排器运行."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as out_f:
            out_path = out_f.name
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as rpt_f:
            report_path = rpt_f.name

        try:
            orchestrator = CleaningOrchestrator()
            result = orchestrator.run(
                file_path=temp_csv,
                output_path=out_path,
                report_path=report_path,
            )

            assert result["rows_before"] == 3
            assert result["rows_after"] <= 3
            assert result["score_before"] is not None
            assert result["score_after"] is not None
            assert Path(out_path).exists()
            assert Path(report_path).exists()
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)
            if os.path.exists(report_path):
                os.unlink(report_path)


class TestPipelineGeneratorIntegration:
    """Pipeline生成器集成测试."""

    @pytest.fixture
    def temp_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,age,email,join_date\nAlice,30,alice@test.com,2024-01-15\nBob,25,,2024-02-20\n")
            csv_path = f.name

        yield csv_path
        os.unlink(csv_path)

    def test_generate_pipeline(self, temp_csv):
        """测试生成Pipeline."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as out_f:
            out_path = out_f.name

        try:
            generator = PipelineGenerator()
            result_path = generator.generate(temp_csv, out_path)

            assert Path(result_path).exists()
            code = Path(result_path).read_text(encoding="utf-8")
            assert "def load_data" in code
            assert "def run_pipeline" in code
            assert "import pandas" in code
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)
