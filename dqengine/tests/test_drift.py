"""数据漂移检测测试."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dqengine.drift.detector import DriftDetector
from dqengine.models.schemas import DriftSeverity


class TestDriftDetector:
    """漂移检测器测试."""

    @pytest.fixture
    def detector(self):
        return DriftDetector()

    @pytest.fixture
    def baseline_df(self):
        np.random.seed(42)
        return pd.DataFrame({
            "age": np.random.normal(35, 10, 100).astype(int),
            "salary": np.random.normal(50000, 15000, 100),
            "dept": np.random.choice(["A", "B", "C"], 100),
            "score": np.random.uniform(60, 100, 100),
        })

    @pytest.fixture
    def current_similar_df(self):
        np.random.seed(99)
        return pd.DataFrame({
            "age": np.random.normal(36, 11, 100).astype(int),
            "salary": np.random.normal(51000, 16000, 100),
            "dept": np.random.choice(["A", "B", "C"], 100),
            "score": np.random.uniform(58, 98, 100),
        })

    def _save_temp_csv(self, df: pd.DataFrame, suffix: str = "") -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        df.to_csv(tmp.name, index=False)
        return tmp.name

    def test_detect_no_significant_drift(self, detector, baseline_df, current_similar_df):
        b_path = self._save_temp_csv(baseline_df)
        c_path = self._save_temp_csv(current_similar_df)

        try:
            report = detector.detect(b_path, c_path)
            assert report.total_columns >= 1
            assert report.overall_severity in DriftSeverity.__members__.values()
        finally:
            Path(b_path).unlink(missing_ok=True)
            Path(c_path).unlink(missing_ok=True)

    def test_schema_drift_new_column(self, detector, baseline_df):
        b_path = self._save_temp_csv(baseline_df)
        current = baseline_df.copy()
        current["new_col"] = 1
        c_path = self._save_temp_csv(current)

        try:
            report = detector.detect(b_path, c_path)
            schema_drifts = report.schema_drift
            new_col_drifts = [d for d in schema_drifts if d.column_name == "new_col"]
            assert len(new_col_drifts) > 0
        finally:
            Path(b_path).unlink(missing_ok=True)
            Path(c_path).unlink(missing_ok=True)

    def test_schema_drift_removed_column(self, detector, baseline_df):
        b_path = self._save_temp_csv(baseline_df)
        current = baseline_df.drop(columns=["age"])
        c_path = self._save_temp_csv(current)

        try:
            report = detector.detect(b_path, c_path)
            removed_drifts = [d for d in report.schema_drift if d.column_name == "age"]
            assert len(removed_drifts) > 0
        finally:
            Path(b_path).unlink(missing_ok=True)
            Path(c_path).unlink(missing_ok=True)

    def test_null_drift_detected(self, detector):
        baseline = pd.DataFrame({"a": [1, 2, 3, 4, 5], "b": [10, 20, 30, 40, 50]})
        current = pd.DataFrame({"a": [1, np.nan, np.nan, np.nan, 5], "b": [10, 20, 30, 40, 50]})
        b_path = self._save_temp_csv(baseline)
        c_path = self._save_temp_csv(current)

        try:
            report = detector.detect(b_path, c_path)
            null_drifts = [d for d in report.null_drift if d.column_name == "a"]
            assert len(null_drifts) > 0
        finally:
            Path(b_path).unlink(missing_ok=True)
            Path(c_path).unlink(missing_ok=True)

    def test_distribution_drift(self, detector):
        np.random.seed(1)
        baseline = pd.DataFrame({"x": np.random.normal(0, 1, 200)})
        current = pd.DataFrame({"x": np.random.normal(3, 2, 200)})
        b_path = self._save_temp_csv(baseline)
        c_path = self._save_temp_csv(current)

        try:
            report = detector.detect(b_path, c_path)
            dist_drifts = [d for d in report.distribution_drift if d.column_name == "x"]
            assert len(dist_drifts) > 0
        finally:
            Path(b_path).unlink(missing_ok=True)
            Path(c_path).unlink(missing_ok=True)

    def test_html_report_generation(self, detector, baseline_df, current_similar_df):
        b_path = self._save_temp_csv(baseline_df)
        c_path = self._save_temp_csv(current_similar_df)
        report = detector.detect(b_path, c_path)

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
            output_path = detector.generate_html_report(report, tmp.name)

        try:
            assert Path(output_path).exists()
            content = Path(output_path).read_text(encoding="utf-8")
            assert "<html" in content.lower() or "<!DOCTYPE html>" in content
        finally:
            Path(b_path).unlink(missing_ok=True)
            Path(c_path).unlink(missing_ok=True)
            Path(output_path).unlink(missing_ok=True)

    def test_summary_json(self, detector, baseline_df, current_similar_df):
        b_path = self._save_temp_csv(baseline_df)
        c_path = self._save_temp_csv(current_similar_df)
        report = detector.detect(b_path, c_path)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            output_path = detector.save_summary_json(report, tmp.name)

        try:
            assert Path(output_path).exists()
            import json
            data = json.loads(Path(output_path).read_text(encoding="utf-8"))
            assert "baseline_file" in data
        finally:
            Path(b_path).unlink(missing_ok=True)
            Path(c_path).unlink(missing_ok=True)
            Path(output_path).unlink(missing_ok=True)
