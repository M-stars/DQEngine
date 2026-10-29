"""Duplicate row detection and removal."""

from __future__ import annotations

import pandas as pd

from dqengine.models.schemas import RepairResult


class DuplicateCleaner:
    """Detect and remove duplicate rows.

    Usage:
        cleaner = DuplicateCleaner()
        df_clean, result = cleaner.clean(df)
    """

    def clean(
        self,
        df: pd.DataFrame,
        keep: str = "first",
        duplicate_mask: "pd.Series | None" = None,
    ) -> tuple[pd.DataFrame, RepairResult]:
        """Remove duplicate rows.

        Args:
            df: Input DataFrame.
            keep: Which duplicate to keep ('first', 'last', or False to drop all).
            duplicate_mask: 预计算的 df.duplicated(keep=keep) 掩码.
                全帧哈希约 0.5s/百万行, 调用方已算过时传入可避免重复计算.

        Returns:
            Tuple of (cleaned DataFrame, RepairResult).
        """
        rows_before = len(df)
        if duplicate_mask is None:
            duplicate_mask = df.duplicated(keep=keep)
        duplicate_count = int(duplicate_mask.sum())
        df_clean = df[~duplicate_mask].copy()

        result = RepairResult(
            operation="duplicate_removal",
            rows_before=rows_before,
            rows_after=len(df_clean),
            columns_affected=len(df.columns),
            changes_made=duplicate_count,
            details={
                "duplicates_removed": duplicate_count,
                "removal_rate": round(duplicate_count / max(rows_before, 1), 4),
            },
        )

        return df_clean, result
