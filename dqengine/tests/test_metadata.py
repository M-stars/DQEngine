"""元数据与数据血缘测试."""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from dqengine.metadata.lineage import LineageTracker


class TestLineageTracker:
    """血缘追踪器测试."""

    @pytest.fixture
    def tracker(self):
        return LineageTracker()

    def test_start_session(self, tracker):
        dataset_id = tracker.start_session("data.csv")
        assert len(dataset_id) == 8
        lineage = tracker.get_lineage(dataset_id)
        assert lineage is not None
        assert lineage.source_path == "data.csv"

    def test_record_step(self, tracker):
        dataset_id = tracker.start_session("data.csv")
        tracker.record_step(
            dataset_id,
            "load",
            input_data="data.csv",
            output_data="memory",
            operation="csv_load",
        )
        tracker.record_step(
            dataset_id,
            "clean",
            input_data="memory",
            output_data="cleaned",
            operation="remove_duplicates",
        )

        lineage = tracker.get_lineage(dataset_id)
        assert len(lineage.steps) == 2
        assert lineage.steps[0].step_name == "load"
        assert lineage.steps[1].step_name == "clean"

    def test_record_schema(self, tracker):
        dataset_id = tracker.start_session("data.csv")
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        tracker.record_schema(dataset_id, df)

        lineage = tracker.get_lineage(dataset_id)
        assert lineage.current_schema is not None
        assert "a" in lineage.current_schema
        assert "b" in lineage.current_schema

    def test_record_execution(self, tracker):
        tracker.record_execution("age_range", "data.csv", True, 0, 12.5)
        tracker.record_execution("email_regex", "data.csv", False, 3, 8.2)

        history = tracker.get_execution_history()
        assert len(history) == 2

    def test_get_execution_history_filtered(self, tracker):
        tracker.record_execution("rule_a", "f1.csv", True, 0, 5.0)
        tracker.record_execution("rule_b", "f2.csv", True, 0, 10.0)
        tracker.record_execution("rule_a", "f3.csv", False, 2, 7.0)

        history = tracker.get_execution_history(rule_name="rule_a")
        assert len(history) == 2
        assert all(r.rule_name == "rule_a" for r in history)

    def test_save_and_load(self, tracker):
        dataset_id = tracker.start_session("data.csv")
        tracker.record_step(dataset_id, "load", operation="csv")
        tracker.record_execution("test_rule", "data.csv", True, 0, 10.0)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            output_path = tracker.save(tmp.name)

        try:
            tracker2 = LineageTracker()
            tracker2.load(output_path)
            assert tracker2.get_lineage(dataset_id) is not None
            assert len(tracker2.get_execution_history()) == 1
        finally:
            Path(output_path).unlink(missing_ok=True)

    def test_lineage_graph_generation(self, tracker):
        dataset_id = tracker.start_session("data.csv")
        tracker.record_step(dataset_id, "load", operation="csv")
        tracker.record_step(dataset_id, "clean", operation="dedup")
        tracker.record_step(dataset_id, "export", operation="csv")

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
            output = tracker.generate_lineage_graph(dataset_id, tmp.name)

        try:
            assert Path(output).exists()
            content = Path(output).read_text(encoding="utf-8")
            assert "vis.Network" in content or "vis-network" in content
        finally:
            Path(output).unlink(missing_ok=True)

    def test_unknown_dataset_raises_error(self, tracker):
        with pytest.raises(ValueError, match="未知数据集"):
            tracker.record_step("nonexistent", "test")
