"""语义检测器 - 基于正则 + 模式匹配自动识别字段语义."""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd

from dqengine.models.schemas import FieldSemantic, SemanticPattern, SemanticResult, SemanticType
from dqengine.registry.pattern_registry import get_pattern_registry
from dqengine.utils.logger import get_logger

logger = get_logger(__name__)


class SemanticDetector:
    """字段语义自动检测器.

    结合字段名匹配和值内容抽样进行语义识别.

    使用方式:
        detector = SemanticDetector()
        result = detector.detect(df, file_path="data.csv")
    """

    # 每列抽样行数
    SAMPLE_SIZE: int = 20

    def __init__(self) -> None:
        self._registry = get_pattern_registry()

    def detect(
        self,
        df: pd.DataFrame,
        file_path: str = "",
        additional_patterns: Optional[List[SemanticPattern]] = None,
    ) -> SemanticResult:
        """对 DataFrame 所有字段进行语义识别.

        Args:
            df: 输入 DataFrame.
            file_path: 文件路径 (用于结果记录).
            additional_patterns: 额外的自定义语义模式.

        Returns:
            SemanticResult 包含所有字段的语义分析结果.
        """
        # 注册额外模式
        if additional_patterns:
            for pat in additional_patterns:
                self._registry.register(pat)

        fields: List[FieldSemantic] = []

        for col in df.columns:
            field = self._detect_column(df, col)
            fields.append(field)

        recognized = sum(1 for f in fields if f.detected_type != SemanticType.UNKNOWN)

        return SemanticResult(
            file_path=file_path,
            total_columns=len(df.columns),
            recognized_columns=recognized,
            fields=fields,
            analyzed_at=datetime.now().isoformat(),
        )

    def _detect_column(self, df: pd.DataFrame, column: str) -> FieldSemantic:
        """对单个字段进行语义检测.

        Args:
            df: 输入 DataFrame.
            column: 字段名.

        Returns:
            FieldSemantic 包含检测结果.
        """
        # 第一步: 字段名模式匹配
        name_matches = self._registry.match_column(column)

        # 第二步: 值内容抽样
        sample_values = self._sample_values(df[column])

        # 第三步: 对每个匹配的模式进行值验证
        best_match: Optional[Tuple[SemanticPattern, float]] = None

        for pattern in name_matches:
            confidence = self._calculate_confidence(pattern, column, df[column], sample_values)
            if best_match is None or confidence > best_match[1]:
                best_match = (pattern, confidence)

        # 如果没有字段名匹配, 尝试纯值检测
        if best_match is None:
            best_match = self._detect_by_value(column, df[column], sample_values)

        if best_match:
            pattern, confidence = best_match
            return FieldSemantic(
                column_name=column,
                detected_type=pattern.semantic_type,
                confidence=confidence,
                matched_patterns=[pattern.name],
                sample_values=sample_values[:5],
                reasoning=f"字段名匹配模式: {pattern.name} (优先级: {pattern.priority})",
            )

        return FieldSemantic(
            column_name=column,
            detected_type=SemanticType.UNKNOWN,
            confidence=0.0,
            matched_patterns=[],
            sample_values=sample_values[:5],
            reasoning="未匹配到已知语义模式",
        )

    def _calculate_confidence(
        self,
        pattern: SemanticPattern,
        column_name: str,
        series: pd.Series,
        sample_values: List[str],
    ) -> float:
        """计算语义匹配的置信度.

        Args:
            pattern: 语义模式.
            column_name: 字段名.
            series: 数据列.
            sample_values: 抽样值.

        Returns:
            置信度 0.0 ~ 1.0.
        """
        confidence = 0.0

        # 字段名匹配得分 (0.6 权重)
        name_lower = column_name.lower()
        for col_pat in pattern.column_patterns:
            if col_pat.lower() == name_lower:
                confidence += 0.6
                break
            elif col_pat.lower() in name_lower:
                confidence += 0.45
                break
        else:
            confidence += 0.2  # 没有直接匹配

        # 值正则验证得分 (0.4 权重)
        if pattern.value_regex and sample_values:
            try:
                compiled = re.compile(pattern.value_regex)
                matches = 0
                for val in sample_values:
                    if val and compiled.search(str(val)):
                        matches += 1
                value_ratio = matches / len(sample_values) if sample_values else 0
                confidence += 0.4 * value_ratio
            except re.error:
                pass

        # 优先级加成
        confidence *= min(1.0, 0.8 + pattern.priority / 50)

        return round(min(confidence, 1.0), 4)

    def _detect_by_value(
        self,
        column: str,
        series: pd.Series,
        sample_values: List[str],
    ) -> Optional[Tuple[SemanticPattern, float]]:
        """纯值内容检测 (字段名未匹配时使用).

        Args:
            column: 字段名.
            series: 数据列.
            sample_values: 抽样值.

        Returns:
            (SemanticPattern, confidence) 或 None.
        """
        # 获取所有有正则的模式
        all_patterns = self._registry.get_all()
        regex_patterns = [p for p in all_patterns if p.value_regex]

        for pattern in regex_patterns:
            try:
                compiled = re.compile(pattern.value_regex)
                matches = 0
                for val in sample_values:
                    if val and compiled.search(str(val)):
                        matches += 1
                ratio = matches / len(sample_values) if sample_values else 0
                if ratio >= 0.8:
                    return (pattern, round(ratio, 4))
            except re.error:
                continue

        return None

    @staticmethod
    def _sample_values(series: pd.Series) -> List[str]:
        """从列中抽样非空值.

        Args:
            series: 数据列.

        Returns:
            字符串样例列表.
        """
        non_null = series.dropna().head(SemanticDetector.SAMPLE_SIZE)
        return [str(v) for v in non_null.tolist()]

    def add_pattern(self, pattern: SemanticPattern) -> None:
        """添加自定义语义模式.

        Args:
            pattern: SemanticPattern 实例.
        """
        self._registry.register(pattern)

    def remove_pattern(self, name: str) -> bool:
        """移除语义模式.

        Args:
            name: 模式名称.

        Returns:
            是否成功移除.
        """
        return self._registry.unregister(name)

    def list_patterns(self) -> List[SemanticPattern]:
        """列出所有已注册的语义模式."""
        return self._registry.get_all()
