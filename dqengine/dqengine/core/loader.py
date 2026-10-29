"""数据加载模块 - 支持 CSV / Excel / JSON / Parquet / SQLite."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from dqengine.utils.logger import get_logger

logger = get_logger(__name__)


class DataLoader:
    """多数据源加载器.

    支持格式:
        - CSV (自动编码检测)
        - Excel (.xlsx, .xls)
        - JSON (.json)
        - Parquet (.parquet)
        - SQLite (.db, .sqlite, .sqlite3) — 需 sqlalchemy

    使用方式:
        loader = DataLoader()
        df = loader.load("data.csv")
    """

    # gb2312 是 gbk 的子集, gbk 失败后 gb2312 必失败, 不重复尝试;
    # 不放 latin-1/iso-8859-1: 单字节编码对任意字节序列都合法,
    # 会让坏 UTF-8 文件被静默 mojibake 读入而不报错
    ENCODINGS = ["utf-8", "gbk", "utf-16"]

    def load(
        self,
        file_path: "str | Path",
        table_name: Optional[str] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """加载文件到 DataFrame.

        Args:
            file_path: 文件路径.
            table_name: 对于数据库文件, 指定表名.
            **kwargs: 传递给底层 pandas 读取函数的额外参数.

        Returns:
            DataFrame.

        Raises:
            FileNotFoundError: 文件不存在.
            ValueError: 不支持的格式.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件未找到: {path}")

        suffix = path.suffix.lower()

        if suffix == ".csv":
            return self.load_csv(path, **kwargs)
        elif suffix in (".xlsx", ".xls"):
            return self.load_excel(path, **kwargs)
        elif suffix == ".json":
            return self.load_json(path, **kwargs)
        elif suffix == ".parquet":
            return self.load_parquet(path, **kwargs)
        elif suffix in (".db", ".sqlite", ".sqlite3"):
            return self.load_sqlite(path, table_name=table_name, **kwargs)
        else:
            raise ValueError(
                f"不支持的文件格式: {suffix}. 支持: .csv, .xlsx, .xls, .json, .parquet, .db, .sqlite"
            )

    def load_csv(self, path: Path, **kwargs) -> pd.DataFrame:
        """加载 CSV 文件 (自动编码检测).

        Args:
            path: CSV 文件路径.
            **kwargs: 传递给 pd.read_csv 的参数.

        Returns:
            DataFrame.
        """
        # 用户显式指定 encoding 时不再走自动探测,
        # 且必须从 kwargs 中取出, 否则与位置参数重复必抛 TypeError
        user_encoding = kwargs.pop("encoding", None)
        encodings = [user_encoding] if user_encoding else self.ENCODINGS

        # 先用 64KB 样本预探测编码, 命中后只全量读一次;
        # 盲试编码在最坏情况下每个候选都完整解析一遍
        # (69MB 文件每次约 1.2s), 解码错误出现得晚时浪费巨大
        if user_encoding is None:
            try:
                with open(path, "rb") as f:
                    head = f.read(65536)
                for encoding in encodings:
                    try:
                        head.decode(encoding)
                        encodings = [encoding] + [e for e in encodings if e != encoding]
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
            except OSError:
                pass

        last_error: Exception = None
        for encoding in encodings:
            try:
                df = pd.read_csv(path, encoding=encoding, **kwargs)
                logger.debug("CSV 加载成功: %s (编码: %s)", path.name, encoding)
                return df
            except (UnicodeDecodeError, UnicodeError) as e:
                # 样本之外才失败的情形仍走全量重试兜底
                last_error = e
                continue
        raise ValueError(f"无法解码 {path.name}, 尝试编码: {encodings}") from last_error

    def load_excel(self, path: Path, **kwargs) -> pd.DataFrame:
        """加载 Excel 文件.

        Args:
            path: Excel 文件路径.
            **kwargs: 传递给 pd.read_excel 的参数.

        Returns:
            DataFrame.
        """
        logger.debug("Excel 加载: %s", path.name)
        return pd.read_excel(path, **kwargs)

    def load_json(self, path: Path, **kwargs) -> pd.DataFrame:
        """加载 JSON 文件.

        Args:
            path: JSON 文件路径.
            **kwargs: 传递给 pd.read_json 的参数.

        Returns:
            DataFrame.
        """
        logger.debug("JSON 加载: %s", path.name)
        try:
            return pd.read_json(path, **kwargs)
        except ValueError:
            # 逐行 JSON (NDJSON/JSON Lines) 以 .json 后缀保存是常见形态,
            # 标准 json 解析会报 "Trailing data", 回退按行解析
            try:
                return pd.read_json(path, lines=True, **kwargs)
            except ValueError:
                raise

    def load_parquet(self, path: Path, **kwargs) -> pd.DataFrame:
        """加载 Parquet 文件.

        Args:
            path: Parquet 文件路径.
            **kwargs: 传递给 pd.read_parquet 的参数.

        Returns:
            DataFrame.
        """
        logger.debug("Parquet 加载: %s", path.name)
        try:
            return pd.read_parquet(path, **kwargs)
        except ImportError:
            raise ImportError("需要安装 pyarrow 来读取 Parquet 文件: pip install pyarrow")

    def load_sqlite(self, path: Path, table_name: Optional[str] = None, **kwargs) -> pd.DataFrame:
        """加载 SQLite 数据库表.

        Args:
            path: 数据库文件路径.
            table_name: 表名 (必须提供).
            **kwargs: 传递给 pd.read_sql 的参数.

        Returns:
            DataFrame.

        Raises:
            ValueError: 未提供表名.
        """
        import sqlite3

        if not table_name:
            # 尝试获取第一个表名
            conn = sqlite3.connect(str(path))
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()

            if not tables:
                raise ValueError(f"SQLite 数据库 {path.name} 中未找到任何表")
            if len(tables) == 1:
                table_name = tables[0]
                logger.info("自动选择表: %s", table_name)
            else:
                raise ValueError(
                    f"数据库包含多个表: {tables}. 请通过 table_name 参数指定."
                )

        logger.debug("SQLite 加载: %s -> 表: %s", path.name, table_name)

        conn = sqlite3.connect(str(path))
        try:
            df = pd.read_sql(f'SELECT * FROM "{table_name}"', conn, **kwargs)
        finally:
            conn.close()
        return df

    def load_bytes(self, content: bytes, file_name: str, **kwargs) -> pd.DataFrame:
        """从内存字节加载 DataFrame (供 API 上传等场景免落盘).

        Args:
            content: 文件字节内容.
            file_name: 原始文件名 (用于识别格式).
            **kwargs: 传递给底层 pandas 读取函数的额外参数.

        Returns:
            DataFrame.

        Raises:
            ValueError: 不支持的格式或无法解码.
        """
        import io

        suffix = Path(file_name).suffix.lower()
        if suffix == ".csv":
            # 与 load_csv 相同的编码探测, 但作用于内存字节
            user_encoding = kwargs.pop("encoding", None)
            encodings = [user_encoding] if user_encoding else self.ENCODINGS
            if user_encoding is None:
                head = content[:65536]
                for encoding in encodings:
                    try:
                        head.decode(encoding)
                        encodings = [encoding] + [e for e in encodings if e != encoding]
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
            last_error: Exception = None
            for encoding in encodings:
                try:
                    return pd.read_csv(io.BytesIO(content), encoding=encoding, **kwargs)
                except (UnicodeDecodeError, UnicodeError) as e:
                    last_error = e
                    continue
            raise ValueError(f"无法解码 {file_name}, 尝试编码: {encodings}") from last_error
        elif suffix in (".xlsx", ".xls"):
            return pd.read_excel(io.BytesIO(content), **kwargs)
        elif suffix == ".json":
            try:
                return pd.read_json(io.BytesIO(content), **kwargs)
            except ValueError:
                return pd.read_json(io.BytesIO(content), lines=True, **kwargs)
        elif suffix == ".parquet":
            return pd.read_parquet(io.BytesIO(content), **kwargs)
        else:
            raise ValueError(f"不支持的文件格式: {suffix} (支持 csv/xlsx/json/parquet)")

    def detect_format(self, file_path: "str | Path") -> str:
        """检测文件格式.

        Args:
            file_path: 文件路径.

        Returns:
            格式标识: csv, excel, json, parquet, sqlite.
        """
        path = Path(file_path)
        suffix = path.suffix.lower()
        mapping = {
            ".csv": "csv",
            ".xlsx": "excel",
            ".xls": "excel",
            ".json": "json",
            ".parquet": "parquet",
            ".db": "sqlite",
            ".sqlite": "sqlite",
            ".sqlite3": "sqlite",
        }
        return mapping.get(suffix, "unknown")
