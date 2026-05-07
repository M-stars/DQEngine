"""Domain 实体定义 - 核心业务对象."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Dataset:
    """数据集实体."""

    id: str
    name: str
    file_path: str
    row_count: int = 0
    column_count: int = 0
    schema: Dict[str, str] = field(default_factory=dict)
    quality_score: float = 0.0
    last_profiled: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def size_category(self) -> str:
        if self.row_count < 1000:
            return "small"
        elif self.row_count < 100000:
            return "medium"
        return "large"


@dataclass
class QualityRule:
    """数据质量规则实体."""

    id: str
    name: str
    column: str
    rule_type: str  # type, range, regex, unique, nullable, allowed_values
    params: Dict[str, Any] = field(default_factory=dict)
    severity: RiskLevel = RiskLevel.MEDIUM
    enabled: bool = True
    created_by: str = "manual"  # manual, heuristic, llm
    description: str = ""


@dataclass
class GovernanceJob:
    """治理任务实体."""

    id: str
    name: str
    steps: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        self.status = "running"
        self.started_at = datetime.now().isoformat()

    def complete(self, success: bool = True) -> None:
        self.status = "completed" if success else "failed"
        self.completed_at = datetime.now().isoformat()


@dataclass
class RiskAssessment:
    """数据质量风险评估."""

    dataset_id: str
    overall_risk: RiskLevel = RiskLevel.LOW
    factors: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    assessed_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_factor(self, name: str, severity: RiskLevel, detail: str) -> None:
        self.factors.append({"name": name, "severity": severity.value, "detail": detail})
        self._recalculate()

    def _recalculate(self) -> None:
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        max_sev = max(
            (severity_order.get(f["severity"], 0) for f in self.factors),
            default=0,
        )
        for level, idx in severity_order.items():
            if idx == max_sev:
                self.overall_risk = RiskLevel(level)
                break


@dataclass
class AnomalyReport:
    """数据异常报告实体."""

    id: str
    dataset_id: str
    patterns: List[Dict[str, Any]] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    suggestions: List[str] = field(default_factory=list)
    detected_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_pattern(
        self,
        pattern_type: str,
        column: str,
        description: str,
        suggestion: str = "",
    ) -> None:
        self.patterns.append({
            "pattern_type": pattern_type,
            "column": column,
            "description": description,
            "suggestion": suggestion,
        })
