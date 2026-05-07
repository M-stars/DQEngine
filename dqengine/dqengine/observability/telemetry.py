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

from dqengine.models.schemas import (
    ExecutionTrace,
    Metric,
    MetricType,
    ObservabilityReport,
    RuleExecutionStats,
)


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
        self.metrics: Dict[str, Metric] = {}
        self.traces: List[ExecutionTrace] = []
        self.rule_stats: Dict[str, RuleExecutionStats] = {}
        self._db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """初始化 SQLite 数据库."""
        conn = sqlite3.connect(str(self._db_path))
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
        conn.close()

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

    def export_prometheus(self) -> str:
        """导出 Prometheus 格式指标 (接口预留)."""
        lines: List[str] = []
        for name, metric in self.metrics.items():
            labels_str = ",".join(f'{k}="{v}"' for k, v in metric.labels.items())
            label_part = f"{{{labels_str}}}" if labels_str else ""
            lines.append(
                f"dqengine_{name}{label_part} {metric.value}"
            )
        return "\n".join(lines) + "\n"

    # ---- Database ----

    def _save_trace_to_db(self, trace: ExecutionTrace) -> None:
        conn = None
        try:
            conn = sqlite3.connect(str(self._db_path))
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
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

    def _save_rule_execution_to_db(
        self,
        rule_name: str,
        file_path: str,
        passed: bool,
        violations_count: int,
        execution_time_ms: float,
    ) -> None:
        conn = None
        try:
            conn = sqlite3.connect(str(self._db_path))
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
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

    def query_executions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """查询执行历史."""
        conn = None
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM executions ORDER BY start_time DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            if conn:
                conn.close()

    def get_execution_stats(self) -> Dict[str, Any]:
        """获取执行统计."""
        conn = None
        try:
            conn = sqlite3.connect(str(self._db_path))
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
        except Exception:
            return {}
        finally:
            if conn:
                conn.close()

    def close(self) -> None:
        """关闭数据库连接."""
        pass  # SQLite 连接在每次操作后自动关闭
