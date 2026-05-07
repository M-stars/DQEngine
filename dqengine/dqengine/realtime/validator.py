"""实时流式验证器 — Local Streaming Simulator."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pandas as pd

from dqengine.models.schemas import StreamEvent, StreamValidationResult
from dqengine.rules.validator import RuleValidator


class StreamValidator:
    """实时流式验证器 (Local Streaming Simulator).

    第一版实现:
    - 本地流模拟器 (从 JSON 文件读取事件流)
    - 逐条验证
    - WebSocket 接口预留
    - Kafka 接口预留

    Usage:
        validator = StreamValidator("configs/rules.yaml")
        for result in validator.validate_stream("stream_data.json"):
            print(result.passed)
    """

    def __init__(
        self,
        rules_path: Optional[str] = None,
        mode: str = "local",
    ) -> None:
        """
        Args:
            rules_path: YAML 规则文件路径
            mode: 模式 - "local" (本地模拟器), "websocket" (预留), "kafka" (预留)
        """
        self.rules_path = rules_path
        self.mode = mode
        self.validator = RuleValidator() if rules_path else None
        self._rules_loaded: Optional[Any] = None

    def validate_stream(
        self,
        stream_source: str,
        interval_ms: int = 0,
        max_events: int = 0,
    ) -> Iterator[StreamValidationResult]:
        """流式验证入口.

        Args:
            stream_source: 数据源 (JSON 文件路径 或 WebSocket URL 或 Kafka topic)
            interval_ms: 事件间延迟 (ms, 模拟实时)
            max_events: 最大事件数 (0 = 不限)

        Yields:
            StreamValidationResult: 每条事件的验证结果
        """
        if self.mode == "local":
            yield from self._validate_local_stream(stream_source, interval_ms, max_events)
        elif self.mode == "websocket":
            yield from self._validate_websocket_stream(stream_source)
        elif self.mode == "kafka":
            yield from self._validate_kafka_stream(stream_source)
        else:
            raise ValueError(f"不支持的流模式: {self.mode}")

    def _validate_local_stream(
        self,
        json_path: str,
        interval_ms: int = 0,
        max_events: int = 0,
    ) -> Iterator[StreamValidationResult]:
        """本地流模拟器: 从 JSON 文件逐条读取事件并验证."""
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"流数据文件未找到: {json_path}")

        with open(path, encoding="utf-8") as f:
            events_data = json.load(f)

        # 支持单条对象或对象数组
        if isinstance(events_data, dict):
            events_data = [events_data]

        count = 0
        for event_data in events_data:
            if max_events > 0 and count >= max_events:
                break

            event_id = event_data.get("id", str(uuid.uuid4())[:8])
            data = event_data.get("data", event_data)

            start_time = time.time()
            violations = []
            passed = True

            if self.validator and self.rules_path:
                df = pd.DataFrame([data])
                try:
                    result = self.validator.validate(df, self.rules_path)
                    violations = result.violations
                    passed = result.passed
                except Exception as e:
                    passed = False

            elapsed = (time.time() - start_time) * 1000

            yield StreamValidationResult(
                event_id=event_id,
                passed=passed,
                violations=violations,
                processing_time_ms=round(elapsed, 4),
            )

            count += 1
            if interval_ms > 0:
                time.sleep(interval_ms / 1000)

    def _validate_websocket_stream(self, url: str) -> Iterator[StreamValidationResult]:
        """WebSocket 流验证 (接口预留)."""
        raise NotImplementedError(
            "WebSocket 流验证尚未实现。安装 websockets 库后可用。"
        )

    def _validate_kafka_stream(self, topic: str) -> Iterator[StreamValidationResult]:
        """Kafka 流验证 (接口预留)."""
        raise NotImplementedError(
            "Kafka 流验证尚未实现。安装 kafka-python 库后可用。"
        )

    def validate_batch_stream(
        self,
        df: pd.DataFrame,
        rules_path: str,
        chunk_size: int = 1000,
    ) -> Iterator[StreamValidationResult]:
        """批量 DataFrame 流式验证 (分块处理)."""
        for i in range(0, len(df), chunk_size):
            chunk = df.iloc[i : i + chunk_size]
            event_id = f"batch_{i // chunk_size}"

            start = time.time()
            result = self.validator.validate(chunk, rules_path) if self.validator else None
            elapsed = (time.time() - start) * 1000

            yield StreamValidationResult(
                event_id=event_id,
                passed=result.passed if result else True,
                violations=result.violations if result else [],
                processing_time_ms=round(elapsed, 4),
            )
