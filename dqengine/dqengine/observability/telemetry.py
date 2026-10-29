"""可观测性系统 — metrics, tracing, execution logs."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from dqengine.utils.logger import get_logger
from dqengine.models.schemas import (
    ExecutionTrace,
    Metric,
    MetricType,
    ObservabilityReport,
    RuleExecutionStats,
)


logger = get_logger(__name__)


class TelemetryManager:
    """可观测性管理器.

    功能:
    - Metrics: counter / gauge / histogram / timer
    - Tracing: 执行追踪 (tree spans)
    - Execution Logs: SQLite 持久化
    - Rule Execution Stats: 规则执行统计
    - Prometheus 接口预留

    Usage:
        tm = TelemetryManager()
        tm.increment("profiles_created")
        with tm.trace("auto_clean"):
            ...
        tm.save_metrics("metrics.json")
    """

    def __init__(self, db_path: str = "execution_history.db") -> None:
        self._started_at = __import__('time').time()
        self.metrics: Dict[str, Metric] = {}
        self.traces: List[ExecutionTrace] = []
        self.rule_stats: Dict[str, RuleExecutionStats] = {}
        self._db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """初始化 SQLite 数据库."""
                # 持久连接 + WAL: 此前每条 trace/记录都新建连接并 commit
        # (fsync 约 4ms 占大头), 高频打点下开销放大 100 倍以上
        self._db_conn = sqlite3.connect(str(self._db_path))
        self._db_conn.execute("PRAGMA journal_mode=WAL")
        self._db_conn.execute("PRAGMA synchronous=NORMAL")
        conn = self._db_conn
        conn.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY,
                operation TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_ms REAL DEFAULT 0,
                success INTEGER DEFAULT 1,
                metadata TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                metric_type TEXT NOT NULL,
                value REAL NOT NULL,
                labels TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rule_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name TEXT NOT NULL,
                file_path TEXT,
                passed INTEGER,
                violations_count INTEGER,
                execution_time_ms REAL,
                executed_at TEXT NOT NULL
            )
        """)
        conn.commit()
        # 持久连接保持打开, close() 时统一关闭

    # ---- Metrics ----

    def increment(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """计数器 +1."""
        if name in self.metrics:
            self.metrics[name].value += value
            self.metrics[name].timestamp = datetime.now().isoformat()
        else:
            self.metrics[name] = Metric(
                name=name,
                metric_type=MetricType.COUNTER,
                value=value,
                labels=labels or {},
            )

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """设置仪表值."""
        self.metrics[name] = Metric(
            name=name,
            metric_type=MetricType.GAUGE,
            value=value,
            labels=labels or {},
        )

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """记录直方图值."""
        self.metrics[name] = Metric(
            name=name,
            metric_type=MetricType.HISTOGRAM,
            value=value,
            labels=labels or {},
        )

    def timer(self, name: str, duration_ms: float, labels: Optional[Dict[str, str]] = None) -> None:
        """记录时间指标."""
        self.metrics[name] = Metric(
            name=name,
            metric_type=MetricType.TIMER,
            value=duration_ms,
            labels=labels or {},
        )

    def get_metric(self, name: str) -> Optional[Metric]:
        """获取指标."""
        return self.metrics.get(name)

    # ---- Tracing ----

    @contextmanager
    def trace(self, operation: str, metadata: Optional[Dict[str, Any]] = None) -> Iterator[ExecutionTrace]:
        """执行追踪上下文管理器.

        Usage:
            with tm.trace("profile", {"file": "data.csv"}) as trace:
                ...
        """
        trace = ExecutionTrace(
            trace_id=str(uuid.uuid4())[:8],
            operation=operation,
            start_time=datetime.now().isoformat(),
            metadata=metadata or {},
        )
        start = time.time()
        try:
            yield trace
            trace.success = True
        except Exception:
            trace.success = False
            raise
        finally:
            trace.end_time = datetime.now().isoformat()
            trace.duration_ms = round((time.time() - start) * 1000, 2)
            self.traces.append(trace)
            # 长驻进程内存保护: 只保留最近 1000 条
            if len(self.traces) > 1000:
                del self.traces[: len(self.traces) - 1000]
            self._save_trace_to_db(trace)

    def add_span(self, parent_trace_id: str, span: ExecutionTrace) -> None:
        """添加子追踪."""
        for trace in self.traces:
            if trace.trace_id == parent_trace_id:
                trace.spans.append(span)
                return

    # ---- Rule Execution Stats ----

    def record_rule_execution(
        self,
        rule_name: str,
        passed: bool,
        violations_count: int = 0,
        execution_time_ms: float = 0.0,
        file_path: str = "",
    ) -> None:
        """记录规则执行."""
        if rule_name not in self.rule_stats:
            self.rule_stats[rule_name] = RuleExecutionStats(rule_name=rule_name)

        stats = self.rule_stats[rule_name]
        stats.total_executions += 1
        if passed:
            stats.passed += 1
        else:
            stats.failed += 1

        # 更新平均执行时间 (增量平均)
        stats.avg_execution_time_ms = (
            (stats.avg_execution_time_ms * (stats.total_executions - 1) + execution_time_ms)
            / stats.total_executions
        )
        stats.last_executed = datetime.now().isoformat()
        stats.pass_rate = stats.passed / max(stats.total_executions, 1)

        # 持久化到数据库
        self._save_rule_execution_to_db(rule_name, file_path, passed, violations_count, execution_time_ms)

    # ---- Report ----

    def generate_report(self) -> ObservabilityReport:
        """生成可观测性报告."""
        return ObservabilityReport(
            metrics=list(self.metrics.values()),
            traces=self.traces[-50:],
            rule_stats=list(self.rule_stats.values()),
        )

    def save_metrics(self, output_path: str = "metrics.json") -> str:
        """保存指标到 JSON."""
        report = self.generate_report()
        path = Path(output_path)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return str(path)

    def _rss_bytes(self) -> int:
        """当前进程常驻内存 (无 psutil 时用 resource/procfs, 再退化返回 0)."""
        try:
            import resource
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        except Exception:
            pass
        try:
            with open("/proc/self/status", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
        except Exception:
            pass
        return 0

    def export_prometheus(self) -> str:
        """导出 Prometheus 格式指标 (含进程级内置指标)."""
        import time as _time

        __import__("psutil") if False else None
        lines: List[str] = []
        # 内置运行时指标: 无需调用方打点即有数据
        start = getattr(self, "_started_at", None)
        if start:
            lines.append(f"dqengine_uptime_seconds {max(_time.time() - start, 0):.1f}")
        lines.append(f"dqengine_traces_total {len(self.traces)}")
        lines.append(f"dqengine_process_resident_memory_bytes {self._rss_bytes()}")
        for name, metric in self.metrics.items():
            labels_str = ",".join(f'{k}="{v}"' for k, v in metric.labels.items())
            label_part = f"{{{labels_str}}}" if labels_str else ""
            lines.append(
                f"dqengine_{name}{label_part} {metric.value}"
            )
        return "\n".join(lines) + "\n"

    # ---- Database ----

    def _save_trace_to_db(self, trace: ExecutionTrace) -> None:
        try:
            conn = self._db_conn
            conn.execute(
                "INSERT INTO executions VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    trace.trace_id,
                    trace.operation,
                    trace.start_time,
                    trace.end_time,
                    trace.duration_ms,
                    1 if trace.success else 0,
                    json.dumps(trace.metadata),
                ),
            )
            conn.commit()
        except Exception as e:
            logger.warning("遥测数据写入数据库失败: %s", e)

    def _save_rule_execution_to_db(
        self,
        rule_name: str,
        file_path: str,
        passed: bool,
        violations_count: int,
        execution_time_ms: float,
    ) -> None:
        try:
            conn = self._db_conn
            conn.execute(
                "INSERT INTO rule_executions VALUES (NULL, ?, ?, ?, ?, ?, ?)",
                (
                    rule_name,
                    file_path,
                    1 if passed else 0,
                    violations_count,
                    execution_time_ms,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
        except Exception as e:
            logger.warning("遥测数据写入数据库失败: %s", e)

    def query_executions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """查询执行历史."""
        try:
            conn = self._db_conn
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM executions ORDER BY start_time DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning("查询执行历史失败: %s", e)
            return []

    def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计."""
        try:
            conn = self._db_conn
            total = conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
            success = conn.execute("SELECT COUNT(*) FROM executions WHERE success=1").fetchone()[0]
            avg_duration = conn.execute(
                "SELECT AVG(duration_ms) FROM executions"
            ).fetchone()[0] or 0
            return {
                "total_executions": total,
                "successful": success,
                "failed": total - success,
                "success_rate": success / max(total, 1),
                "avg_duration_ms": round(avg_duration, 2),
            }
        except Exception as e:
            logger.warning("查询规则统计失败: %s", e)
            return {}

    def close(self) -> None:
        """关闭数据库连接."""
        if getattr(self, "_db_conn", None):
            try:
                self._db_conn.close()
            except Exception:
                pass
            self._db_conn = None
