"""数据库连接器插件测试 (SQL 连接器 + URI 路由).

依赖 sqlalchemy; 未安装时跳过.
"""

import logging

import pandas as pd
import pytest

from dqengine.core.loader import DataLoader
from dqengine.plugins.discovery import (
    ensure_plugins_discovered,
    find_connector,
    reset_discovery,
)

sqlalchemy = pytest.importorskip("sqlalchemy")


@pytest.fixture(scope="module")
def sqlite_db(tmp_path_factory):
    """建一个含两表的 SQLite 库, 返回库文件路径."""
    import sqlite3

    path = tmp_path_factory.mktemp("db") / "test.db"
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE users (id INTEGER, name TEXT, age INTEGER)")
    conn.executemany(
        "INSERT INTO users VALUES (?, ?, ?)",
        [(1, "张三", 25), (2, "李四", None), (3, "王五", 40)],
    )
    conn.execute("CREATE TABLE orders (id INTEGER, amount REAL)")
    conn.execute("INSERT INTO orders VALUES (1, 9.9)")
    conn.commit()
    conn.close()
    return path


@pytest.fixture(autouse=True)
def _fresh_discovery():
    """每个用例重置发现缓存, 避免跨用例的注册状态串扰."""
    reset_discovery()
    yield
    reset_discovery()


@pytest.fixture(scope="module")
def connector(sqlite_db):
    ensure_plugins_discovered()
    return find_connector("sqlite://")


class TestSqlConnector:
    def test_query_mode(self, connector):
        df = connector.load("sqlite://", query="SELECT 1 AS x, 'a' AS y")
        assert list(df.columns) == ["x", "y"]
        assert len(df) == 1

    def test_table_mode(self, connector, sqlite_db):
        df = connector.load(f"sqlite:///{sqlite_db}", table="users")
        assert len(df) == 3
        assert list(df.columns) == ["id", "name", "age"]

    def test_table_mode_limit(self, connector, sqlite_db):
        df = connector.load(f"sqlite:///{sqlite_db}", table="users", limit=2)
        assert len(df) == 2

    def test_query_precedence_over_table(self, connector, sqlite_db):
        df = connector.load(
            f"sqlite:///{sqlite_db}",
            table="users",
            query="SELECT COUNT(*) AS n FROM orders",
        )
        assert df["n"].iloc[0] == 1

    def test_no_table_no_query_raises(self, connector, sqlite_db):
        with pytest.raises(ValueError, match="未指定表名或查询"):
            connector.load(f"sqlite:///{sqlite_db}")

    def test_password_never_logged_on_error(self, connector):
        """带密码连接失败时, 密码不得出现在任何日志记录中."""
        records: list = []
        handler = logging.Handler()
        handler.emit = lambda rec: records.append(rec.getMessage())
        # 插件模块在注册表中以别名加载, logger 名可能是包路径或插件别名
        loggers = [
            logging.getLogger("dqengine.plugins.builtin.sql_connector"),
            logging.getLogger("dqengine_plugin_sql_connector"),
        ]
        old_levels = [lg.level for lg in loggers]
        for lg in loggers:
            lg.addHandler(handler)
            lg.setLevel(logging.DEBUG)
        try:
            with pytest.raises(Exception):
                connector.load("postgresql://user:secretpw@localhost:1/db", table="t")
        finally:
            for lg, lvl in zip(loggers, old_levels):
                lg.removeHandler(handler)
                lg.setLevel(lvl)
        assert not any("secretpw" in msg for msg in records)

    def test_safe_uri_logged(self, connector):
        """连接日志只出现脱敏连接串 (主机可见, 密码不可见)."""
        records: list = []
        handler = logging.Handler()
        handler.emit = lambda rec: records.append(rec.getMessage())
        loggers = [
            logging.getLogger("dqengine.plugins.builtin.sql_connector"),
            logging.getLogger("dqengine_plugin_sql_connector"),
        ]
        for lg in loggers:
            lg.addHandler(handler)
        try:
            with pytest.raises(Exception):
                connector.load("postgresql://user:secretpw@localhost:1/db", table="t")
        finally:
            for lg in loggers:
                lg.removeHandler(handler)
        assert any("secretpw" not in m and "postgresql://user" in m for m in records)


class TestLoaderUriRouting:
    def test_loader_routes_uri_to_connector(self, sqlite_db):
        df = DataLoader().load(f"sqlite:///{sqlite_db}", table_name="users")
        assert len(df) == 3

    def test_loader_unknown_scheme_helpful_error(self):
        with pytest.raises(ValueError, match="连接器插件"):
            DataLoader().load("nosuchproto://x/y", table_name="t")

    def test_file_loading_unaffected(self, tmp_path):
        """URI 路由不得影响普通文件路径加载."""
        f = tmp_path / "data.csv"
        pd.DataFrame({"a": [1, 2]}).to_csv(f, index=False)
        df = DataLoader().load(f)
        assert len(df) == 2

    def test_windows_path_not_treated_as_uri(self, tmp_path):
        """单字母盘符路径 (C:/...) 不满足 scheme:// 形态, 走文件加载."""
        f = tmp_path / "data.csv"
        pd.DataFrame({"a": [1]}).to_csv(f, index=False)
        assert len(DataLoader().load(str(f))) == 1


class TestCustomConnectorPlugin:
    def test_custom_scheme_plugin_routing(self, tmp_path):
        """用户自定义连接器插件放入 plugins/ 目录即可按 scheme 路由."""
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "my_proto.py").write_text(
            '''
from typing import Optional
import pandas as pd
from dqengine.models.schemas import PluginInfo, PluginType
from dqengine.plugins.base import BaseConnector


class MyProtoConnector(BaseConnector):
    PLUGIN_INFO = PluginInfo(
        name="my_proto_connector",
        plugin_type=PluginType.LOADER,
        description="测试自定义协议",
    )
    SCHEMES = ("myproto",)

    def load(self, uri, table=None, query=None, **kwargs):
        return pd.DataFrame({"uri": [uri], "table": [table]})
''',
            encoding="utf-8",
        )

        import os

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            loader = DataLoader()
            df = loader.load("myproto://host/db", table_name="t1")
            assert df["table"].iloc[0] == "t1"
            assert df["uri"].iloc[0] == "myproto://host/db"
        finally:
            os.chdir(old_cwd)
