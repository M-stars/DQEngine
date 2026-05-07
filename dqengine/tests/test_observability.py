"""可观测性模块测试."""

import tempfile
from pathlib import Path

import pytest

from dqengine.models.schemas import MetricType
from dqengine.observability.telemetry import TelemetryManager


class TestTelemetryManager:
    """可观测性管理器测试."""

    @pytest.fixture
    def tm(self):
        import tempfile
        db_fd, db_path = tempfile.mkstemp(suffix=".db")
        tm = TelemetryManager(db_path=db_path)
        yield tm
        tm.close() if hasattr(tm, 'close') else None
        import time
        time.sleep(0.1)
        try:
            Path(db_path).unlink(missing_ok=True)
        except PermissionError:
            pass

    def test_increment_counter(self, tm):
        tm.increment("profiles_created")
        assert tm.get_metric("profiles_created").value == 1

        tm.increment("profiles_created", 5)
        assert tm.get_metric("profiles_created").value == 6

    def test_gauge(self, tm):
        tm.gauge("active_tasks", 3)
        assert tm.get_metric("active_tasks").value == 3
        assert tm.get_metric("active_tasks").metric_type == MetricType.GAUGE

    def test_histogram(self, tm):
        tm.histogram("response_time", 150.5)
        assert tm.get_metric("response_time").value == 150.5

    def test_timer(self, tm):
        tm.timer("clean_duration", 250.0)
        metric = tm.get_metric("clean_duration")
        assert metric.value == 250.0
        assert metric.metric_type == MetricType.TIMER

    def test_trace_context_manager(self, tm):
        with tm.trace("test_operation", {"key": "value"}) as trace:
            assert trace.operation == "test_operation"
            assert trace.metadata == {"key": "value"}

        assert len(tm.traces) == 1
        assert tm.traces[0].success
        assert tm.traces[0].duration_ms >= 0

    def test_trace_exception_capture(self, tm):
        with pytest.raises(ValueError):
            with tm.trace("failing_operation"):
                raise ValueError("test error")

        assert len(tm.traces) == 1
        assert not tm.traces[0].success

    def test_rule_execution_stats(self, tm):
        tm.record_rule_execution("age_range", True, 0, 12.5)
        tm.record_rule_execution("age_range", False, 1, 15.0)
        tm.record_rule_execution("age_range", True, 0, 10.0)

        stats = tm.rule_stats["age_range"]
        assert stats.total_executions == 3
        assert stats.passed == 2
        assert stats.failed == 1
        assert stats.pass_rate == 2 / 3

    def test_generate_report(self, tm):
        tm.increment("test_counter", 10)
        with tm.trace("test_op"):
            pass

        report = tm.generate_report()
        assert len(report.metrics) == 1
        assert len(report.traces) == 1

    def test_save_metrics(self, tm):
        tm.increment("test_metric", 5)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            output = tm.save_metrics(tmp.name)

        try:
            assert Path(output).exists()
            import json

            data = json.loads(Path(output).read_text(encoding="utf-8"))
            assert "metrics" in data
        finally:
            Path(output).unlink(missing_ok=True)

    def test_export_prometheus(self, tm):
        tm.increment("profiles_total", 42)
        prom_output = tm.export_prometheus()
        assert "dqengine_profiles_total 42.0" in prom_output
        assert "\n" in prom_output

    def test_execution_stats(self, tm):
        with tm.trace("op1"):
            pass
        with tm.trace("op2"):
            pass

        stats = tm.get_execution_stats()
        assert stats["total_executions"] == 2
        assert stats["successful"] == 2
        assert stats["success_rate"] == 1.0

    def test_query_executions(self, tm):
        with tm.trace("op_a"):
            pass
        with tm.trace("op_b"):
            pass

        results = tm.query_executions(limit=5)
        assert len(results) <= 5
        assert len(results) >= 2
