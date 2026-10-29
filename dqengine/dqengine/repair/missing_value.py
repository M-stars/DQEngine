"""Missing value repair: mean imputation for numeric, mode for categorical."""

from __future__ import annotations

import pandas as pd

from dqengine.models.schemas import RepairResult


class MissingValueCleaner:
    """Fill missing values using column-type-aware strategies.

    Strategies:
        - mean:     numeric columns -> mean, others -> mode (default).
        - median:   numeric columns -> median, others -> mode.
        - mode:     all columns -> mode (fallback placeholder "MISSING").
        - drop:     drop any row containing a missing value.
        - constant: fill every column with ``constant_value``.

    Usage:
        cleaner = MissingValueCleaner()
        df_clean, result = cleaner.clean(df, strategy="median")
    """

    def clean(
        self,
        df: pd.DataFrame,
        strategy: str = "mean",
        constant_value: "str | None" = None,
    ) -> tuple[pd.DataFrame, RepairResult]:
        """Fill missing values and return cleaned DataFrame with repair result.

        Args:
            df: Input DataFrame.
            strategy: One of "mean", "median", "mode", "drop", "constant".
            constant_value: Fill value used by the "constant" strategy.

        Returns:
            Tuple of (cleaned DataFrame, RepairResult).
        """
        rows_before = len(df)

        if strategy == "drop":
            df_clean = df.dropna().copy()
            dropped = rows_before - len(df_clean)
            details = {
                col: f"dropped rows with nulls ({int(df[col].isna().sum())} nulls)"
                for col in df.columns
                if df[col].isna().any()
            }
            result = RepairResult(
                operation="missing_value_fill",
                rows_before=rows_before,
                rows_after=len(df_clean),
                columns_affected=len(details),
                changes_made=dropped,
                details=details,
            )
            return df_clean, result

        if strategy not in ("mean", "median", "mode", "constant"):
            raise ValueError(
                f"未知的缺失值策略: {strategy!r} (可选: mean, median, mode, drop, constant)"
            )

        df_clean = df.copy()
        changes = 0
        affected_cols = 0
        fill_details: dict[str, str] = {}

        for col in df_clean.columns:
            null_count = int(df_clean[col].isna().sum())
            if null_count == 0:
                continue

            fill_value = None

            if strategy == "constant":
                if pd.api.types.is_numeric_dtype(df_clean[col]):
                    try:
                        fill_value = (
                            float(constant_value) if constant_value is not None else None
                        )
                    except (TypeError, ValueError):
                        fill_details[col] = (
                            f"skipped: constant {constant_value!r} not valid for numeric column"
                        )
                        continue
                else:
                    fill_value = constant_value if constant_value is not None else "MISSING"
                fill_details[col] = f"constant={fill_value}"
            elif strategy == "mode":
                mode_vals = df_clean[col].mode()
                if len(mode_vals) > 0:
                    fill_value = mode_vals[0]
                    fill_details[col] = f"mode={fill_value}"
                else:
                    fill_value = "MISSING"
                    fill_details[col] = "placeholder='MISSING'"
            elif pd.api.types.is_numeric_dtype(df_clean[col]):
                if strategy == "median":
                    fill_value = df_clean[col].median()
                    fill_details[col] = f"median={fill_value:.2f}"
                else:
                    fill_value = df_clean[col].mean()
                    fill_details[col] = f"mean={fill_value:.2f}"
            else:
                # mean/median strategy on a non-numeric column falls back to mode
                mode_vals = df_clean[col].mode()
                if len(mode_vals) > 0:
                    fill_value = mode_vals[0]
                    fill_details[col] = f"mode={fill_value}"
                else:
                    fill_value = "MISSING"
                    fill_details[col] = "placeholder='MISSING'"

            if fill_value is None or pd.isna(fill_value):
                # No valid fill value computable (e.g. all-null column).
                fill_details[col] = "skipped: no valid values to compute fill"
                continue

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
