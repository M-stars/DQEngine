"""内置插件: SQLAlchemy 通用 SQL 数据库连接器.

依赖可选: 未安装 sqlalchemy 时本模块 import 即失败,
PluginRegistry 会跳过该插件, 核心文件加载不受影响.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from dqengine.models.schemas import PluginInfo, PluginType
from dqengine.plugins.base import BaseConnector
from dqengine.utils.logger import get_logger

logger = get_logger(__name__)


class SqlConnector(BaseConnector):
    """通用 SQL 连接器 — 通过 sqlalchemy 接入 PostgreSQL/MySQL/SQLite 等.

    用法:
        - 表模式: ``dq profile postgresql://user:pass@host:5432/db --table users``
        - 查询模式: ``dq profile postgresql://... --query "SELECT ..."``

    取数只读 (SELECT), 不向数据源写入任何内容.
    """

    PLUGIN_INFO = PluginInfo(
        name="sql_connector",
        plugin_type=PluginType.LOADER,
        version="0.1.0",
        description="SQL 数据库连接器 (postgresql/mysql/sqlite/mssql/oracle), 依赖 sqlalchemy",
        dependencies=["sqlalchemy"],
    )

    SCHEMES = ("postgresql", "postgres", "mysql", "mariadb", "sqlite", "mssql", "oracle")

    def load(
        self,
        uri: str,
        table: Optional[str] = None,
        query: Optional[str] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """从数据库加载表或查询结果.

        Args:
            uri: sqlalchemy 连接串 (日志中密码始终脱敏).
            table: 表名 (与 query 二选一; 仅支持纯表名, 带 schema 前缀请用 query).
            query: SQL 查询语句, 优先于 table; 大结果集请自行加 LIMIT.
            **kwargs: ``limit`` 用于表模式限制行数 (方言无关),
                其余参数透传给 pd.read_sql.

        Returns:
            DataFrame.

        Raises:
            ImportError: 未安装 sqlalchemy.
            ValueError: table 与 query 均未提供.
        """
        try:
            from sqlalchemy import MetaData, Table, create_engine, select, text
            from sqlalchemy.engine import make_url
        except ImportError:
            raise ImportError(
                'SQL 连接器需要 sqlalchemy: pip install "dqengine[db]" '
                '(PostgreSQL 驱动: pip install "dqengine[postgres]", '
                'MySQL 驱动: pip install "dqengine[mysql]")'
            )

        try:
            safe_uri = make_url(uri).render_as_string(hide_password=True)
        except Exception:
            safe_uri = "<无法解析的连接串>"

        limit = kwargs.pop("limit", None)
        if not query and not table:
            raise ValueError(f"数据源 {safe_uri} 未指定表名或查询, 请通过 --table / --query 提供")

        logger.info("数据库连接: %s (模式: %s)", safe_uri, "查询" if query else f"表 {table}")
        engine = create_engine(uri)
        try:
            if query is not None:
                if limit is not None:
                    logger.warning(
                        "limit 仅在表模式下生效, 查询模式请直接在 SQL 中使用 LIMIT/TOP"
                    )
                df = pd.read_sql(text(query), engine, **kwargs)
            else:
                # 方言无关的表读取: 表名经元数据反射参数化, 无拼接注入面
                tbl = Table(table, MetaData(), autoload_with=engine)
                stmt = select(tbl)
                if limit is not None:
                    stmt = stmt.limit(int(limit))
                df = pd.read_sql(stmt, engine, **kwargs)
        finally:
            engine.dispose()

        logger.info("数据库加载完成: %d 行 x %d 列", len(df), len(df.columns))
        return df
