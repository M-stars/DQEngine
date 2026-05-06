"""Tests for the Profiler and QualityScorer modules."""

from __future__ import annotations

import pandas as pd
import pytest

from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer


class TestProfiler:
    def test_basic_profile(self) -> None:
        """Profile a simple DataFrame."""
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        profiler = Profiler()
        result = profiler.profile(df)

        assert result.row_count == 3
        assert result.column_count == 2
        assert result.total_cells == 6
        assert len(result.columns) == 2

    def test_null_rate(self) -> None:
        """Correctly compute null rates."""
        df = pd.DataFrame({"a": [1, None, 3], "b": ["x", None, None]})
        profiler = Profiler()
        result = profiler.profile(df)

        col_a = next(c for c in result.columns if c.column_name == "a")
        col_b = next(c for c in result.columns if c.column_name == "b")
        assert col_a.null_rate == pytest.approx(1 / 3, 0.01)
        assert col_b.null_rate == pytest.approx(2 / 3, 0.01)

    def test_duplicate_detection(self) -> None:
        """Detect duplicate rows."""
        df = pd.DataFrame({"a": [1, 1, 2], "b": [3, 3, 4]})
        profiler = Profiler()
        result = profiler.profile(df)

        assert result.duplicate_row_count == 1
        assert result.duplicate_row_rate == pytest.approx(1 / 3, 0.01)

    def test_numeric_stats(self) -> None:
        """Include numeric statistics for numeric columns."""
        df = pd.DataFrame({"x": [1, 2, 3, 4, 5]})
        profiler = Profiler()
        result = profiler.profile(df)

        col = result.columns[0]
        assert col.mean == pytest.approx(3.0)
        assert col.min_val == pytest.approx(1.0)
        assert col.max_val == pytest.approx(5.0)

    def test_non_numeric_stats(self) -> None:
        """Omit numeric stats for non-numeric columns."""
        df = pd.DataFrame({"name": ["Alice", "Bob"]})
        profiler = Profiler()
        result = profiler.profile(df)

        col = result.columns[0]
        assert col.mean is None
        assert col.min_val is None

    def test_empty_dataframe(self) -> None:
        """Handle empty DataFrame gracefully."""
        df = pd.DataFrame()
        profiler = Profiler()
        result = profiler.profile(df)

        assert result.row_count == 0
        assert result.column_count == 0


class TestQualityScorer:
    def test_perfect_score(self) -> None:
        """Perfect data should score 100."""
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        profiler = Profiler()
        profile = profiler.profile(df)
        scorer = QualityScorer()
        score = scorer.score(df, profile)

        assert score.overall_score == pytest.approx(100.0, 0.1)
        assert score.grade == "A"

    def test_null_penalty(self) -> None:
        """High null rate should lower the score."""
        df = pd.DataFrame({"a": [1, None, None, None, None]})
        profiler = Profiler()
        profile = profiler.profile(df)
        scorer = QualityScorer()
        score = scorer.score(df, profile)

        assert score.overall_score < 80

    def test_grade_boundaries(self) -> None:
        """Verify grade boundaries."""
        scorer = QualityScorer()
        assert scorer._grade(95) == "A"
        assert scorer._grade(80) == "B"
        assert scorer._grade(65) == "C"
        assert scorer._grade(50) == "D"
        assert scorer._grade(30) == "F"
