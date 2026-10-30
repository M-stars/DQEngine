"""内置插件: MongoDB 文档库连接器.

URI 语义:
    - ``table`` 参数 = collection 名 (必须)
    - ``query`` 参数 = JSON 过滤条件 (MongoDB 查询语法, 可省略)
    - 连接串须包含库名: ``mongodb://host:27017/mydb``

嵌套文档经 pd.json_normalize 展平为 ``a.b.c`` 形式的列;
``_id`` 等 ObjectId 统一转字符串, 保证后续画像/报告可序列化.

依赖可选: 未安装 pymongo 时本模块 import 即失败,
PluginRegistry 会跳过该插件, 不影响核心功能.
"""

from __future__ import annotations

import json
from typing import Optional

import pandas as pd
from urllib.parse import urlparse

from dqengine.models.schemas import PluginInfo, PluginType
from dqengine.plugins.base import BaseConnector
from dqengine.utils.logger import get_logger

logger = get_logger(__name__)


def db_name_from_uri(uri: str) -> str:
    """从 MongoDB 连接串解析库名 (纯函数, 便于测试).

    Args:
        uri: ``mongodb://host[:port]/db`` 或 ``mongodb+srv://host/db``.

    Returns:
        库名; 连接串未包含库名时为空字符串.
    """
    path = urlparse(uri).path
    return path.lstrip("/").split("?", 1)[0]


def parse_query(query: Optional[str]) -> dict:
    """解析 JSON 过滤条件 (纯函数, 便于测试).

    Args:
        query: MongoDB 查询 JSON 字符串 (如 ``{"age": {"$gt": 18}}``), 可为 None.

    Returns:
        查询字典.

    Raises:
        ValueError: query 不是合法 JSON 对象.
    """
    if not query:
        return {}
    try:
        parsed = json.loads(query)
    except json.JSONDecodeError as e:
        raise ValueError(f"MongoDB 查询必须是合法 JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError("MongoDB 查询必须是 JSON 对象, 如 {\"age\": {\"$gt\": 18}}")
    return parsed


class MongoConnector(BaseConnector):
    """MongoDB 连接器 — collection 取数, JSON 过滤, 嵌套文档展平."""

    PLUGIN_INFO = PluginInfo(
        name="mongo_connector",
        plugin_type=PluginType.LOADER,
        version="0.1.0",
        description="MongoDB 文档库连接器 (collection→表, JSON 过滤, 嵌套展平), 依赖 pymongo",
        dependencies=["pymongo"],
    )

    SCHEMES = ("mongodb", "mongodb+srv")

    def load(
        self,
        uri: str,
        table: Optional[str] = None,
        query: Optional[str] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """从 MongoDB collection 加载文档.

        Args:
            uri: 连接串 (须含库名; 密码日志脱敏).
            table: collection 名 (必须).
            query: JSON 过滤条件字符串 (MongoDB 查询语法).
            **kwargs: ``limit`` 限制文档数; ``timeout_ms`` 服务器选择超时
                (缺省 10000); 其余参数保留.

        Returns:
            DataFrame (嵌套文档已展平, ObjectId 已转字符串).

        Raises:
            ImportError: 未安装 pymongo.
            ValueError: 未指定 collection / 库名缺失 / query 非法 JSON.
        """
        try:
            from pymongo import MongoClient
            from bson import ObjectId
        except ImportError:
            raise ImportError(
                'MongoDB 连接器需要 pymongo: pip install "dqengine[mongo]"'
            )

        limit = kwargs.pop("limit", None)
        timeout_ms = kwargs.pop("timeout_ms", 10000)
        if query is not None:
            logger.warning("MongoDB 连接器中 --query 为 JSON 过滤条件, 非 SQL")

        if not table:
            raise ValueError(
                "MongoDB 连接需指定 collection, 请通过 --table 提供 "
                "(格式: dq profile \"mongodb://host/db\" --table mycoll)"
            )
        db_name = db_name_from_uri(uri)
        if not db_name:
            raise ValueError(
                f"MongoDB 连接串需包含库名: mongodb://host[:port]/<db> (当前: {table} 无库可寻)"
            )

        filt = parse_query(query)

        import re

        # 密码脱敏: 凭据段 (user:pass@) 替换后再落日志
        safe_uri = re.sub(r"//([^/@:]+):([^@]+)@", r"//\1:***@", uri)
        logger.info("MongoDB 连接: %s, 库 %s, collection %s", safe_uri, db_name, table)

        client = MongoClient(uri, serverSelectionTimeoutMS=int(timeout_ms))
        try:
            cursor = client[db_name][table].find(filt)
            if limit is not None:
                cursor = cursor.limit(int(limit))
            docs = list(cursor)
        finally:
            client.close()

        logger.info("MongoDB 加载完成: %d 条文档", len(docs))
        if not docs:
            return pd.DataFrame()

        df = pd.json_normalize(docs)
        if "_id" in df.columns:
            df["_id"] = df["_id"].astype(str)
        # 嵌套文档内嵌的 ObjectId (展平后列名任意) 统一字符串化
        for col in df.columns:
            if df[col].map(lambda v: isinstance(v, ObjectId)).any():
                df[col] = df[col].astype(str)
        return df
