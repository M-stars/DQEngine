"""任务调度系统 — cron, interval, file watcher."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import yaml

from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.models.schemas import (
    ScheduledTask,
    ScheduleConfig,
    ScheduleType,
)
from dqengine.repair.date_standardizer import DateStandardizer
from dqengine.repair.duplicate import DuplicateCleaner
from dqengine.repair.missing_value import MissingValueCleaner
from dqengine.repair.outlier import OutlierDetector
from dqengine.report.generator import ReportGenerator


class TaskScheduler:
    """任务调度器.

    支持三种调度模式:
    - cron: 基于 cron 表达式的定时调度
    - interval: 固定间隔调度 (秒)
    - watch: 文件监听 (目录变化触发)

    Usage:
        scheduler = TaskScheduler()
        scheduler.load_config("schedule.yaml")
        scheduler.start()
    """

    def __init__(self, config: Optional[ScheduleConfig] = None) -> None:
        self.config = config or ScheduleConfig()
        self.tasks: Dict[str, ScheduledTask] = {
            t.task_id: t for t in self.config.tasks
        }
        self._running: bool = False
        self._executors: Dict[str, Callable] = {
            "profile": self._run_profile,
            "validate": self._run_validate,
            "clean": self._run_clean,
            "report": self._run_report,
        }
        self._results: List[Dict[str, Any]] = []
        self.loader = DataLoader()
        self.profiler = Profiler()
        self.scorer = QualityScorer()

    def load_config(self, config_path: str) -> None:
        """从 YAML 文件加载调度配置."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"调度配置文件未找到: {config_path}")

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        tasks_data = data.get("tasks", data.get("schedule", []))
        task_list: List[ScheduledTask] = []
        for t in tasks_data:
            task_list.append(
                ScheduledTask(
                    task_id=t.get("id", str(uuid.uuid4())[:8]),
                    name=t.get("name", "unnamed"),
                    schedule_type=ScheduleType(t.get("schedule_type", "interval")),
                    schedule_value=str(t.get("schedule_value", "3600")),
                    action=t.get("action", "profile"),
                    target_path=t.get("target_path", ""),
                    config_path=t.get("config"),
                    enabled=t.get("enabled", True),
                )
            )

        self.config = ScheduleConfig(
            tasks=task_list,
            max_concurrent=data.get("max_concurrent", 3),
            log_dir=data.get("log_dir", "logs"),
        )
        self.tasks = {t.task_id: t for t in self.config.tasks}

    def add_task(self, task: ScheduledTask) -> None:
        """动态添加调度任务."""
        self.tasks[task.task_id] = task
        self.config.tasks.append(task)

    def remove_task(self, task_id: str) -> bool:
        """移除调度任务."""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self.config.tasks = [t for t in self.config.tasks if t.task_id != task_id]
            return True
        return False

    def update_next_run(self, task: ScheduledTask) -> None:
        """根据调度类型更新下次运行时间."""
        now = datetime.now()
        task.last_run = now.isoformat()

        if task.schedule_type == ScheduleType.INTERVAL:
            seconds = int(task.schedule_value)
            from datetime import timedelta
            task.next_run = (now + timedelta(seconds=seconds)).isoformat()
        elif task.schedule_type == ScheduleType.CRON:
            # 使用 croniter 计算下次运行时间
            try:
                from croniter import croniter
                cron = croniter(task.schedule_value, now)
                task.next_run = cron.get_next(datetime).isoformat()
            except ImportError:
                from datetime import timedelta
                task.next_run = (now + timedelta(minutes=5)).isoformat()
        elif task.schedule_type == ScheduleType.WATCH:
            task.next_run = None  # 文件监听模式下动态触发

    def start(self, blocking: bool = True) -> None:
        """启动调度器."""
        self._running = True
        print(f"[调度器] 启动: {len(self.tasks)} 个任务")

        # 使用 APScheduler (如果可用)
        try:
            self._start_apscheduler(blocking)
        except ImportError:
            print("[调度器] APScheduler 未安装，使用内置轮询模式")
            if blocking:
                self._start_polling()

    def _start_apscheduler(self, blocking: bool) -> None:
        """使用 APScheduler 启动."""
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = BackgroundScheduler()

        for task in self.tasks.values():
            if not task.enabled:
                continue

            job_id = task.task_id

            if task.schedule_type == ScheduleType.CRON:
                parts = task.schedule_value.split()
                trigger = CronTrigger(
                    minute=parts[0] if len(parts) > 0 else "*",
                    hour=parts[1] if len(parts) > 1 else "*",
                    day=parts[2] if len(parts) > 2 else "*",
                    month=parts[3] if len(parts) > 3 else "*",
                    day_of_week=parts[4] if len(parts) > 4 else "*",
                )
            elif task.schedule_type == ScheduleType.INTERVAL:
                trigger = IntervalTrigger(seconds=int(task.schedule_value))
            else:
                continue

            scheduler.add_job(
                self._execute_task,
                trigger=trigger,
                args=[task],
                id=job_id,
                name=task.name,
            )

        scheduler.start()
        print(f"[调度器] APScheduler 已启动")

        try:
            if blocking:
                while self._running:
                    time.sleep(1)
        except KeyboardInterrupt:
            scheduler.shutdown()
            print(f"\n[调度器] 已停止")

    def _start_polling(self) -> None:
        """内置轮询模式."""
        try:
            while self._running:
                now = datetime.now()

                for task in self.tasks.values():
                    if not task.enabled:
                        continue

                    should_run = False
                    if task.next_run is None:
                        should_run = True
                    elif task.schedule_type == ScheduleType.INTERVAL:
                        next_run = datetime.fromisoformat(task.next_run) if task.next_run else now
                        should_run = now >= next_run

                    if should_run:
                        print(f"[调度器] 执行任务: {task.name} ({task.action})")
                        self._execute_task(task)

                time.sleep(10)
        except KeyboardInterrupt:
            print(f"\n[调度器] 已停止")

    def stop(self) -> None:
        """停止调度器."""
        self._running = False

    def _execute_task(self, task: ScheduledTask) -> None:
        """执行单个调度任务."""
        try:
            executor = self._executors.get(task.action)
            if executor is None:
                print(f"[调度器] 未知操作: {task.action}")
                return

            result = executor(task)
            result["task_id"] = task.task_id
            result["task_name"] = task.name
            result["executed_at"] = datetime.now().isoformat()
            self._results.append(result)
            self.update_next_run(task)
        except Exception as e:
            print(f"[调度器] 任务失败 [{task.name}]: {e}")

    def _run_profile(self, task: ScheduledTask) -> Dict[str, Any]:
        df = self.loader.load(Path(task.target_path))
        profile = self.profiler.profile(df, file_path=task.target_path)
        score = self.scorer.score(df, profile)
        return {"action": "profile", "success": True, "score": score.overall_score}

    def _run_validate(self, task: ScheduledTask) -> Dict[str, Any]:
        from dqengine.rules.validator import RuleValidator
        df = self.loader.load(Path(task.target_path))
        rules_path = task.config_path or "configs/rules.yaml"
        result = RuleValidator().validate(df, rules_path)
        return {"action": "validate", "success": result.passed, "violations": result.total_violations}

    def _run_clean(self, task: ScheduledTask) -> Dict[str, Any]:
        df = self.loader.load(Path(task.target_path))
        rows_before = len(df)
        df, _ = MissingValueCleaner().clean(df)
        df, _ = DuplicateCleaner().clean(df)
        df, _ = DateStandardizer().standardize(df)
        rows_after = len(df)
        return {"action": "clean", "success": True, "rows_before": rows_before, "rows_after": rows_after}

    def _run_report(self, task: ScheduledTask) -> Dict[str, Any]:
        df = self.loader.load(Path(task.target_path))
        output = task.config_path or "scheduled_report.html"
        generator = ReportGenerator()
        profile = self.profiler.profile(df)
        score = self.scorer.score(df, profile)
        generator.generate(profile, score, [], [], output)
        return {"action": "report", "success": True, "output": output}

    def get_results(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取最近执行结果."""
        return self._results[-limit:]

    def save_results(self, output_path: str = "schedule_results.json") -> str:
        """保存执行结果."""
        path = Path(output_path)
        path.write_text(json.dumps(self._results, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)
