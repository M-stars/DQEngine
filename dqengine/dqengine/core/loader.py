"""Data loading module with automatic encoding detection."""

from __future__ import annotations

from pathlib import Path
from typing import Union

import pandas as pd


class DataLoader:
    """Load CSV and Excel files with automatic encoding detection.

    Usage:
        loader = DataLoader()
        df = loader.load("data.csv")
    """

    ENCODINGS = ["utf-8", "gbk", "gb2312", "latin-1", "iso-8859-1"]

    def load(self, file_path: "str | Path") -> pd.DataFrame:
        """Load a file into a pandas DataFrame.

        Args:
            file_path: Path to a .csv or .xlsx/.xls file.

        Returns:
            DataFrame with the loaded data.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file format is not supported.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        suffix = path.suffix.lower()
        if suffix == ".csv":
            return self._load_csv(path)
        elif suffix in (".xlsx", ".xls"):
            return self._load_excel(path)
        else:
            raise ValueError(
                f"Unsupported file format: {suffix}. Supported: .csv, .xlsx, .xls"
            )

    def _load_csv(self, path: Path) -> pd.DataFrame:
        """Load CSV with automatic encoding fallback."""
        for encoding in self.ENCODINGS:
            try:
                df = pd.read_csv(path, encoding=encoding)
                return df
            except (UnicodeDecodeError, UnicodeError):
                continue
        raise ValueError(
            f"Could not decode {path} with any encoding: {self.ENCODINGS}"
        )

    def _load_excel(self, path: Path) -> pd.DataFrame:
        """Load Excel file."""
        return pd.read_excel(path)
