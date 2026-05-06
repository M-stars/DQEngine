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
        return {
            "mean": round(float(desc.get("mean", 0)), 2) if "mean" in desc else None,
            "std": round(float(desc.get("std", 0)), 2) if "std" in desc else None,
            "min_val": round(float(desc.get("min", 0)), 2) if "min" in desc else None,
            "q25": round(float(desc.get("25%", 0)), 2) if "25%" in desc else None,
            "q50": round(float(desc.get("50%", 0)), 2) if "50%" in desc else None,
            "q75": round(float(desc.get("75%", 0)), 2) if "75%" in desc else None,
            "max_val": round(float(desc.get("max", 0)), 2) if "max" in desc else None,
        }
