"""扩展连接器测试 (MongoDB / Kafka / SQL 方言 scheme 路由).

不含服务器的用例只测路由与纯函数解析; 需要真实服务的
load() 路径不在 CI 覆盖范围 (本地手动验证).
"""

import pandas as pd
import pytest

from dqengine.core.loader import DataLoader
from dqengine.plugins.discovery import (
    ensure_plugins_discovered,
    find_connector,
    reset_discovery,
)

pymongo = pytest.importorskip("pymongo", reason="pymongo 未安装, MongoDB 插件不可加载")
kafka_python = pytest.importorskip("kafka", reason="kafka-python 未安装, Kafka 插件不可加载")


@pytest.fixture(autouse=True)
def _fresh_discovery():
    reset_discovery()
    ensure_plugins_discovered()
    yield
    reset_discovery()


class TestSchemeRouting:
    """scheme -> 连接器插件路由."""

    @pytest.mark.parametrize(
        "uri,expected_name",
        [
            ("mongodb://host:27017/mydb", "mongo_connector"),
            ("mongodb+srv://cluster.example.com/mydb", "mongo_connector"),
            ("kafka://broker1:9092,broker2:9092/orders", "kafka_connector"),
            ("clickhouse://host:8123/db", "sql_connector"),
            ("clickhousedb://host:8123/db", "sql_connector"),
            ("hive://host:10000/default", "sql_connector"),
            ("spark://host:10000/default", "sql_connector"),
            ("presto://host:8080/hive/default", "sql_connector"),
            ("trino://host:8080/hive/default", "sql_connector"),
        ],
    )
    def test_routes_to_expected_connector(self, uri, expected_name):
        connector = find_connector(uri)
        assert connector is not None
        assert connector.name == expected_name

    def test_unknown_scheme_still_rejected(self):
        assert find_connector("nosuchproto://x") is None


class TestMongoHelpers:
    def test_db_name_parsing(self):
        from dqengine.plugins.builtin.mongo_connector import db_name_from_uri

        assert db_name_from_uri("mongodb://user:pass@host:27017/mydb?replicaSet=rs0") == "mydb"
        assert db_name_from_uri("mongodb+srv://cluster.example.com/db") == "db"
        assert db_name_from_uri("mongodb://host:27017") == ""  # 无库名

    def test_query_parsing(self):
        from dqengine.plugins.builtin.mongo_connector import parse_query

        assert parse_query(None) == {}
        assert parse_query("") == {}
        assert parse_query('{"age": {"$gt": 18}}') == {"age": {"$gt": 18}}
        with pytest.raises(ValueError, match="合法 JSON"):
            parse_query("{age: 18}")  # 非 JSON (键未引号)
        with pytest.raises(ValueError, match="JSON 对象"):
            parse_query("[1, 2]")

    def test_load_requires_collection(self):
        connector = find_connector("mongodb://host:27017/mydb")
        with pytest.raises(ValueError, match="collection"):
            connector.load("mongodb://host:27017/mydb")

    def test_load_requires_db_in_uri(self):
        connector = find_connector("mongodb://host:27017")
        with pytest.raises(ValueError, match="库名"):
            connector.load("mongodb://host:27017", table="coll")

    def test_load_rejects_bad_query_json(self):
        connector = find_connector("mongodb://host:27017/mydb")
        with pytest.raises(ValueError, match="合法 JSON"):
            connector.load("mongodb://host:27017/mydb", table="c", query="{bad")


class TestKafkaHelpers:
    def test_uri_parsing(self):
        from dqengine.plugins.builtin.kafka_connector import parse_kafka_uri

        brokers, topic = parse_kafka_uri("kafka://b1:9092,b2:9092/orders")
        assert brokers == ["b1:9092", "b2:9092"]
        assert topic == "orders"

    def test_uri_missing_broker(self):
        from dqengine.plugins.builtin.kafka_connector import parse_kafka_uri

        with pytest.raises(ValueError, match="broker"):
            parse_kafka_uri("kafka:///orders")

    def test_uri_missing_topic(self):
        from dqengine.plugins.builtin.kafka_connector import parse_kafka_uri

        with pytest.raises(ValueError, match="topic"):
            parse_kafka_uri("kafka://b1:9092/")

    def test_decode_json_message(self):
        from dqengine.plugins.builtin.kafka_connector import decode_message

        row = decode_message(b'{"user": {"id": 1}, "action": "click"}')
        assert row == {"user": {"id": 1}, "action": "click"}

    def test_decode_non_json_message(self):
        from dqengine.plugins.builtin.kafka_connector import decode_message

        assert decode_message(b"plain text") == {"value": "plain text"}
        # 非 dict JSON (数组/标量) 也不炸
        assert decode_message(b"[1,2]") == {"value": [1, 2]}
        assert decode_message(b"42") == {"value": 42}

    def test_decode_bad_utf8_fallback(self):
        from dqengine.plugins.builtin.kafka_connector import decode_message

        row = decode_message(b"\xff\xfe")
        assert "value" in row

    def test_load_table_overrides_uri_topic(self, monkeypatch):
        """--table 参数应覆盖 URI 路径中的 topic."""
        captured = {}

        class FakeConsumer:
            def __init__(self, topic, **kwargs):
                captured["topic"] = topic

            def __iter__(self):
                return iter([])

            def close(self):
                pass

        monkeypatch.setattr("kafka.KafkaConsumer", FakeConsumer)
        connector = find_connector("kafka://b1:9092/from_uri")
        connector.load("kafka://b1:9092/from_uri", table="from_table")
        assert captured["topic"] == "from_table"

    def test_load_empty_topic_result(self, monkeypatch):
        """无消息时返回空 DataFrame."""
        class FakeConsumer:
            def __init__(self, topic, **kwargs):
                pass

            def __iter__(self):
                return iter([])

            def close(self):
                pass

        monkeypatch.setattr("kafka.KafkaConsumer", FakeConsumer)
        connector = find_connector("kafka://b1:9092/t")
        df = connector.load("kafka://b1:9092/t")
        assert isinstance(df, pd.DataFrame)
        assert df.empty


class TestLoaderIntegration:
    def test_loader_end_to_end_kafka(self, monkeypatch):
        """DataLoader → 发现 → Kafka 连接器 → 消息展平 全链路 (打桩 broker)."""
        from collections import namedtuple

        FakeMsg = namedtuple("FakeMsg", ["value"])

        class FakeConsumer:
            def __init__(self, topic, **kwargs):
                pass

            def __iter__(self):
                return iter(
                    [FakeMsg(b'{"user": {"id": 7}, "action": "click"}'), FakeMsg(b"raw")]
                )

            def close(self):
                pass

        monkeypatch.setattr("kafka.KafkaConsumer", FakeConsumer)
        df = DataLoader().load("kafka://b1:9092/orders")
        assert len(df) == 2
        assert df["user.id"].iloc[0] == 7  # 嵌套展平
        assert df["value"].iloc[1] == "raw"  # 非 JSON 入 value 列

    def test_graceful_message_for_missing_scheme(self):
        with pytest.raises(ValueError, match="连接器插件"):
            DataLoader().load("weirdscheme://host/db")
