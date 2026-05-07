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


# ============================================================================
# 第三阶段新增模型 - AI规则生成、漂移检测、监控、API、编排、实时、元数据、调度、可观测性
# ============================================================================


# ---- AI 规则生成模型 ----


class AIRule(BaseModel):
    """AI 生成的单条数据质量规则."""

    column: str
    rule_type: str  # type, range, regex, unique, nullable, allowed_values
    params: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, description="生成置信度")
    reasoning: str = ""


class AIRuleSet(BaseModel):
    """AI 生成的完整规则集."""

    columns: Dict[str, List[AIRule]] = Field(default_factory=dict)
    generated_by: str = "heuristic"
    generation_time_ms: float = 0.0
    warnings: List[str] = Field(default_factory=list)


class AIProviderType(str, Enum):
    """AI Provider 类型."""

    HEURISTIC = "heuristic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    LOCAL = "local"


# ---- 数据漂移检测模型 ----


class DriftType(str, Enum):
    """漂移类型."""

    SCHEMA = "schema"
    DISTRIBUTION = "distribution"
    NULL = "null"
    CATEGORY = "category"


class DriftSeverity(str, Enum):
    """漂移严重程度."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ColumnDriftResult(BaseModel):
    """单列漂移检测结果."""

    column_name: str
    drift_type: DriftType
    severity: DriftSeverity = DriftSeverity.NONE
    statistic_name: str = ""  # KS statistic, PSI value, etc.
    statistic_value: float = 0.0
    threshold: float = 0.0
    baseline_value: Any = None
    current_value: Any = None
    description: str = ""


class DriftReport(BaseModel):
    """完整漂移检测报告."""

    baseline_file: str
    current_file: str
    total_columns: int
    drifted_columns: int
    overall_severity: DriftSeverity = DriftSeverity.NONE
    schema_drift: List[ColumnDriftResult] = Field(default_factory=list)
    distribution_drift: List[ColumnDriftResult] = Field(default_factory=list)
    null_drift: List[ColumnDriftResult] = Field(default_factory=list)
    category_drift: List[ColumnDriftResult] = Field(default_factory=list)
    detected_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ---- 监控模型 ----


class MonitorEvent(BaseModel):
    """单次监控事件."""

    timestamp: str
    file_path: str
    event_type: str  # created, modified, deleted
    profile: Optional[ProfileResult] = None
    score: Optional[QualityScore] = None
    drift_detected: bool = False


class QualityTrend(BaseModel):
    """质量趋势数据点."""

    timestamp: str
    file_name: str
    overall_score: float
    row_count: int
    null_rate: float
    duplicate_rate: float


class MonitorSession(BaseModel):
    """监控会话."""

    session_id: str
    watch_directory: str
    started_at: str
    events: List[MonitorEvent] = Field(default_factory=list)
    trends: List[QualityTrend] = Field(default_factory=list)
    total_files_processed: int = 0
    alerts: List[str] = Field(default_factory=list)


# ---- API 模型 ----


class APIResponse(BaseModel):
    """通用 API 响应."""

    success: bool
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    errors: List[str] = Field(default_factory=list)


class ProfileRequest(BaseModel):
    """画像请求."""

    file_path: str
    output_format: str = "json"


class ValidateRequest(BaseModel):
    """验证请求."""

    file_path: str
    rules_path: str


class CleanRequest(BaseModel):
    """清洗请求."""

    file_path: str
    config_path: Optional[str] = None
    output_path: str = "cleaned_data.csv"


class DriftRequest(BaseModel):
    """漂移检测请求."""

    baseline_path: str
    current_path: str


# ---- DAG 编排模型 ----


class DAGNodeType(str, Enum):
    """DAG 节点类型."""

    LOAD = "load"
    PROFILE = "profile"
    VALIDATE = "validate"
    CLEAN = "clean"
    SCORE = "score"
    REPORT = "report"
    SEMANTIC = "semantic"
    DRIFT = "drift"
    EXPORT = "export"


class DAGNodeStatus(str, Enum):
    """DAG 节点执行状态."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class DAGNode(BaseModel):
    """DAG 节点定义."""

    node_id: str
    node_type: DAGNodeType
    depends_on: List[str] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)
    status: DAGNodeStatus = DAGNodeStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class DAGPipeline(BaseModel):
    """DAG Pipeline 定义."""

    name: str
    version: str = "1.0.0"
    description: str = ""
    nodes: List[DAGNode]
    edges: List[tuple] = Field(default_factory=list)  # (from_node, to_node)


