"""Pydantic data models for DQEngine."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    """Statistical profile of a single column."""

    column_name: str
    dtype: str
    total_count: int
    non_null_count: int
    null_count: int
    null_rate: float
    unique_count: int
    unique_rate: float
    duplicate_count: int = 0
    mean: Optional[float] = None
    std: Optional[float] = None
    min_val: Optional[float] = None
    q25: Optional[float] = None
    q50: Optional[float] = None
    q75: Optional[float] = None
    max_val: Optional[float] = None


class ProfileResult(BaseModel):
    """Complete profiling result for a dataset."""

    file_path: str
    row_count: int
    column_count: int
    total_cells: int
    duplicate_row_count: int
    duplicate_row_rate: float
    memory_usage_mb: float
    columns: List[ColumnProfile]


class QualityDimension(BaseModel):
    """A single quality dimension score."""

    name: str
    score: float  # 0-100
    weight: float = 1.0
    description: str = ""


class QualityScore(BaseModel):
    """Overall data quality score."""

    overall_score: float  # 0-100
    dimensions: List[QualityDimension]
    grade: str  # A, B, C, D, F


class RepairResult(BaseModel):
    """Result of a data repair operation."""

    operation: str
    rows_before: int
    rows_after: int
    columns_affected: int
    changes_made: int
    details: Dict[str, Any] = Field(default_factory=dict)


class OutlierRecord(BaseModel):
    """Record of a detected outlier."""

    column: str
    row_index: int
    value: float
    lower_bound: float
    upper_bound: float
    severity: str  # mild, extreme


class ValidationRule(BaseModel):
    """A single validation rule parsed from YAML."""

    column: str
    rule_type: str  # range, regex, not_null, allowed_values
    params: Dict[str, Any] = Field(default_factory=dict)


class RuleViolation(BaseModel):
    """A single rule violation."""

    column: str
    rule_type: str
    row_index: int
    value: Any
    message: str


class ValidationResult(BaseModel):
    """Result of rule-based validation."""

    passed: bool
    total_rules: int
    passed_rules: int
    failed_rules: int
    total_violations: int
    violations: List[RuleViolation]
