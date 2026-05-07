"""AI 规则生成器 - 基于统计数据推断数据质量规则."""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from dqengine.models.schemas import AIRule, AIRuleSet, AIProviderType


class RuleGeneratorBase(ABC):
    """AI 规则生成器基类 — 可扩展 Provider 架构."""

    provider_type: AIProviderType

    @abstractmethod
    def generate(self, df: pd.DataFrame, columns: Optional[List[str]] = None) -> AIRuleSet:
        """从 DataFrame 推断数据质量规则."""
        ...


class HeuristicRuleGenerator(RuleGeneratorBase):
    """基于统计推断和启发式规则的生成器.

    自动推断:
    - 类型规则 (dtype)
    - 范围规则 (min/max)
    - 正则规则 (email, phone, url 等)
    - 唯一性规则 (unique rate)
    - 空值规则 (null rate)
    """

    provider_type = AIProviderType.HEURISTIC

    # 常用正则模式
    PATTERNS: Dict[str, Dict[str, Any]] = {
        "email": {
            "regex": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
            "sample_match": r".*@.*\..*",
            "name": "电子邮件",
        },
        "phone_cn": {
            "regex": r"^1[3-9]\d{9}$",
            "sample_match": r"^1[3-9]\d{9}$",
            "name": "中国手机号",
        },
        "url": {
            "regex": r"^https?://[^\s/$.?#].[^\s]*$",
            "sample_match": r"^https?://",
            "name": "URL",
        },
        "ip": {
            "regex": r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$",
            "sample_match": r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$",
            "name": "IP地址",
        },
        "uuid": {
            "regex": r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            "sample_match": r"^[0-9a-f]{8}-",
            "name": "UUID",
        },
    }

    def __init__(self, sample_size: int = 100) -> None:
        self.sample_size = sample_size
        self._warnings: List[str] = []

    def generate(self, df: pd.DataFrame, columns: Optional[List[str]] = None) -> AIRuleSet:
        """从 DataFrame 推断数据质量规则."""
        start_time = time.time()
        self._warnings = []

        target_columns = columns or list(df.columns)
        rules: Dict[str, List[AIRule]] = {}

        for col in target_columns:
            if col not in df.columns:
                self._warnings.append(f"列 '{col}' 不存在于数据中")
                continue

            series = df[col]
            col_rules: List[AIRule] = []

            # 1. 类型规则
            type_rule = self._infer_type_rule(col, series)
            if type_rule:
                col_rules.append(type_rule)

            # 2. 空值规则
            null_rule = self._infer_null_rule(col, series)
            if null_rule:
                col_rules.append(null_rule)

            # 3. 唯一性规则
            unique_rule = self._infer_unique_rule(col, series)
            if unique_rule:
                col_rules.append(unique_rule)

            # 4. 数值列: 范围规则
            if pd.api.types.is_numeric_dtype(series):
                range_rule = self._infer_range_rule(col, series)
                if range_rule:
                    col_rules.append(range_rule)

            # 5. 字符串列: 正则规则
            if pd.api.types.is_string_dtype(series) or series.dtype == object:
                regex_rules = self._infer_regex_rules(col, series)
                col_rules.extend(regex_rules)

            # 6. 分类列: 允许值规则
            if not pd.api.types.is_numeric_dtype(series):
                allowed_rule = self._infer_allowed_values_rule(col, series)
                if allowed_rule:
                    col_rules.append(allowed_rule)

            rules[col] = col_rules

        elapsed = (time.time() - start_time) * 1000
        return AIRuleSet(
            columns=rules,
            generated_by=self.provider_type.value,
            generation_time_ms=round(elapsed, 2),
            warnings=self._warnings,
        )

    def _infer_type_rule(self, col: str, series: pd.Series) -> Optional[AIRule]:
        """推断数据类型的预期类型."""
        dtype_str = str(series.dtype)
        type_map = {
            "int64": "int",
            "int32": "int",
            "float64": "float",
            "float32": "float",
            "object": "str",
            "bool": "bool",
            "datetime64[ns]": "datetime",
        }

        expected_type = type_map.get(dtype_str, "str")
        # 整数型但存为 float 的特殊处理
        if expected_type == "float":
            sample = series.dropna().head(self.sample_size)
            if len(sample) > 0 and (sample == sample.astype(int)).all():
                expected_type = "int"

        return AIRule(
            column=col,
            rule_type="type",
            params={"expected_type": expected_type},
            confidence=0.95,
            reasoning=f"根据列数据类型 ({dtype_str}) 推断为 {expected_type}",
        )

    def _infer_null_rule(self, col: str, series: pd.Series) -> Optional[AIRule]:
        """推断空值约束规则."""
        null_rate = series.isna().mean()

        if null_rate == 0:
            return AIRule(
                column=col,
                rule_type="nullable",
                params={"nullable": False, "max_null_rate": 0.0},
                confidence=0.9,
                reasoning=f"字段无空值，建议设为必填",
            )
        elif null_rate < 0.1:
            return AIRule(
                column=col,
                rule_type="nullable",
                params={"nullable": True, "max_null_rate": 0.1},
                confidence=0.7,
                reasoning=f"空值率 {null_rate:.1%} < 10%，建议允许空值但设上限",
            )
        elif null_rate > 0.5:
            self._warnings.append(f"字段 '{col}' 空值率高达 {null_rate:.1%}")
            return AIRule(
                column=col,
                rule_type="nullable",
                params={"nullable": True, "max_null_rate": 1.0},
                confidence=0.5,
                reasoning=f"空值率较高 ({null_rate:.1%})，无法强制非空",
            )
        return None

    def _infer_unique_rule(self, col: str, series: pd.Series) -> Optional[AIRule]:
        """推断唯一性规则."""
        unique_rate = series.nunique() / max(len(series.dropna()), 1)

        if unique_rate > 0.95:
            return AIRule(
                column=col,
                rule_type="unique",
                params={"should_be_unique": True, "min_unique_rate": 0.95},
                confidence=0.85,
                reasoning=f"唯一值率 {unique_rate:.1%}，适合作为唯一标识",
            )
        elif unique_rate < 0.01 and len(series) > 100:
            return AIRule(
                column=col,
                rule_type="unique",
                params={"should_be_unique": False, "max_unique_values": 50},
                confidence=0.6,
                reasoning=f"唯一值率极低 ({unique_rate:.1%})，疑似分类字段",
            )
        return None

    def _infer_range_rule(self, col: str, series: pd.Series) -> Optional[AIRule]:
        """推断数值范围规则."""
        clean = series.dropna()
        if len(clean) == 0:
            return None

        q1 = float(clean.quantile(0.01))
        q99 = float(clean.quantile(0.99))
        iqr = q99 - q1

        # 使用 IQR 扩展边界
        lower = max(q1 - 1.5 * iqr, float(clean.min()) * 0.5 if clean.min() > 0 else float(clean.min()) * 2)
        upper = q99 + 1.5 * iqr

        dtype_str = str(series.dtype)
        if "int" in dtype_str:
            lower, upper = int(lower), int(upper)

        return AIRule(
            column=col,
            rule_type="range",
            params={"min": lower, "max": upper, "allow_outliers": True},
            confidence=0.8,
            reasoning=f"基于 IQR 方法推断范围: [{lower}, {upper}]",
        )

    def _infer_regex_rules(self, col: str, series: pd.Series) -> List[AIRule]:
        """推断正则匹配规则."""
        sample = series.dropna().head(min(self.sample_size, len(series))).astype(str)
        if len(sample) == 0:
            return []

        rules: List[AIRule] = []
        for pattern_name, pattern_def in self.PATTERNS.items():
            match_count = sample.str.match(pattern_def["sample_match"]).sum()
            match_rate = match_count / len(sample)

            if match_rate > 0.8:
                rules.append(
                    AIRule(
                        column=col,
                        rule_type="regex",
                        params={"pattern": pattern_def["regex"], "pattern_name": pattern_name},
                        confidence=round(match_rate, 2),
                        reasoning=f"{match_rate:.0%} 的样本匹配 {pattern_def['name']} 模式",
                    )
                )

        return rules

    def _infer_allowed_values_rule(self, col: str, series: pd.Series) -> Optional[AIRule]:
        """推断分类字段的允许值范围."""
        unique_vals = series.dropna().unique()
        if len(unique_vals) <= 20 and len(unique_vals) > 0:
            return AIRule(
                column=col,
                rule_type="allowed_values",
                params={"values": sorted([str(v) for v in unique_vals])},
                confidence=0.7 if len(unique_vals) <= 10 else 0.5,
                reasoning=f"仅包含 {len(unique_vals)} 个不同值，疑似分类字段",
            )
        return None


class LLMRuleGenerator(RuleGeneratorBase):
    """LLM 规则生成器 (Stub) — 为未来 LLM 集成预留接口.

    计划支持的 Provider:
    - OpenAI (GPT-4, GPT-4o)
    - Ollama (本地模型)
    - 自定义本地模型
    """

    provider_type = AIProviderType.OPENAI

    def __init__(self, model_name: str = "gpt-4o", api_key: Optional[str] = None) -> None:
        self.model_name = model_name
        self.api_key = api_key

    def generate(self, df: pd.DataFrame, columns: Optional[List[str]] = None) -> AIRuleSet:
        """LLM 规则生成 (未实现)."""
        return AIRuleSet(
            columns={},
            generated_by=f"llm:{self.model_name}",
            generation_time_ms=0,
            warnings=["LLM 规则生成器尚未实现，请使用 HeuristicRuleGenerator"],
        )
