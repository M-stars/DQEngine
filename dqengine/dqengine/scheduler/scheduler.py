"""任务调度系统 — cron, interval, file watcher."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.utils.logger import get_logger
from dqengine.models.schemas import (
    ScheduledTask,
    ScheduleConfig,
    ScheduleType,
)
from dqengine.repair.date_standardizer import DateStandardizer
from dqengine.repair.duplicate import DuplicateCleaner
from dqengine.repair.missing_value import MissingValueCleaner
from dqengine.report.generator import ReportGenerator


logger = get_logger(__name__)


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

    def __init__(
        self,
        config: Optional[ScheduleConfig] = None,
        state_file: Optional[str] = None,
    ) -> None:
        self.config = config or ScheduleConfig()
        # 任务状态持久化: 重启后恢复 next_run, 避免 CRON 任务在重启后
        # 因 next_run 为空被立即触发一次 (意外重跑副作用任务)
        self.state_file = Path(state_file) if state_file else None
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
        self._apscheduler: Any = None
        # WATCH 任务的文件快照: task_id -> {file_path: mtime}
        self._watch_state: Dict[str, Dict[str, float]] = {}
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

        if not isinstance(data, dict):
            raise ValueError(
                f"调度配置文件格式错误: 顶层应为映射 (收到 {type(data).__name__})"
            )

        tasks_data = data.get("tasks", data.get("schedule", [])) or []
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
        self.save_state()

    def save_state(self) -> None:
        """持久化任务定义与调度状态 (next_run/last_run) 到 state_file."""
        if not self.state_file:
            return
        data = {
            "tasks": [
                {
                    "task_id": t.task_id,
                    "name": t.name,
                    "schedule_type": t.schedule_type.value,
                    "schedule_value": t.schedule_value,
                    "action": t.action,
                    "target_path": t.target_path,
                    "config_path": t.config_path,
                    "enabled": t.enabled,
                    "next_run": t.next_run,
                    "last_run": t.last_run,
                }
                for t in self.tasks.values()
            ]
        }
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def load_state(self) -> int:
        """从 state_file 恢复任务与调度状态.

        Returns:
            恢复的任务数 (无状态文件时为 0).
        """
        if not self.state_file or not self.state_file.exists():
            return 0
        data = json.loads(self.state_file.read_text(encoding="utf-8"))
        restored = 0
        for t in data.get("tasks", []):
            task = ScheduledTask(
                task_id=t["task_id"],
                name=t["name"],
                schedule_type=ScheduleType(t["schedule_type"]),
                schedule_value=t["schedule_value"],
                action=t["action"],
                target_path=t["target_path"],
                config_path=t.get("config_path"),
                enabled=t.get("enabled", True),
                next_run=t.get("next_run"),
                last_run=t.get("last_run"),
            )
            existing = self.tasks.get(task.task_id)
            if existing is None:
                self.tasks[task.task_id] = task
                self.config.tasks.append(task)
                restored += 1
            else:
                # 任务定义以代码/YAML 为准, 但调度状态 (next_run) 以
                # 持久化状态为准——否则重启后 CRON 仍会被立即执行一次
                existing.next_run = task.next_run
                existing.last_run = task.last_run
                existing.enabled = task.enabled
        logger.info("已从 %s 恢复 %d 个调度任务", self.state_file, restored)
        return restored

    def remove_task(self, task_id: str) -> bool:
        """移除调度任务."""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self.config.tasks = [t for t in self.config.tasks if t.task_id != task_id]
            self.save_state()
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
            task.next_run = self._next_cron_run(task.schedule_value, now)
        elif task.schedule_type == ScheduleType.WATCH:
            task.next_run = None  # 文件监听模式下动态触发

    def _next_cron_run(self, expr: str, after: datetime) -> str:
        """计算 cron 表达式在 after 之后的下次运行时间."""
        try:
            from croniter import croniter
            return croniter(expr, after).get_next(datetime).isoformat()
        except ImportError:
            logger.warning(
                "croniter 未安装, cron 任务退化为每 5 分钟执行 "
                "(pip install croniter 可按表达式调度)"
            )
            from datetime import timedelta
            return (after + timedelta(minutes=5)).isoformat()

    @staticmethod
    def _snapshot_dir(root: Path) -> dict:
        """递归快照 {路径: mtime}.

        os.scandir 的 DirEntry.stat 复用目录句柄缓存, 每个文件只触发
        一次系统调用; 逐 entry 调 Path.is_file()+Path.stat() 是两次 stat
        (实测 5000 文件 334ms → 6ms), WATCH 任务每 10s 执行一次本方法.
        """
        state: dict = {}
        stack = [str(root)]
        while stack:
            current = stack.pop()
            with os.scandir(current) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    else:
                        try:
                            state[entry.path] = entry.stat(follow_symlinks=False).st_mtime
                        except OSError:
                            continue
        return state

    def _watch_has_changes(self, task: ScheduledTask) -> bool:
        """轮询模式下 WATCH 任务的变更检测.

        对监听路径建立文件 mtime 快照，与上次快照比较；首次见到该任务
        仅建立基线不触发，之后快照发生变化（新增/修改/删除文件）才触发.
        """
        watch_path = Path(task.schedule_value) if task.schedule_value else Path(task.target_path)
        try:
            if watch_path.is_dir():
                state = self._snapshot_dir(watch_path)
            elif watch_path.exists():
                state = {str(watch_path): watch_path.stat().st_mtime}
            else:
                return False
        except OSError:
            return False

        last_state = self._watch_state.get(task.task_id)
        self._watch_state[task.task_id] = state
        return last_state is not None and state != last_state

    def start(self, blocking: bool = True) -> None:
        """启动调度器."""
        self._running = True
        self.load_state()
        logger.info(f"[调度器] 启动: {len(self.tasks)} 个任务")

        # 使用 APScheduler (如果可用)
        try:
            self._start_apscheduler(blocking)
        except ImportError:
            logger.info("[调度器] APScheduler 未安装，使用内置轮询模式")
            if blocking:
                self._start_polling()
            else:
                import threading
                thread = threading.Thread(target=self._start_polling, daemon=True)
                thread.start()

    def _start_apscheduler(self, blocking: bool) -> None:
        """使用 APScheduler 启动."""
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        scheduler = BackgroundScheduler()
        self._apscheduler = scheduler

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
                logger.warning(
                    "APScheduler 模式暂不支持 watch 任务 [%s], 请改用 blocking 轮询模式",
                    task.name,
                )
                continue

            scheduler.add_job(
                self._execute_task,
                trigger=trigger,
                args=[task],
                id=job_id,
                name=task.name,
            )

        scheduler.start()
        logger.info("[调度器] APScheduler 已启动")

        try:
            if blocking:
                while self._running:
                    time.sleep(1)
        except KeyboardInterrupt:
            scheduler.shutdown()
            logger.info("\n[调度器] 已停止")

    def _start_polling(self) -> None:
        """内置轮询模式."""
        try:
            while self._running:
                now = datetime.now()

                for task in self.tasks.values():
                    if not task.enabled:
                        continue

                    should_run = False
                    if task.schedule_type == ScheduleType.INTERVAL:
                        if task.next_run is None:
                            should_run = True  # 首次立即执行，随后按间隔调度
                        else:
                            should_run = now >= datetime.fromisoformat(task.next_run)
                    elif task.schedule_type == ScheduleType.CRON:
                        if task.next_run is None:
                            # 按 cron 表达式计算首次运行时间，不立即执行
                            task.next_run = self._next_cron_run(task.schedule_value, now)
                        else:
                            should_run = now >= datetime.fromisoformat(task.next_run)
                    elif task.schedule_type == ScheduleType.WATCH:
                        should_run = self._watch_has_changes(task)

                    if should_run:
                        logger.info(f"[调度器] 执行任务: {task.name} ({task.action})")
                        self._execute_task(task)

                time.sleep(10)
        except KeyboardInterrupt:
            logger.info("\n[调度器] 已停止")

    def stop(self) -> None:
        """停止调度器."""
        self._running = False
        if self._apscheduler is not None:
            try:
                self._apscheduler.shutdown(wait=False)
            except Exception as e:
                logger.info(f"[调度器] APScheduler 关闭异常: {e}")
            finally:
                self._apscheduler = None

    def _execute_task(self, task: ScheduledTask) -> None:
        """执行单个调度任务."""
        try:
            executor = self._executors.get(task.action)
            if executor is None:
                logger.info(f"[调度器] 未知操作: {task.action}")
                return

            result = executor(task)
            result["task_id"] = task.task_id
            result["task_name"] = task.name
            result["executed_at"] = datetime.now().isoformat()
            self._results.append(result)
            if len(self._results) > 1000:
                del self._results[: len(self._results) - 1000]
            self.update_next_run(task)
            self.save_state()
        except Exception as e:
            logger.error(f"[调度器] 任务失败 [{task.name}]: {e}")
            self._results.append(
                {
                    "task_id": task.task_id,
                    "task_name": task.name,
                    "action": task.action,
                    "success": False,
                    "error": str(e),
                    "executed_at": datetime.now().isoformat(),
                }
            )

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
        # 清洗结果落盘: 否则 clean 调度动作除统计外没有任何持久效果
        target = Path(task.target_path)
        output = Path(task.config_path) if task.config_path else target.parent / f"cleaned_{target.name}"
        output.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output, index=False, encoding="utf-8")
        return {
            "action": "clean",
            "success": True,
            "rows_before": rows_before,
            "rows_after": rows_after,
            "output": str(output),
        }

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
