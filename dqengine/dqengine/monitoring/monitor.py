"""持续数据质量监控器 — 文件监听、增量分析、历史趋势."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.drift.detector import DriftDetector
from dqengine.utils.logger import get_logger
from dqengine.models.schemas import (
    DriftReport,
    MonitorEvent,
    MonitorSession,
    ProfileResult,
    QualityScore,
    QualityTrend,
)


logger = get_logger(__name__)


class QualityMonitor:
    """持续数据质量监控器.

    功能:
    - 监听目录中的文件变化 (支持 watchdog)
    - 增量分析新文件
    - 记录历史质量趋势
    - 漂移检测告警

    Usage:
        monitor = QualityMonitor("./incoming_data")
        monitor.start_polling(interval_seconds=30)
    """

    SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".json", ".parquet"}

    def __init__(
        self,
        watch_directory: str,
        baseline_file: Optional[str] = None,
        trends_file: str = "quality_trends.json",
    ) -> None:
        self.watch_dir = Path(watch_directory)
        self.baseline_file = baseline_file
        self.trends_file = Path(trends_file)
        self.session = MonitorSession(
            session_id=str(uuid.uuid4())[:8],
            watch_directory=str(self.watch_dir),
            started_at=datetime.now().isoformat(),
        )
        self.loader = DataLoader()
        self.profiler = Profiler()
        self.scorer = QualityScorer()
        self.drift_detector = DriftDetector() if baseline_file else None
        self._processed_files: set[str] = set()
        # 基线缓存: (路径, mtime, DataFrame), 基线文件变化时自动失效
        self._baseline_cache: tuple = (None, None, None)
        self._historical_trends: List[QualityTrend] = []
        self._callbacks: List[Callable[[MonitorEvent], None]] = []

    def on_event(self, callback: Callable[[MonitorEvent], None]) -> None:
        """注册事件回调."""
        self._callbacks.append(callback)

    def scan_directory(self) -> List[MonitorEvent]:
        """扫描目录中所有数据文件并分析."""
        events: List[MonitorEvent] = []

        # 单次 os.walk 全树遍历后按后缀过滤, 替代按扩展名多次全树 glob;
        # 后缀比较大小写不敏感 (Windows 下 *.CSV 此前会被漏检)
        exts = {e.lower() for e in self.SUPPORTED_EXTENSIONS}
        candidates = []
        for dirpath, _dirnames, filenames in os.walk(self.watch_dir):
            for fn in filenames:
                if fn.lower().endswith(tuple(exts)):
                    candidates.append(Path(dirpath) / fn)

        for file_path in candidates:
            if str(file_path) in self._processed_files:
                continue

            try:
                event = self._process_file(file_path)
                events.append(event)
                self._processed_files.add(str(file_path))
            except Exception as e:
                event = MonitorEvent(
                    timestamp=datetime.now().isoformat(),
                    file_path=str(file_path),
                    event_type="created",
                )
                self.session.alerts.append(f"处理失败: {file_path.name} - {e}")
                events.append(event)

        self.session.events.extend(events)

        return events

    def _get_baseline(self):
        """返回缓存的基线 (mtime, df); 基线未变时免重读, 变化时返回 None 触发重载."""
        cached_path, cached_mtime, cached_df = self._baseline_cache
        if cached_path != self.baseline_file or cached_df is None:
            return None, None
        try:
            if Path(self.baseline_file).stat().st_mtime == cached_mtime:
                return cached_df, cached_mtime
        except OSError:
            pass
        return None, None

    def _process_file(self, file_path: Path) -> MonitorEvent:
        """处理单个文件."""
        self.session.total_files_processed += 1
        df = self.loader.load(file_path)
        profile = self.profiler.profile(df, file_path=str(file_path))
        score = self.scorer.score(df, profile)

        # 记录趋势
        null_rates = [c.null_rate for c in profile.columns]
        trend = QualityTrend(
            timestamp=datetime.now().isoformat(),
            file_name=file_path.name,
            overall_score=score.overall_score,
            row_count=profile.row_count,
            null_rate=sum(null_rates) / max(len(null_rates), 1),
            duplicate_rate=profile.duplicate_row_rate,
        )
        self.session.trends.append(trend)

        # 漂移检测 (基线按 mtime 缓存: 基线 1M 行时每新文件可省
        # 约 1.3s 读取 + 1.8s 画像; 漂移只用到 null_rate, 但复用
        # detect_frames 的完整实现以保证语义一致)
        drift_detected = False
        if self.drift_detector and self.baseline_file:
            try:
                baseline_df, baseline_mtime = self._get_baseline()
                if baseline_df is None:
                    baseline_df = self.loader.load(Path(self.baseline_file))
                    baseline_mtime = Path(self.baseline_file).stat().st_mtime
                    self._baseline_cache = (self.baseline_file, baseline_mtime, baseline_df)
                current_df = self.loader.load(file_path)
                drift_report = self.drift_detector.detect_frames(
                    baseline_df, current_df,
                    baseline_name=self.baseline_file,
                    current_name=str(file_path),
                )
                drift_detected = drift_report.overall_severity.value not in ("none", "low")
                if drift_detected:
                    self.session.alerts.append(
                        f"漂移检测告警 [{file_path.name}]: {drift_report.overall_severity.value}"
                    )
            except Exception as e:
                # 漂移是监控的核心告警能力, 失败必须可见, 否则静默漏报
                logger.error("[监控] 漂移检测失败 [{file_path.name}]: {e}")

        # 阈值告警
        if score.overall_score < 60:
            self.session.alerts.append(
                f"低质量告警 [{file_path.name}]: 评分 {score.overall_score:.1f}"
            )

        event = MonitorEvent(
            timestamp=datetime.now().isoformat(),
            file_path=str(file_path),
            event_type="created",
            profile=profile,
            score=score,
            drift_detected=drift_detected,
        )

        # 触发回调
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.error("[监控] 回调执行失败: {e}")

        return event

    def start_polling(self, interval_seconds: int = 30) -> None:
        """轮询模式: 定期扫描目录.

        对于持续监听, 推荐配合 watchdog 使用 (见 start_watching 方法).
        """
        import time as _time

        interval_seconds = max(1, int(interval_seconds))
        logger.info("[监控] 开始轮询: {self.watch_dir} (间隔: {interval_seconds}s)")
        logger.info("[监控] 会话 ID: {self.session.session_id}")
        try:
            while True:
                events = self.scan_directory()
                if events:
                    for e in events:
                        if e.score:
                            logger.info(
                                "%s 评分: %.1f 漂移: %s",
                                Path(e.file_path).name,
                                e.score.overall_score,
                                "是" if e.drift_detected else "否",
                            )
                self._save_trends()
                _time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("\n[监控] 停止轮询. 共处理 {self.session.total_files_processed} 个文件")
            self._save_trends()
            # 向调用方传播, 让其执行停止后的收尾逻辑 (如生成趋势报告)
            raise

    def start_watching(self) -> None:
        """Watchdog 模式: 实时文件监听."""
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            logger.info("[监控] watchdog 未安装, 回退到轮询模式")
            self.start_polling()
            return

        monitor = self

        class DataFileHandler(FileSystemEventHandler):
            def on_created(self_2, event, attempt: int = 0) -> None:  # type: ignore
                if event.is_directory:
                    return
                path = Path(event.src_path)
                if path.suffix not in QualityMonitor.SUPPORTED_EXTENSIONS:
                    return
                if str(path) in monitor._processed_files:
                    return
                logger.info("[监控] 检测到新文件: {path.name}")
                try:
                    monitor._process_file(path)
                    monitor._save_trends()
                    monitor._processed_files.add(str(path))
                except Exception as e:
                    # 创建事件触发时文件常尚未写完 (复制/上传中), 延迟重试
                    # 而不是永久漏检
                    if attempt < 3:
                        delay = 5 * (attempt + 1)
                        logger.warning(
                            "处理失败 (可能仍在写入): %s - %s, %ds 后重试 (%d/3)",
                            path.name, e, delay, attempt + 1,
                        )
                        timer = threading.Timer(
                            delay, self_2.on_created, args=(event,), kwargs={"attempt": attempt + 1}
                        )
                        timer.daemon = True
                        timer.start()
                    else:
                        logger.error("[监控] 处理失败, 已放弃: {path.name} - {e}")

        logger.info("[监控] 开始 Watchdog 监听: {self.watch_dir}")
        logger.info("[监控] 会话 ID: {self.session.session_id}")

        observer = Observer()
        observer.schedule(DataFileHandler(), str(self.watch_dir), recursive=True)
        observer.start()

        try:
            while observer.is_alive():
                observer.join(1)
        except KeyboardInterrupt:
            observer.stop()
            logger.info("\n[监控] 停止监听")
        observer.join()

    def get_trends(self, hours: int = 24) -> List[QualityTrend]:
        """获取指定时间范围内的质量趋势."""
        cutoff = datetime.now().timestamp() - hours * 3600
        return [t for t in self.session.trends if datetime.fromisoformat(t.timestamp).timestamp() > cutoff]

    MAX_TRENDS = 1000

    def _save_trends(self) -> None:
        """保存趋势数据 (长驻会话: 内存与文件都只保留最近 MAX_TRENDS 条)."""
        if self.trends_file:
            if len(self.session.trends) > self.MAX_TRENDS:
                del self.session.trends[: len(self.session.trends) - self.MAX_TRENDS]
            data = [t.model_dump() for t in self.session.trends]
            self.trends_file.parent.mkdir(parents=True, exist_ok=True)
            self.trends_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def generate_trends_html(self, output_path: str = "monitoring_report.html") -> str:
        """生成监控趋势 HTML 报告."""
        trends = self.session.trends

        chart_data = json.dumps([
            {
                "timestamp": t.timestamp[:19],
                "score": t.overall_score,
                "null_rate": round(t.null_rate * 100, 2),
                "duplicate_rate": round(t.duplicate_rate * 100, 2),
            }
            for t in trends[-100:]
        ])

        alerts_html = "".join(
            f'<tr><td style="color:#e74c3c">{a}</td></tr>' for a in self.session.alerts[-20:]
        )

        if not trends:
            return ""

        latest = trends[-1]
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>DQEngine 质量监控报告</title>
    <script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 2rem; }}
        .header {{ text-align: center; margin-bottom: 2rem; }}
        .header h1 {{ color: #38bdf8; }}
        .summary {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 2rem; }}
        .summary-item {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; text-align: center; }}
        .summary-item .value {{ font-size: 2rem; font-weight: bold; color: #38bdf8; }}
        .summary-item .label {{ color: #94a3b8; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }}
        .card h2 {{ color: #38bdf8; margin-bottom: 1rem; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 0.5rem; text-align: left; border-bottom: 1px solid #334155; }}
        #chart {{ min-height: 400px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>DQEngine 质量监控报告</h1>
        <p>会话: {self.session.session_id} | 目录: {self.watch_dir}</p>
    </div>
    <div class="summary">
        <div class="summary-item">
            <div class="value">{self.session.total_files_processed}</div>
            <div class="label">已处理文件</div>
        </div>
        <div class="summary-item">
            <div class="value">{latest.overall_score:.1f}</div>
            <div class="label">最新评分</div>
        </div>
        <div class="summary-item">
            <div class="value">{len(self.session.alerts)}</div>
            <div class="label">告警数</div>
        </div>
    </div>
    <div class="card">
        <h2>质量趋势</h2>
        <div id="chart"></div>
    </div>
    <div class="card">
        <h2>近期告警</h2>
        <table>
            {alerts_html or '<tr><td style="color:#94a3b8">没有告警</td></tr>'}
        </table>
    </div>
    <script>
        var data = {chart_data};
        var timestamps = data.map(d => d.timestamp);
        var scores = data.map(d => d.score);
        var nullRates = data.map(d => d.null_rate);

        var trace1 = {{ x: timestamps, y: scores, type: 'scatter', mode: 'lines+markers',
            name: '质量评分', line: {{ color: '#38bdf8', width: 3 }} }};
        var trace2 = {{ x: timestamps, y: nullRates, type: 'scatter', mode: 'lines+markers',
            name: '空值率(%)', yaxis: 'y2', line: {{ color: '#f97316', width: 2, dash: 'dot' }} }};

        var layout = {{
            paper_bgcolor: '#1e293b', plot_bgcolor: '#1e293b',
            font: {{ color: '#e2e8f0' }},
            xaxis: {{ gridcolor: '#334155', showgrid: true }},
            yaxis: {{ title: '质量评分', range: [0, 100], gridcolor: '#334155' }},
            yaxis2: {{ title: '空值率(%)', overlaying: 'y', side: 'right', gridcolor: 'transparent' }},
            margin: {{ t: 20, r: 60, l: 50, b: 50 }}
        }};

        Plotly.newPlot('chart', [trace1, trace2], layout, {{ responsive: true }});
    </script>
</body>
</html>"""
        path = Path(output_path)
        path.write_text(html, encoding="utf-8")
        return str(path)
