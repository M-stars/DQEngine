"""Missing value repair: mean imputation for numeric, mode for categorical."""

from __future__ import annotations

import pandas as pd

from dqengine.models.schemas import RepairResult


class MissingValueCleaner:
    """Fill missing values using column-type-aware strategies.

    - Numeric columns: fill with mean.
    - Categorical / object columns: fill with mode.
    - Other columns: fill with mode (fallback).

    Usage:
        cleaner = MissingValueCleaner()
        df_clean, result = cleaner.clean(df)
    """

    def clean(self, df: pd.DataFrame) -> tuple[pd.DataFrame, RepairResult]:
        """Fill missing values and return cleaned DataFrame with repair result.

        Args:
            df: Input DataFrame.

        Returns:
            Tuple of (cleaned DataFrame, RepairResult).
        """
        rows_before = len(df)
        df_clean = df.copy()
        changes = 0
        affected_cols = 0
        fill_details: dict[str, str] = {}

        for col in df_clean.columns:
            if df_clean[col].isna().sum() == 0:
                continue

            null_count = int(df_clean[col].isna().sum())
            fill_value = None

            if pd.api.types.is_numeric_dtype(df_clean[col]):
                fill_value = df_clean[col].mean()
                fill_details[col] = f"mean={fill_value:.2f}"
            else:
                mode_vals = df_clean[col].mode()
                if len(mode_vals) > 0:
                    fill_value = mode_vals[0]
                    fill_details[col] = f"mode={fill_value}"
                else:
                    fill_value = "MISSING"
                    fill_details[col] = "placeholder='MISSING'"

            df_clean[col] = df_clean[col].fillna(fill_value)
            changes += null_count
            affected_cols += 1

        result = RepairResult(
            operation="missing_value_fill",
            rows_before=rows_before,
            rows_after=len(df_clean),
            columns_affected=affected_cols,
            changes_made=changes,
            details=fill_details,
        )

        return df_clean, result
