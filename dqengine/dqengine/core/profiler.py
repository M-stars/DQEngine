"""Data profiling engine - column-level statistics and analysis."""

from __future__ import annotations

import pandas as pd

from dqengine.models.schemas import ColumnProfile, ProfileResult


class Profiler:
    """Generate statistical profiles for DataFrames.

    Usage:
        profiler = Profiler()
        result = profiler.profile(df, file_path="data.csv")
    """

    def profile(self, df: pd.DataFrame, file_path: str = "") -> ProfileResult:
        """Profile all columns in a DataFrame.

        Args:
            df: Input DataFrame.
            file_path: Original file path for reference in the result.

        Returns:
            ProfileResult with row/column counts and per-column profiles.
        """
        columns = [self._profile_column(df, col) for col in df.columns]
        duplicate_count = df.duplicated().sum()
        total_cells = df.shape[0] * df.shape[1]

        return ProfileResult(
            file_path=file_path,
            row_count=len(df),
            column_count=len(df.columns),
            total_cells=total_cells,
            duplicate_row_count=int(duplicate_count),
            duplicate_row_rate=round(duplicate_count / max(len(df), 1), 4),
            memory_usage_mb=round(df.memory_usage(deep=True).sum() / (1024 * 1024), 2),
            columns=columns,
        )

    def _profile_column(self, df: pd.DataFrame, column: str) -> ColumnProfile:
        """Profile a single column."""
        series = df[column]
        total = len(series)
        non_null = int(series.count())
        null_count = int(series.isna().sum())
        null_rate = round(null_count / max(total, 1), 4)
        unique_count = int(series.nunique())
        unique_rate = round(unique_count / max(total, 1), 4)

        numeric_stats = self._numeric_stats(series)

        return ColumnProfile(
            column_name=str(column),
            dtype=str(series.dtype),
            total_count=total,
            non_null_count=non_null,
            null_count=null_count,
            null_rate=null_rate,
            unique_count=unique_count,
            unique_rate=unique_rate,
            **numeric_stats,
        )

    @staticmethod
    def _numeric_stats(series: pd.Series) -> dict:
        """Compute numeric statistics if applicable."""
        if not pd.api.types.is_numeric_dtype(series):
            return {
                "mean": None,
                "std": None,
                "min_val": None,
                "q25": None,
                "q50": None,
                "q75": None,
                "max_val": None,
            }
        desc = series.describe()

        def _num(key: str):
            # 可空 dtype (Int64/Float64) 的全空列, describe 返回 pd.NA,
            # float(pd.NA) 会抛 TypeError 中断整个画像
            value = desc.get(key)
            if value is None or pd.isna(value):
                return None
            return round(float(value), 2)

        return {
            "mean": _num("mean"),
            "std": _num("std"),
            "min_val": _num("min"),
            "q25": _num("25%"),
            "q50": _num("50%"),
            "q75": _num("75%"),
            "max_val": _num("max"),
        }
