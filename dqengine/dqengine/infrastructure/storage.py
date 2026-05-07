"""存储层 - SQLite / DuckDB / PostgreSQL (接口预留)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from dqengine.models.schemas import StorageType


class StorageManager:
    """统一存储管理器.

    支持:
    - SQLite: 本地轻量存储
    - DuckDB: 分析型存储
    - PostgreSQL: 生产级存储 (接口预留)

    Usage:
        store = StorageManager(StorageType.SQLITE, "dqengine.db")
        store.save_dataframe(df, "profiles")
        df = store.load_dataframe("profiles")
    """

    def __init__(
        self,
        storage_type: StorageType = StorageType.SQLITE,
        connection_string: str = "dqengine.db",
    ) -> None:
        self.storage_type = storage_type
        self.connection_string = connection_string
        self._conn: Any = None

    @property
    def connection(self) -> Any:
        if self._conn is None:
            self._conn = self._create_connection()
        return self._conn

    def _create_connection(self) -> Any:
        if self.storage_type == StorageType.SQLITE:
            conn = sqlite3.connect(self.connection_string)
            conn.row_factory = sqlite3.Row
            return conn
        elif self.storage_type == StorageType.DUCKDB:
            try:
                import duckdb
                return duckdb.connect(self.connection_string)
            except ImportError:
                raise ImportError("请安装 duckdb: pip install duckdb")
        elif self.storage_type == StorageType.POSTGRESQL:
            raise NotImplementedError("PostgreSQL 存储尚未实现")
        else:
            raise ValueError(f"不支持的存储类型: {self.storage_type}")

    def save_dataframe(self, df: pd.DataFrame, table_name: str, if_exists: str = "replace") -> None:
        """保存 DataFrame 到存储."""
        if self.storage_type == StorageType.SQLITE:
            conn = sqlite3.connect(self.connection_string)
            df.to_sql(table_name, conn, if_exists=if_exists, index=False)
            conn.close()
        elif self.storage_type == StorageType.DUCKDB:
            conn = self.connection
            conn.register("temp_df", df)
            conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM temp_df")
        else:
            raise NotImplementedError(f"存储类型 {self.storage_type} 的 save_dataframe 尚未实现")

    def load_dataframe(self, table_name: str) -> pd.DataFrame:
        """从存储加载 DataFrame."""
        if self.storage_type == StorageType.SQLITE:
            conn = sqlite3.connect(self.connection_string)
            df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
            conn.close()
            return df
        elif self.storage_type == StorageType.DUCKDB:
            conn = self.connection
            return conn.execute(f"SELECT * FROM {table_name}").df()
        else:
            raise NotImplementedError(f"存储类型 {self.storage_type} 的 load_dataframe 尚未实现")

    def execute(self, query: str, params: Optional[tuple] = None) -> Any:
        """执行 SQL 查询."""
        if self.storage_type == StorageType.SQLITE:
            conn = sqlite3.connect(self.connection_string)
            conn.row_factory = sqlite3.Row
            if params:
                result = conn.execute(query, params)
            else:
                result = conn.execute(query)
            conn.commit()
            rows = [dict(r) for r in result.fetchall()]
            conn.close()
            return rows
        else:
            return self.connection.execute(query).fetchall()

    def create_index(self, table_name: str, column: str) -> None:
        """创建索引."""
        if self.storage_type == StorageType.SQLITE:
            conn = sqlite3.connect(self.connection_string)
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{column} ON {table_name}({column})")
            conn.commit()
            conn.close()

    def close(self) -> None:
        """关闭连接."""
        if self._conn:
            self._conn.close()
            self._conn = None
