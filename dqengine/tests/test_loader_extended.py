"""多数据源加载器测试."""

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from dqengine.core.loader import DataLoader


class TestDataLoaderExtended:
    """多数据源加载器测试."""

    @pytest.fixture
    def loader(self):
        return DataLoader()

    def test_load_json(self, loader):
        """测试加载JSON."""
        data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f, ensure_ascii=False)
            json_path = f.name

        try:
            df = loader.load(json_path)
            assert len(df) == 2
            assert list(df.columns) == ["name", "age"]
        finally:
            os.unlink(json_path)

    def test_load_json_with_kwargs(self, loader):
        """测试加载JSON (带参数)."""
        import json
        data = {"users": [{"name": "Alice"}, {"name": "Bob"}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            json_path = f.name

        try:
            # orient="records" is the default for list-like JSON
            pass
        finally:
            os.unlink(json_path)

    def test_detect_csv_format(self, loader):
        """测试检测CSV格式."""
        assert loader.detect_format("data.csv") == "csv"

    def test_detect_excel_format(self, loader):
        """测试检测Excel格式."""
        assert loader.detect_format("data.xlsx") == "excel"
        assert loader.detect_format("data.xls") == "excel"

    def test_detect_json_format(self, loader):
        """测试检测JSON格式."""
        assert loader.detect_format("data.json") == "json"

    def test_detect_parquet_format(self, loader):
        """测试检测Parquet格式."""
        assert loader.detect_format("data.parquet") == "parquet"

    def test_detect_sqlite_format(self, loader):
        """测试检测SQLite格式."""
        assert loader.detect_format("data.db") == "sqlite"
        assert loader.detect_format("data.sqlite") == "sqlite"

    def test_detect_unknown_format(self, loader):
        """测试检测未知格式."""
        assert loader.detect_format("data.txt") == "unknown"

    def test_invalid_file_not_found(self, loader):
        """测试文件不存在."""
        with pytest.raises(FileNotFoundError):
            loader.load("nonexistent_file.csv")

    def test_invalid_format(self, loader):
        """测试不支持的文件格式."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            txt_path = f.name

        try:
            with pytest.raises(ValueError, match="不支持"):
                loader.load(txt_path)
        finally:
            os.unlink(txt_path)


class TestDataLoaderCSV:
    """CSV加载测试 (保持向后兼容)."""

    @pytest.fixture
    def loader(self):
        return DataLoader()

    @pytest.fixture
    def sample_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,age,email\nAlice,30,alice@test.com\nBob,25,bob@test.com\n")
            csv_path = f.name

        yield csv_path
        os.unlink(csv_path)

    def test_load_csv(self, loader, sample_csv):
        """测试加载CSV."""
        df = loader.load(sample_csv)
        assert len(df) == 2
        assert "name" in df.columns
        assert "age" in df.columns
        assert "email" in df.columns
