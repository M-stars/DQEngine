"""Date column detection and standardization to YYYY-MM-DD format."""

from __future__ import annotations

import warnings

import pandas as pd

from dqengine.models.schemas import RepairResult


class DateStandardizer:
    """Auto-detect date columns and standardize to YYYY-MM-DD.

    Usage:
        standardizer = DateStandardizer()
        df_clean, result = standardizer.standardize(df)
    """

    DATE_PATTERNS = ["date", "time", "dt", "created", "updated", "birth", "day"]

    def standardize(
        self, df: pd.DataFrame, target_format: str = "%Y-%m-%d"
    ) -> tuple[pd.DataFrame, RepairResult]:
        """Detect and normalize date columns.

        Args:
            df: Input DataFrame.
            target_format: Desired output date format.

        Returns:
            Tuple of (standardized DataFrame, RepairResult).
        """
        rows_before = len(df)
        df_clean = df.copy()
        changes = 0
        affected_cols = 0
        details: dict[str, str] = {}

        candidates = self._detect_date_columns(df_clean)

        for col in candidates:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    converted = pd.to_datetime(df_clean[col], errors="coerce")
                converted_str = converted.dt.strftime(target_format)
                valid_before = df_clean[col].notna().sum()
                valid_after = converted.notna().sum()

                # Only apply when conversion preserves every previously valid
                # value; coercing unparseable values would silently null them.
                if valid_before > 0 and valid_after >= valid_before:
                    changed_mask = converted.notna() & (
                        df_clean[col].astype(str) != converted_str
                    )
                    changed = int(changed_mask.sum())
                    if changed > 0:
                        df_clean[col] = converted_str
                        changes += changed
                        affected_cols += 1
                        details[col] = (
                            f"standardized {changed}/{rows_before} values to {target_format}"
                        )
            except (ValueError, TypeError):
                continue

        result = RepairResult(
            operation="date_standardization",
            rows_before=rows_before,
            rows_after=len(df_clean),
            columns_affected=affected_cols,
            changes_made=changes,
            details=details,
        )

        return df_clean, result

    def _detect_date_columns(self, df: pd.DataFrame) -> list[str]:
        """Heuristically detect columns likely containing dates."""
        candidates = []

        for col in df.columns:
            # Numeric columns whose names merely look date-ish (unix timestamps,
            # "day" counters) must never be reformatted — parsing them as
            # nanoseconds turns every value into 1970-01-01.
            convertible = (
                pd.api.types.is_object_dtype(df[col])
                or pd.api.types.is_string_dtype(df[col])
                or pd.api.types.is_datetime64_any_dtype(df[col])
            )
            if not convertible:
                continue

            col_lower = str(col).lower()
            # Name-based heuristic
            if any(pattern in col_lower for pattern in self.DATE_PATTERNS):
                candidates.append(col)
                continue

            # Content-based heuristic: try parsing sample
            if df[col].dtype == "object":
                sample = df[col].dropna().head(10)
                if len(sample) > 0:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        parsed = pd.to_datetime(sample, errors="coerce")
                    if parsed.notna().sum() > len(sample) * 0.5:
                        candidates.append(col)

        return candidates