class DAGExecutionResult(BaseModel):
    """DAG 执行结果."""

    pipeline_name: str
    success: bool
    nodes_executed: int
    nodes_failed: int
    total_duration_ms: float
    node_results: Dict[str, DAGNode] = Field(default_factory=dict)


# ---- 实时验证模型 ----


class StreamEvent(BaseModel):
    """流式数据事件."""

    event_id: str
    timestamp: str
    data: Dict[str, Any]
    source: str = "simulator"


class StreamValidationResult(BaseModel):
    """流式验证结果."""

    event_id: str
    passed: bool
    violations: List[RuleViolation] = Field(default_factory=list)
    processing_time_ms: float = 0.0
    score: Optional[float] = None


# ---- 元数据与血缘模型 ----


class LineageStep(BaseModel):
    """血缘追踪中的一个处理步骤."""

    step_id: str
    step_name: str
    input_data: str
    output_data: str
    operation: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: float = 0.0


class DataLineage(BaseModel):
    """完整数据血缘."""

    dataset_id: str
    source_path: str
    created_at: str
    steps: List[LineageStep] = Field(default_factory=list)
    current_schema: Optional[Dict[str, str]] = None


class ExecutionRecord(BaseModel):
    """规则执行历史记录."""

    execution_id: str
    rule_name: str
    file_path: str
    passed: bool
    violations_count: int
    execution_time_ms: float
    executed_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ---- 调度模型 ----


class ScheduleType(str, Enum):
    """调度类型."""

    CRON = "cron"
    INTERVAL = "interval"
    WATCH = "watch"


class ScheduledTask(BaseModel):
    """调度任务定义."""

    task_id: str
    name: str
    schedule_type: ScheduleType
    schedule_value: str  # cron表达式 或 间隔秒数
    action: str  # profile, validate, clean, report
    target_path: str
    config_path: Optional[str] = None
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None


class ScheduleConfig(BaseModel):
    """调度配置."""

    tasks: List[ScheduledTask] = Field(default_factory=list)
    max_concurrent: int = 3
    log_dir: str = "logs"


# ---- 可观测性模型 ----


class MetricType(str, Enum):
    """指标类型."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class Metric(BaseModel):
    """单个指标."""

    name: str
    metric_type: MetricType
    value: float
    labels: Dict[str, str] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ExecutionTrace(BaseModel):
    """执行追踪记录."""

    trace_id: str
    operation: str
    start_time: str
    end_time: Optional[str] = None
    duration_ms: float = 0.0
    success: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
    spans: List["ExecutionTrace"] = Field(default_factory=list)


class RuleExecutionStats(BaseModel):
    """规则执行统计."""

    rule_name: str
    total_executions: int = 0
    passed: int = 0
    failed: int = 0
    avg_execution_time_ms: float = 0.0
    last_executed: Optional[str] = None
    pass_rate: float = 0.0


class ObservabilityReport(BaseModel):
    """可观测性报告."""

    metrics: List[Metric] = Field(default_factory=list)
    traces: List[ExecutionTrace] = Field(default_factory=list)
    rule_stats: List[RuleExecutionStats] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ---- 企业架构模型 ----


class StorageType(str, Enum):
    """存储类型."""

    SQLITE = "sqlite"
    DUCKDB = "duckdb"
    POSTGRESQL = "postgresql"


class CacheProvider(str, Enum):
    """缓存提供者."""

    MEMORY = "memory"
    REDIS = "redis"


class Environment(str, Enum):
    """运行环境."""

    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class RiskLevel(str, Enum):
    """数据质量风险等级."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyPattern(BaseModel):
    """数据异常模式."""

    pattern_type: str  # field_conflict, type_drift, high_null, anomaly
    column: str
    description: str
    risk_level: RiskLevel = RiskLevel.MEDIUM
    suggestion: str = ""
    detected_at: str = Field(default_factory=lambda: datetime.now().isoformat())
