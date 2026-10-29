"""生产化特性测试: API 鉴权/指标、Webhook、违规隔离、CI 门禁、调度器持久化."""

import json
import time
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from dqengine.cli.commands import app as cli_app

runner = CliRunner()


@pytest.fixture
def sample_csv(tmp_path):
    df = pd.DataFrame({"age": [-5, 30, 999], "name": ["a", "b", "c"]})
    path = tmp_path / "d.csv"
    df.to_csv(path, index=False)
    return path


@pytest.fixture
def rules_yaml(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(
        "columns:\n  age:\n    min: 0\n    max: 100\n    not_null: true\n",
        encoding="utf-8",
    )
    return path


# ---- API Key 鉴权 + /metrics ----


class TestApiAuth:
    def test_open_mode_when_no_key(self, monkeypatch, sample_csv):
        monkeypatch.delenv("DQENGINE_API_KEY", raising=False)
        from fastapi.testclient import TestClient
        from dqengine.api.server import create_app

        client = TestClient(create_app())
        assert client.get("/health").status_code == 200
        with open(sample_csv, "rb") as f:
            # 未配置 key 时数据端点保持开放
            assert client.post("/profile", files={"file": ("d.csv", f)}).status_code == 200

    def test_key_auth_enforced(self, monkeypatch, sample_csv):
        monkeypatch.setenv("DQENGINE_API_KEY", "secret123")
        from fastapi.testclient import TestClient
        from dqengine.api.server import create_app

        client = TestClient(create_app())
        assert client.get("/health").status_code == 200
        assert client.get("/metrics").status_code == 200
        with open(sample_csv, "rb") as f:
            assert client.post("/profile", files={"file": ("d.csv", f)}).status_code == 401
        with open(sample_csv, "rb") as f:
            ok = client.post(
                "/profile", files={"file": ("d.csv", f)}, headers={"X-API-Key": "secret123"}
            )
        assert ok.status_code == 200

    def test_metrics_builtin_series(self, monkeypatch):
        monkeypatch.delenv("DQENGINE_API_KEY", raising=False)
        from fastapi.testclient import TestClient
        from dqengine.api.server import create_app

        client = TestClient(create_app())
        text = client.get("/metrics").text
        assert "dqengine_uptime_seconds" in text
        assert "dqengine_traces_total" in text


# ---- 告警 Webhook ----


class TestWebhook:
    def test_alert_delivery(self, tmp_path, monkeypatch):
        import dqengine.monitoring.monitor as mon_mod

        captured = []

        class FakeResp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class FakeUrlRequest:
            @staticmethod
            def Request(url, data=None, headers=None, method=None):
                class R:
                    pass
                R.data = data
                return R

            @staticmethod
            def urlopen(req, timeout=None):
                captured.append(json.loads(req.data))
                return FakeResp()

        monkeypatch.setattr(mon_mod, "_url_request", FakeUrlRequest)
        from dqengine.monitoring.monitor import QualityMonitor

        incoming = tmp_path / "in"
        incoming.mkdir()
        pd.DataFrame({"a": [None] * 8 + [1, 2]}).to_csv(incoming / "bad.csv", index=False)
        m = QualityMonitor(
            watch_directory=str(incoming),
            trends_file=str(tmp_path / "t.json"),
            webhook_url="http://example/hook",
        )
        m.scan_directory()
        assert m.session.alerts, "应产生低质量告警"
        assert captured and captured[0]["text"] == m.session.alerts[0]

    def test_webhook_failure_does_not_interrupt(self, tmp_path, monkeypatch):
        import dqengine.monitoring.monitor as mon_mod

        class FailingUrlRequest:
            @staticmethod
            def urlopen(req, timeout=None):
                raise OSError("connection refused")

        monkeypatch.setattr(mon_mod, "_url_request", FailingUrlRequest)
        from dqengine.monitoring.monitor import QualityMonitor

        incoming = tmp_path / "in"
        incoming.mkdir()
        pd.DataFrame({"a": [None] * 8 + [1, 2]}).to_csv(incoming / "bad.csv", index=False)
        m = QualityMonitor(
            watch_directory=str(incoming),
            trends_file=str(tmp_path / "t.json"),
            webhook_url="http://127.0.0.1:1/hook",
        )
        events = m.scan_directory()
        assert len(events) == 1 and m.session.alerts


# ---- 违规隔离 + CI 门禁 ----


class TestValidateGates:
    def test_quarantine_output(self, tmp_path, sample_csv, rules_yaml):
        q_path = tmp_path / "q" / "quarantine.csv"
        result = runner.invoke(
            cli_app,
            ["validate", str(sample_csv), "--rules", str(rules_yaml), "--quarantine", str(q_path)],
        )
        assert result.exit_code == 1
        q = pd.read_csv(q_path)
        assert len(q) == 2
        assert "dqengine_violations" in q.columns

    def test_json_output_pure(self, tmp_path, sample_csv, rules_yaml):
        result = runner.invoke(
            cli_app, ["validate", str(sample_csv), "--rules", str(rules_yaml), "--json"]
        )
        assert result.exit_code == 1
        body = json.loads(result.stdout)
        assert body["passed"] is False
        assert body["total_violations"] >= 2

    def test_pass_exit_code_zero(self, tmp_path, rules_yaml):
        ok = tmp_path / "ok.csv"
        pd.DataFrame({"age": [10, 20], "name": ["a", "b"]}).to_csv(ok, index=False)
        result = runner.invoke(
            cli_app, ["validate", str(ok), "--rules", str(rules_yaml), "--json"]
        )
        assert result.exit_code == 0
        assert json.loads(result.stdout)["passed"] is True

    def test_auto_fail_below_score(self, tmp_path):
        bad = tmp_path / "bad.csv"
        pd.DataFrame({"v": [None] * 9 + [1.0]}).to_csv(bad, index=False)
        result = runner.invoke(
            cli_app,
            [
                "auto", str(bad),
                "-o", str(tmp_path / "o.csv"),
                "-r", str(tmp_path / "r.html"),
                "--fail-below-score", "99",
            ],
        )
        assert result.exit_code == 2
        assert "质量门禁未通过" in result.stdout


# ---- 调度器状态持久化 ----


class TestSchedulerState:
    def test_persistence_prevents_rerun_on_restart(self, tmp_path):
        import dqengine.scheduler.scheduler as sched_mod
        from dqengine.models.schemas import ScheduleType, ScheduledTask
        from dqengine.scheduler.scheduler import TaskScheduler

        state = tmp_path / "state.json"
        data = tmp_path / "data.csv"
        pd.DataFrame({"a": [1, 2]}).to_csv(data, index=False)

        s1 = TaskScheduler(state_file=str(state))
        s1.add_task(
            ScheduledTask(
                task_id="c1", name="daily", schedule_type=ScheduleType.CRON,
                schedule_value="0 3 * * *", action="profile", target_path=str(data),
            )
        )
        s1.tasks["c1"].next_run = "2030-01-01T03:00:00"
        s1.save_state()

        s2 = TaskScheduler(state_file=str(state))
        assert s2.load_state() == 1
        assert s2.tasks["c1"].next_run == "2030-01-01T03:00:00"

        # 重启后首次轮询: CRON 的 next_run 在未来, 不应执行
        s2._running = True
        orig_sleep = sched_mod.time.sleep
        sched_mod.time.sleep = lambda sec: (_ for _ in ()).throw(KeyboardInterrupt)
        s2._start_polling()
        sched_mod.time.sleep = orig_sleep
        assert len(s2.get_results()) == 0

    def test_no_state_file_noop(self, tmp_path):
        from dqengine.scheduler.scheduler import TaskScheduler

        s = TaskScheduler()
        assert s.save_state() is None
        assert s.load_state() == 0


# ---- 监控大小写后缀 + 基线缓存 ----


class TestMonitorScan:
    def test_case_insensitive_suffix_and_processing(self, tmp_path):
        from dqengine.monitoring.monitor import QualityMonitor

        incoming = tmp_path / "in"
        incoming.mkdir()
        pd.DataFrame({"a": [1]}).to_csv(incoming / "UP.CSV", index=False)
        m = QualityMonitor(watch_directory=str(incoming), trends_file=str(tmp_path / "t.json"))
        events = m.scan_directory()
        assert len(events) == 1 and events[0].profile is not None
        assert m.session.total_files_processed == 1

    def test_baseline_cache_hit_and_invalidate(self, tmp_path):
        from dqengine.monitoring.monitor import QualityMonitor

        baseline = tmp_path / "base.csv"
        pd.DataFrame({"a": range(100)}).to_csv(baseline, index=False)
        incoming = tmp_path / "in"
        incoming.mkdir()
        m = QualityMonitor(
            watch_directory=str(incoming),
            baseline_file=str(baseline),
            trends_file=str(tmp_path / "t.json"),
        )
        loads = {"n": 0}
        orig_load = m.loader.load

        def counting(p):
            if str(p) == str(baseline):
                loads["n"] += 1
            return orig_load(p)

        m.loader.load = counting
        for name, v in [("d1.csv", 1), ("d2.csv", 2), ("d3.csv", 3)]:
            pd.DataFrame({"a": [v]}).to_csv(incoming / name, index=False)
            m.scan_directory()
        assert loads["n"] == 1, "基线应被缓存"

        time.sleep(0.05)
        pd.DataFrame({"a": range(200)}).to_csv(baseline, index=False)
        pd.DataFrame({"a": [9]}).to_csv(incoming / "d4.csv", index=False)
        m.scan_directory()
        assert loads["n"] == 2, "基线变更后应失效重读"
