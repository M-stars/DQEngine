"""Data quality scoring engine."""

from __future__ import annotations

import pandas as pd

from dqengine.models.schemas import ProfileResult, QualityScore, QualityDimension


class QualityScorer:
    """Score data quality across multiple dimensions: completeness, uniqueness, validity.

    Usage:
        scorer = QualityScorer()
        score = scorer.score(df, profile_result)
    """

    def score(self, df: pd.DataFrame, profile: ProfileResult) -> QualityScore:
        """Compute overall quality score.

        Args:
            df: Input DataFrame.
            profile: Pre-computed ProfileResult.

        Returns:
            QualityScore with overall score, dimension breakdown, and grade.
        """
        completeness = self._score_completeness(profile)
        uniqueness = self._score_uniqueness(profile)
        validity = self._score_validity(df, profile)

        dimensions = [
            QualityDimension(
                name="completeness",
                score=round(completeness, 1),
                weight=0.4,
                description="Measures the proportion of non-null values across all columns.",
            ),
            QualityDimension(
                name="uniqueness",
                score=round(uniqueness, 1),
                weight=0.3,
                description="Measures the proportion of unique rows and unique values per column.",
            ),
            QualityDimension(
                name="validity",
                score=round(validity, 1),
                weight=0.3,
                description="Measures data type consistency and value plausibility.",
            ),
        ]

        overall = sum(d.score * d.weight for d in dimensions)

        return QualityScore(
            overall_score=round(overall, 1),
            dimensions=dimensions,
            grade=self._grade(overall),
        )

    def _score_completeness(self, profile: ProfileResult) -> float:
        """Score completeness: average non-null rate across columns."""
        if not profile.columns:
            return 0.0
        avg_completeness = sum(
            (1.0 - c.null_rate) for c in profile.columns
        ) / len(profile.columns)
        return avg_completeness * 100

    def _score_uniqueness(self, profile: ProfileResult) -> float:
        """Score uniqueness: combines row uniqueness and column value uniqueness."""
        row_uniqueness = 1.0 - profile.duplicate_row_rate
        if not profile.columns:
            col_uniqueness = 0.0
        else:
            col_uniqueness = sum(c.unique_rate for c in profile.columns) / len(
                profile.columns
            )
        combined = row_uniqueness * 0.5 + col_uniqueness * 0.5
        return combined * 100

    def _score_validity(self, df: pd.DataFrame, profile: ProfileResult) -> float:
        """Score validity: check for type consistency and reasonable value ranges."""
        if len(df) == 0 or not profile.columns:
            return 100.0

        scores = []
        for col in profile.columns:
            col_score = 100.0
            series = df[col.column_name]

            # Penalize mixed types
            if series.dtype == "object":
                non_null = series.dropna()
                if len(non_null) > 0:
                    type_counts = non_null.map(type).value_counts()
                    dominant_ratio = type_counts.iloc[0] / len(non_null)
                    col_score *= 0.7 + 0.3 * dominant_ratio

            # Penalize extreme null rates
            if col.null_rate > 0.5:
                col_score -= (col.null_rate - 0.5) * 100

            scores.append(max(col_score, 0))

        return sum(scores) / len(scores)

    @staticmethod
    def _grade(score: float) -> str:
        """Convert numeric score to letter grade."""
        if score >= 90:
            return "A"
        elif score >= 75:
            return "B"
        elif score >= 60:
            return "C"
        elif score >= 40:
            return "D"
        else:
            return "F"
