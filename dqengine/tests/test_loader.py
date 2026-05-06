"""Tests for the DataLoader module."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from dqengine.core.loader import DataLoader

SAMPLE_CSV = Path(__file__).parent.parent / "examples" / "sample.csv"


class TestDataLoader:
    def test_load_csv_utf8(self, tmp_path: Path) -> None:
        """Load a UTF-8 CSV file."""
        file = tmp_path / "test.csv"
        file.write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")

        loader = DataLoader()
        df = loader.load(file)
        assert isinstance(df, pd.DataFrame)
        assert df.shape == (2, 3)
        assert list(df.columns) == ["a", "b", "c"]

    def test_load_sample_csv(self) -> None:
        """Load the sample.csv file included in the project."""
        loader = DataLoader()
        df = loader.load(SAMPLE_CSV)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 25
        assert len(df.columns) == 8

    def test_load_csv_gbk(self, tmp_path: Path) -> None:
        """Load a GBK-encoded CSV with fallback."""
        content = "姓名,年龄\n张三,25\n李四,30\n"
        file = tmp_path / "gbk_test.csv"
        file.write_text(content, encoding="gbk")

        loader = DataLoader()
        df = loader.load(file)
        assert df.shape == (2, 2)

    def test_file_not_found(self) -> None:
        """Raise FileNotFoundError for missing files."""
        loader = DataLoader()
        with pytest.raises(FileNotFoundError):
            loader.load("/nonexistent/path.csv")

    def test_unsupported_format(self, tmp_path: Path) -> None:
        """Raise ValueError for unsupported formats."""
        file = tmp_path / "data.json"
        file.write_text("{}")
        loader = DataLoader()
        with pytest.raises(ValueError, match="Unsupported"):
            loader.load(file)

    def test_load_excel(self, tmp_path: Path) -> None:
        """Load an Excel file."""
        file = tmp_path / "test.xlsx"
        df_in = pd.DataFrame({"x": [1, 2, 3], "y": ["a", "b", "c"]})
        df_in.to_excel(file, index=False)

        loader = DataLoader()
        df = loader.load(file)
        assert df.shape == (3, 2)
