"""Outlier detection using the IQR method."""

from __future__ import annotations

import pandas as pd

from dqengine.models.schemas import OutlierRecord


class OutlierDetector:
    """Detect outliers in numeric columns using the IQR method.

    Outliers are values outside [Q1 - 1.5*IQR, Q3 + 1.5*IQR].
    Extreme outliers are outside [Q1 - 3*IQR, Q3 + 3*IQR].

    Usage:
        detector = OutlierDetector()
        outliers = detector.detect(df)
        df_clean = detector.remove_outliers(df, outliers)
    """

    def detect(self, df: pd.DataFrame) -> list[OutlierRecord]:
        """Detect outliers in all numeric columns.

        Args:
            df: Input DataFrame.

        Returns:
            List of OutlierRecord for each detected outlier.
        """
        outliers: list[OutlierRecord] = []
        numeric_cols = df.select_dtypes(include=["number"]).columns

        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 4:
                continue

            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1

            if iqr == 0:
                continue

            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            extreme_lower = q1 - 3 * iqr
            extreme_upper = q3 + 3 * iqr

            for idx in series.index:
                val = series[idx]
                if val < extreme_lower or val > extreme_upper:
                    severity = "extreme"
                elif val < lower or val > upper:
                    severity = "mild"
                else:
                    continue

                outliers.append(
                    OutlierRecord(
                        column=str(col),
                        row_index=int(idx),
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
            outliers: List of detected outliers.

        Returns:
            DataFrame with outlier rows removed.
        """
        indices_to_drop = {o.row_index for o in outliers}
        return df.drop(index=indices_to_drop).copy()

    def summary(self, outliers: list[OutlierRecord]) -> dict:
        """Summarize detected outliers by column."""
        summary: dict[str, dict[str, int]] = {}
        for o in outliers:
            if o.column not in summary:
                summary[o.column] = {"mild": 0, "extreme": 0}
            summary[o.column][o.severity] += 1
        return summary
