"""Pydantic data models for DQEngine."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# 第一阶段模型 - 数据分析、质量评分、数据修复、规则验证
# ============================================================================


class ColumnProfile(BaseModel):
    """单个字段的统计画像."""

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
    """数据集完整画像结果."""

    file_path: str
    row_count: int
    column_count: int
    total_cells: int
    duplicate_row_count: int
    duplicate_row_rate: float
    memory_usage_mb: float
    columns: List[ColumnProfile]


class QualityDimension(BaseModel):
    """单一质量维度评分."""

    name: str
    score: float  # 0-100
    weight: float = 1.0
    description: str = ""


class QualityScore(BaseModel):
    """整体数据质量评分."""

    overall_score: float  # 0-100
    dimensions: List[QualityDimension]
    grade: str  # A, B, C, D, F


class RepairResult(BaseModel):
    """数据修复操作结果."""

    operation: str
    rows_before: int
    rows_after: int
    columns_affected: int
    changes_made: int
    details: Dict[str, Any] = Field(default_factory=dict)


class OutlierRecord(BaseModel):
    """异常值记录."""

    column: str
    row_index: int
    value: float
    lower_bound: float
    upper_bound: float
    severity: str  # mild, extreme


class ValidationRule(BaseModel):
    """YAML解析的验证规则."""

    column: str
    rule_type: str  # range, regex, not_null, allowed_values
    params: Dict[str, Any] = Field(default_factory=dict)


class RuleViolation(BaseModel):
    """单条规则违规记录."""

    column: str
    rule_type: str
    row_index: int
    value: Any
    message: str


class ValidationResult(BaseModel):
    """规则验证结果."""

    passed: bool
    total_rules: int
    passed_rules: int
    failed_rules: int
    total_violations: int
    violations: List[RuleViolation]


# ============================================================================
# 第二阶段新增模型 - 语义引擎、批处理、Pipeline、插件、配置、报告
# ============================================================================


# ---- 语义引擎模型 ----


class SemanticType(str, Enum):
    """统一语义类型枚举."""

    EMAIL = "email"
    PHONE_NUMBER = "phone_number"
    DATETIME = "datetime"
    CURRENCY = "currency"
    UUID = "uuid"
    IP_ADDRESS = "ip"
    URL = "url"
    ID = "id"
    COUNTRY = "country"
    CITY = "city"
    AGE = "age"
    GENDER = "gender"
    NAME = "name"
    UNKNOWN = "unknown"


class FieldSemantic(BaseModel):
    """单个字段的语义分析结果."""

    column_name: str
    detected_type: SemanticType = SemanticType.UNKNOWN
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0-1")
    matched_patterns: List[str] = Field(default_factory=list)
    sample_values: List[Any] = Field(default_factory=list)
    reasoning: str = ""


class SemanticResult(BaseModel):
    """完整语义分析结果."""

    file_path: str
    total_columns: int
    recognized_columns: int
    fields: List[FieldSemantic]
    analyzed_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class SemanticPattern(BaseModel):
    """语义识别模式定义."""

    name: str
    semantic_type: SemanticType
    column_patterns: List[str] = Field(default_factory=list, description="字段名匹配模式")
    value_regex: str = ""
    priority: int = Field(default=0, description="优先级,数值越大越高")
    description: str = ""


# ---- 批处理模型 ----


class BatchFileResult(BaseModel):
    """单个文件的批处理结果."""

    file_path: str
    success: bool
    error: Optional[str] = None
    rows_before: int = 0
    rows_after: int = 0
    score_before: float = 0.0
    score_after: float = 0.0
    repairs: List[RepairResult] = Field(default_factory=list)


class BatchSummary(BaseModel):
    """批处理汇总结果."""

    total_files: int
    succeeded: int
    failed: int
    total_rows_before: int
    total_rows_after: int
    average_score_before: float
    average_score_after: float
    files: List[BatchFileResult]
    executed_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ---- Pipeline 模型 ----


class PipelineStep(BaseModel):
    """Pipeline 中的一个治理步骤."""

    step_name: str
    module: str
    class_name: str
    method: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class PipelineConfig(BaseModel):
    """完整的 Pipeline 配置."""

    name: str
    version: str = "0.1.0"
    description: str = ""
    steps: List[PipelineStep]
    input_file: str = ""
    output_file: str = "cleaned_data.csv"
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ---- 插件模型 ----


class PluginType(str, Enum):
    """插件类型."""

    VALIDATOR = "validator"
    CLEANER = "cleaner"
    SCORER = "scorer"
    LOADER = "loader"
    REPORTER = "reporter"


class PluginInfo(BaseModel):
    """插件信息."""

    name: str
    plugin_type: PluginType
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    file_path: str = ""
    enabled: bool = True
    dependencies: List[str] = Field(default_factory=list)


# ---- 配置模型 ----


class MissingValueConfig(BaseModel):
    """缺失值治理配置."""

    strategy: str = "mean"  # mean, median, mode, drop, constant
    constant_value: Optional[str] = None
    enabled: bool = True


class DuplicateConfig(BaseModel):
    """重复值治理配置."""

    enabled: bool = True
    keep: str = "first"  # first, last, False


class OutlierConfig(BaseModel):
    """异常值治理配置."""

    enabled: bool = True
    method: str = "iqr"  # iqr, zscore
    threshold: float = 1.5
    action: str = "flag"  # flag, remove


class DateConfig(BaseModel):
    """日期标准化配置."""

    enabled: bool = True
    target_format: str = "%Y-%m-%d"


class CleaningConfig(BaseModel):
    """完整清洗配置."""

    missing: MissingValueConfig = Field(default_factory=MissingValueConfig)
    duplicate: DuplicateConfig = Field(default_factory=DuplicateConfig)
    outlier: OutlierConfig = Field(default_factory=OutlierConfig)
    date: DateConfig = Field(default_factory=DateConfig)


class ReportFormat(str, Enum):
    """报告格式枚举."""

    HTML = "html"
    JSON = "json"
    MARKDOWN = "markdown"


class ReportConfig(BaseModel):
    """报告配置."""

    formats: List[ReportFormat] = Field(default_factory=lambda: [ReportFormat.HTML])
    output_dir: str = "reports"
    include_charts: bool = True
    include_outliers: bool = True


class AppConfig(BaseModel):
    """DQEngine 完整应用配置."""

    cleaning: CleaningConfig = Field(default_factory=CleaningConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    semantic_enabled: bool = True
    plugins_dir: str = "plugins"
    log_level: str = "INFO"
    log_file: str = "logs/dqengine.log"


# ---- 环境诊断模型 ----


class DoctorResult(BaseModel):
    """环境诊断结果."""

    python_version: str
    dqengine_version: str
    dependencies: Dict[str, str] = Field(default_factory=dict)
    plugins_loaded: List[str] = Field(default_factory=list)
    config_found: bool = False
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
