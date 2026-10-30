"""内置插件: Kafka 消息队列连接器.

URI 语义 (非 SQL 库, 语义与关系连接器不同):
    - URI: ``kafka://broker1:9092,broker2:9092/topic`` (可多 broker)
    - ``table`` 参数可省略; 提供时覆盖 URI 路径中的 topic
    - ``query`` 不适用 (忽略并告警)

取数语义:
    订阅 topic 消费至多 ``limit`` 条消息 (缺省 1000), 每条消息按
    JSON 解析为行 (嵌套展平); 非 JSON 消息落入 ``value`` 原文列.
    适用于对流入消息做画像/规则验证的数据质量检查, 不是全量回放工具.

依赖可选: 未安装 kafka-python 时本模块 import 即失败,
PluginRegistry 会跳过该插件, 不影响核心功能.
"""

from __future__ import annotations

import json
from typing import Optional
from urllib.parse import urlparse

import pandas as pd

from dqengine.models.schemas import PluginInfo, PluginType
from dqengine.plugins.base import BaseConnector
from dqengine.utils.logger import get_logger

logger = get_logger(__name__)


def parse_kafka_uri(uri: str) -> tuple:
    """解析 Kafka URI 为 (brokers 列表, topic) (纯函数, 便于测试).

    Args:
        uri: ``kafka://broker1:9092,broker2:9092/topic``.

    Returns:
        (brokers, topic) 元组.

    Raises:
        ValueError: URI 缺少 broker 或 topic.
    """
    parsed = urlparse(uri)
    brokers = [b for b in parsed.netloc.split(",") if b.strip()]
    if not brokers:
        raise ValueError(
            f"Kafka URI 缺少 broker 地址: kafka://<broker:9092[,broker2:9092]>/<topic> ({uri!r})"
        )
    topic = parsed.path.lstrip("/").split("?", 1)[0]
    if not topic:
        raise ValueError(f"Kafka URI 缺少 topic: kafka://<broker>/<topic> ({uri!r})")
    return brokers, topic


def decode_message(raw: bytes) -> dict:
    """把单条消息解码为行 (纯函数, 便于测试).

    JSON 消息 → 解析为 dict (供 json_normalize 展平);
    非 JSON 消息 → {"value": <utf-8 原文>}, 解码失败按 latin-1 兜底.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"value": raw.decode("latin-1", errors="replace")}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"value": text}
    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


class KafkaConnector(BaseConnector):
    """Kafka 连接器 — 消费 topic 消息为 DataFrame (JSON 展平, 非JSON入 value 列)."""

    PLUGIN_INFO = PluginInfo(
        name="kafka_connector",
        plugin_type=PluginType.LOADER,
        version="0.1.0",
        description="Kafka 消息连接器 (topic 消费→DataFrame, JSON 展平), 依赖 kafka-python",
        dependencies=["kafka-python"],
    )

    SCHEMES = ("kafka",)

    def load(
        self,
        uri: str,
        table: Optional[str] = None,
        query: Optional[str] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """从 topic 消费消息构建 DataFrame.

        Args:
            uri: ``kafka://broker[:9092][,broker2...]/topic``.
            table: 可选, 覆盖 URI 中的 topic.
            query: 不适用 (忽略并告警).
            **kwargs: ``limit`` 消息条数 (缺省 1000); ``timeout`` 无新消息
                等待秒数 (缺省 10); ``auto_offset_reset`` 起点偏移
                (缺省 earliest); ``security_protocol``/``sasl_*`` 等
                原样透传给 KafkaConsumer.

        Returns:
            DataFrame (JSON 消息展平为列, 非 JSON 消息进 ``value`` 列).

        Raises:
            ImportError: 未安装 kafka-python.
            ValueError: URI 缺少 broker 或 topic.
        """
        try:
            from kafka import KafkaConsumer
        except ImportError:
            raise ImportError(
                'Kafka 连接器需要 kafka-python: pip install "dqengine[kafka]"'
            )

        if query:
            logger.warning("Kafka 连接器不支持 --query, 该参数已忽略")

        brokers, uri_topic = parse_kafka_uri(uri)
        topic = table or uri_topic
        limit = int(kwargs.pop("limit", 1000))
        timeout = float(kwargs.pop("timeout", 10.0))
        offset = kwargs.pop("auto_offset_reset", "earliest")

        logger.info(
            "Kafka 消费: brokers=%s topic=%s (limit=%d, timeout=%.0fs, offset=%s)",
            brokers, topic, limit, timeout, offset,
        )
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=brokers,
            auto_offset_reset=offset,
            consumer_timeout_ms=int(timeout * 1000),
            **kwargs,
        )
        try:
            rows = []
            for msg in consumer:
                rows.append(decode_message(msg.value))
                if len(rows) >= limit:
                    break
        finally:
            consumer.close()

        logger.info("Kafka 加载完成: %d 条消息", len(rows))
        return pd.json_normalize(rows) if rows else pd.DataFrame()
