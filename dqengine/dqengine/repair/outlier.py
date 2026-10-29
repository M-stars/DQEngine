"""Outlier detection using the IQR / z-score methods."""

from __future__ import annotations

import pandas as pd

from dqengine.models.schemas import OutlierRecord


class OutlierDetector:
    """Detect outliers in numeric columns using the IQR or z-score method.

    Outlier row positions are recorded positionally (row_index = position in
    the DataFrame), so detection and removal are correct even when the index
    has duplicate or non-integer labels.

    Usage:
        detector = OutlierDetector()
        outliers = detector.detect(df)
        df_clean = detector.remove_outliers(df, outliers)
    """

    def detect(
        self,
        df: pd.DataFrame,
        method: str = "iqr",
        threshold: float = 1.5,
    ) -> list[OutlierRecord]:
        """Detect outliers in all numeric columns.

        Args:
            df: Input DataFrame.
            method: Detection method, "iqr" or "zscore".
            threshold: IQR multiplier for the "iqr" method, z-score cutoff
                for the "zscore" method. Extreme outliers sit at twice the
                threshold. Must be > 0.

        Returns:
            List of OutlierRecord for each detected outlier.
        """
        if method not in ("iqr", "zscore"):
            raise ValueError(f"未知的异常值检测方法: {method!r} (可选: iqr, zscore)")
        if threshold <= 0:
            raise ValueError(
                f"threshold 必须为正数, 收到 {threshold!r} "
                f"(非正阈值会使检测界反转, 可能清空整个数据集)"
            )

        outliers: list[OutlierRecord] = []
        numeric_cols = df.select_dtypes(include=["number"]).columns

        for col in numeric_cols:
            values = df[col]
            non_null = values.dropna()
            if len(non_null) < 4:
                continue

            if method == "iqr":
                q1 = non_null.quantile(0.25)
                q3 = non_null.quantile(0.75)
                iqr = q3 - q1

                if iqr == 0:
                    continue

                lower = q1 - threshold * iqr
                upper = q3 + threshold * iqr
                extreme_lower = q1 - 2 * threshold * iqr
                extreme_upper = q3 + 2 * threshold * iqr
            else:  # zscore
                mean = non_null.mean()
                std = non_null.std()
                if pd.isna(std) or std == 0:
                    continue

                lower = mean - threshold * std
                upper = mean + threshold * std

            # 按位置遍历而非按标签索引: 重复/非整数索引标签下
            # series[label] 会返回多值 Series 或截断, 导致崩溃或误判
            for pos, val in enumerate(values):
                if pd.isna(val):
                    continue

                if method == "iqr":
                    if val < extreme_lower or val > extreme_upper:
                        severity = "extreme"
                    elif val < lower or val > upper:
                        severity = "mild"
                    else:
                        continue
                else:  # zscore
                    z = abs((val - mean) / std)
                    if z > 2 * threshold:
                        severity = "extreme"
                    elif z > threshold:
                        severity = "mild"
                    else:
                        continue

                outliers.append(
                    OutlierRecord(
                        column=str(col),
                        row_index=pos,
                        value=float(val),
                        lower_bound=round(float(lower), 4),
                        upper_bound=round(float(upper), 4),
                        severity=severity,
                    )
                )

        return outliers

    def remove_outliers(
        self, df: pd.DataFrame, outliers: list[OutlierRecord]
    ) -> pd.DataFrame:
        """Remove rows containing outliers.

        Args:
            df: Input DataFrame.
            outliers: List of detected outliers (row_index 为 df 中的行位置).

        Returns:
            DataFrame with outlier rows removed.
        """
        positions = sorted({o.row_index for o in outliers})
        if not positions or not len(df):
            return df.copy()

        n = len(df)
        keep_mask = [True] * n
        for pos in positions:
            if 0 <= pos < n:
                keep_mask[pos] = False
        return df[pd.Series(keep_mask, index=df.index)].copy()

    def summary(self, outliers: list[OutlierRecord]) -> dict:
        """Summarize detected outliers by column."""
        summary: dict[str, dict[str, int]] = {}
        for o in outliers:
            if o.column not in summary:
                summary[o.column] = {"mild": 0, "extreme": 0}
            summary[o.column][o.severity] += 1
        return summary
