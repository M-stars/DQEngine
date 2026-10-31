"""调度器与监控的关键用例: CRON/INTERVAL/WATCH 调度语义、任务增删、趋势与告警回调."""

from datetime import datetime

import pandas as pd

from dqengine.models.schemas import ScheduleType, ScheduledTask


# ---- 调度器 ----


class TestSchedulerNextRun:
    def _task(self, schedule_type, value, tmp_path):
        data = tmp_path / "data.csv"
        pd.DataFrame({"a": [1, 2]}).to_csv(data, index=False)
        return ScheduledTask(
            task_id=f"t-{schedule_type.value}",
            name="demo",
            schedule_type=schedule_type,
            schedule_value=value,
            action="profile",
            target_path=str(data),
        )

    def test_interval_next_run(self, tmp_path):
        from dqengine.scheduler.scheduler import TaskScheduler

        s = TaskScheduler()
        task = self._task(ScheduleType.INTERVAL, "3600", tmp_path)
        s.update_next_run(task)
        next_dt = datetime.fromisoformat(task.next_run)
        delta = (next_dt - datetime.now()).total_seconds()
        assert 3500 < delta <= 3601
        assert task.last_run is not None

    def test_cron_next_run_future(self, tmp_path):
        from dqengine.scheduler.scheduler import TaskScheduler

        s = TaskScheduler()
        task = self._task(ScheduleType.CRON, "0 3 * * *", tmp_path)
        s.update_next_run(task)
        next_dt = datetime.fromisoformat(task.next_run)
        assert next_dt > datetime.now()
        try:
            import croniter  # noqa: F401

            has_croniter = True
        except ImportError:
            has_croniter = False
        if has_croniter:
            # croniter 可用时表达式语义必须精确
            assert next_dt.hour == 3 and next_dt.minute == 0

    def test_cron_without_croniter_degrades(self, tmp_path, monkeypatch):
        """croniter 缺失时退化为 5 分钟间隔, 不得抛异常停摆."""
        import builtins

        from dqengine.scheduler.scheduler import TaskScheduler

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "croniter":
                raise ImportError("blocked for test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked)
        s = TaskScheduler()
        task = self._task(ScheduleType.CRON, "0 3 * * *", tmp_path)
        s.update_next_run(task)
        next_dt = datetime.fromisoformat(task.next_run)
        delta = (next_dt - datetime.now()).total_seconds()
        assert 200 < delta <= 301

    def test_watch_next_run_is_none(self, tmp_path):
        from dqengine.scheduler.scheduler import TaskScheduler

        s = TaskScheduler()
        task = self._task(ScheduleType.WATCH, str(tmp_path), tmp_path)
        s.update_next_run(task)
        assert task.next_run is None  # 动态触发


class TestSchedulerTasks:
    def test_add_and_remove(self, tmp_path):
        from dqengine.scheduler.scheduler import TaskScheduler

        data = tmp_path / "data.csv"
        pd.DataFrame({"a": [1]}).to_csv(data, index=False)
        s = TaskScheduler(state_file=str(tmp_path / "state.json"))
        task = ScheduledTask(
            task_id="x1", name="n", schedule_type=ScheduleType.INTERVAL,
            schedule_value="60", action="profile", target_path=str(data),
        )
        s.add_task(task)
        assert "x1" in s.tasks
        s.update_next_run(task)
        assert s.remove_task("x1") is True
        assert "x1" not in s.tasks
        assert s.remove_task("x1") is False

    def test_state_roundtrip_keeps_next_run(self, tmp_path):
        from dqengine.scheduler.scheduler import TaskScheduler

        data = tmp_path / "data.csv"
        pd.DataFrame({"a": [1]}).to_csv(data, index=False)
        state = tmp_path / "state.json"
        s1 = TaskScheduler(state_file=str(state))
        task = ScheduledTask(
            task_id="r1", name="n", schedule_type=ScheduleType.INTERVAL,
            schedule_value="120", action="profile", target_path=str(data),
        )
        s1.add_task(task)
        s1.update_next_run(task)
        s1.save_state()

        s2 = TaskScheduler(state_file=str(state))
        s2.load_state()
        assert s2.tasks["r1"].next_run == task.next_run


# ---- 监控 ----


class TestMonitorCallbacksAndTrends:
    def test_event_callback_fires(self, tmp_path):
        from dqengine.monitoring.monitor import QualityMonitor

        incoming = tmp_path / "in"
        incoming.mkdir()
        pd.DataFrame({"a": [1, 2, 3]}).to_csv(incoming / "d.csv", index=False)

        received = []
        m = QualityMonitor(watch_directory=str(incoming), trends_file=str(tmp_path / "t.json"))
        m.on_event(lambda ev: received.append(ev))
        events = m.scan_directory()
        assert len(events) == 1
        assert len(received) == 1
        assert received[0].file_path == events[0].file_path

    def test_failed_file_alerts_not_crashes(self, tmp_path):
        """坏文件扫描不得让整个扫描崩溃; 同目录好文件不受影响."""
        from dqengine.monitoring.monitor import QualityMonitor

        incoming = tmp_path / "in"
        incoming.mkdir()
        (incoming / "bad.csv").write_bytes(b"\x00\xff garbage \x01")
        pd.DataFrame({"a": [1, 2, 3]}).to_csv(incoming / "good.csv", index=False)

        m = QualityMonitor(watch_directory=str(incoming), trends_file=str(tmp_path / "t.json"))
        events = m.scan_directory()  # 不得抛异常
        assert len(events) == 2
        good = [e for e in events if e.file_path.endswith("good.csv")]
        assert good and good[0].profile is not None

    def test_trends_roundtrip(self, tmp_path):
        from dqengine.monitoring.monitor import QualityMonitor

        incoming = tmp_path / "in"
        incoming.mkdir()
        pd.DataFrame({"a": [1, 2, 3]}).to_csv(incoming / "d.csv", index=False)
        trends_file = tmp_path / "t.json"

        m1 = QualityMonitor(watch_directory=str(incoming), trends_file=str(trends_file))
        m1.scan_directory()
        m1._save_trends()
        assert trends_file.exists()

        m2 = QualityMonitor(watch_directory=str(incoming), trends_file=str(trends_file))
        m2.scan_directory()
        # 新会话应能读到历史趋势 (不因文件缺失/格式问题崩溃)
        assert isinstance(m2.get_trends(hours=24), list)

    def test_duplicate_scan_skips_processed(self, tmp_path):
        from dqengine.monitoring.monitor import QualityMonitor

        incoming = tmp_path / "in"
        incoming.mkdir()
        pd.DataFrame({"a": [1]}).to_csv(incoming / "d.csv", index=False)
        m = QualityMonitor(watch_directory=str(incoming), trends_file=str(tmp_path / "t.json"))
        assert len(m.scan_directory()) == 1
        assert len(m.scan_directory()) == 0  # 已处理文件不重扫
