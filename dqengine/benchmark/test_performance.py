"""性能基准测试."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dqengine.ai.generator import HeuristicRuleGenerator
from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.drift.detector import DriftDetector


@pytest.fixture(scope="module")
def large_df():
    """生成 10000 行的大数据集用于性能测试."""
    np.random.seed(42)
    return pd.DataFrame({
        "id": range(1, 10001),
        "name": [f"user_{i}" for i in range(1, 10001)],
        "age": np.random.randint(18, 80, 10000),
        "email": [f"user_{i}@example.com" for i in range(1, 10001)],
        "salary": np.random.normal(50000, 15000, 10000),
        "dept": np.random.choice(["A", "B", "C", "D", "E"], 10000),
        "score": np.random.uniform(0, 100, 10000),
    })


def _save_temp(df: pd.DataFrame) -> str:
    fd, path = tempfile.mkstemp(suffix=".csv")
    df.to_csv(path, index=False)
    return path


class TestProfilerPerformance:
    """画像性能测试."""

    def test_profile_speed(self, large_df, benchmark):
        profiler = Profiler()
        result = benchmark(lambda: profiler.profile(large_df))
        assert result.column_count == 7
        assert result.row_count == 10000

    def test_scorer_speed(self, large_df, benchmark):
        profiler = Profiler()
        profile = profiler.profile(large_df)
        scorer = QualityScorer()
        result = benchmark(lambda: scorer.score(large_df, profile))
        assert 0 <= result.overall_score <= 100


class TestAIPerformance:
    """AI 规则生成性能测试."""

    def test_rule_generation_speed(self, large_df, benchmark):
        generator = HeuristicRuleGenerator()
        result = benchmark(lambda: generator.generate(large_df))
        total_rules = sum(len(rules) for rules in result.columns.values())
        assert total_rules > 0


class TestDriftPerformance:
    """漂移检测性能测试."""

    def test_drift_detection_speed(self, large_df, benchmark):
        baseline = large_df.copy()
        current = large_df.copy()
        current["age"] = current["age"] + np.random.normal(5, 3, 10000).astype(int)
        current["new_col"] = 1

        b_path = _save_temp(baseline)
        c_path = _save_temp(current)

        try:
            detector = DriftDetector()
            report = benchmark(lambda: detector.detect(b_path, c_path))
            assert report.total_columns >= 7
        finally:
            Path(b_path).unlink(missing_ok=True)
            Path(c_path).unlink(missing_ok=True)


class TestLoaderPerformance:
    """数据加载性能测试."""

    def test_csv_load_speed(self, large_df, benchmark):
        path = _save_temp(large_df)
        try:
            loader = DataLoader()
            df = benchmark(lambda: loader.load(Path(path)))
            assert len(df) == 10000
        finally:
            Path(path).unlink(missing_ok=True)
