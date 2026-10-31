"""智能修复建议 — 基于画像统计让 LLM 识别数据问题并给出可执行的清洗配置.

流程: Profiler 统计摘要 (确定性输入) -> LLM 识别问题并从白名单中选动作 ->
本地把动作映射为 CleaningConfig 兼容片段 (LLM 不直接生成配置, 防止结构漂移).

输出的 ``cleaning_config`` 键与 ``CleaningConfig`` 的子配置对齐
(missing / duplicate / outlier / date), 可直接嵌入 pipeline/auto 的清洗配置 YAML.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List

import pandas as pd

from dqengine.ai.llm import LLMProviderBase, LLMAPIError, extract_json
from dqengine.core.profiler import Profiler
from dqengine.models.schemas import RepairSuggestion

__all__ = ["RepairAdvisor"]

# 可映射进 CleaningConfig 的动作白名单 (manual 仅展示不映射)
ACTIONS = (
    "fill_mean",
    "fill_median",
    "fill_mode",
    "fill_constant",
    "drop_null",
    "remove_outliers",
    "flag_outliers",
    "deduplicate",
    "standardize_date",
    "manual",
)

SYSTEM_PROMPT = (
    "你是数据质量专家。根据给出的数据集统计画像, 识别存在的问题并为每列给出修复建议。\n"
    '只输出一个 JSON 对象: {"issues": [{"column": "列名", "issue": "问题描述", '
    '"severity": "high|medium|low", "action": "动作", "params": {}, "reasoning": "理由"}]}\n'
    "action 仅限: fill_mean, fill_median, fill_mode, fill_constant, drop_null, "
    "remove_outliers, flag_outliers, deduplicate, standardize_date, manual。\n"
    "fill_constant 需在 params 中给出 constant_value。数据没有问题的列不要输出。"
    "只输出 JSON, 不要其他文字。"
)

# 每个清洗配置段只保留第一条命中的建议 (config 每类只有一份)
_NULL_ACTIONS = {"fill_mean": "mean", "fill_median": "median", "fill_mode": "mode",
                "fill_constant": "constant", "drop_null": "drop"}
_OUTLIER_ACTIONS = {"remove_outliers": "remove", "flag_outliers": "flag"}


class RepairAdvisor:
    """LLM 驱动的修复建议器."""

    def __init__(self, provider: LLMProviderBase, sample_rows: int = 5) -> None:
        self.provider = provider
        self.sample_rows = max(1, sample_rows)

    def suggest(self, df: pd.DataFrame) -> RepairSuggestion:
        """分析 DataFrame, 返回问题列表与可执行的清洗配置片段."""
        start_time = time.time()
        profile_summary = self._build_summary(df)

        user_prompt = (
            f"数据共 {len(df)} 行 {len(df.columns)} 列。统计画像 JSON:\n"
            f"{json.dumps(profile_summary, ensure_ascii=False, default=str)}"
        )
        reply = self.provider.chat(SYSTEM_PROMPT, user_prompt, json_mode=True)
        try:
            payload = extract_json(reply)
        except ValueError as e:
            raise LLMAPIError(f"LLM 返回内容无法解析为建议 JSON: {e}") from e

        issues, warnings = self._parse_issues(payload, df)
        config = self._build_cleaning_config(issues, warnings)
        return RepairSuggestion(
            issues=issues,
            cleaning_config=config,
            generated_by=f"llm:{getattr(self.provider, 'model', self.provider.name)}",
            generation_time_ms=round((time.time() - start_time) * 1000, 2),
            warnings=warnings,
        )

    # ------------------------------------------------------------------

    def _build_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """构建发送给 LLM 的画像摘要 (Profiler 统计 + 每列要点)."""
        profiler = Profiler()
        result = profiler.profile(df, duplicate_row_count=None)
        columns: Dict[str, Dict[str, Any]] = {}
        for col_profile in result.columns:
            info: Dict[str, Any] = {
                "dtype": col_profile.dtype,
                "null_count": col_profile.null_count,
                "null_rate": col_profile.null_rate,
                "unique_count": col_profile.unique_count,
            }
            series = df[col_profile.column_name]
            if pd.api.types.is_numeric_dtype(series):
                for key in ("mean", "std", "min_val", "max_val"):
                    value = getattr(col_profile, key)
                    if value is not None:
                        info[key] = value
            else:
                info["sample_values"] = (
                    series.dropna().head(self.sample_rows).astype(str).tolist()
                )
            columns[col_profile.column_name] = info
        return {
            "row_count": result.row_count,
            "duplicate_row_rate": result.duplicate_row_rate,
            "columns": columns,
        }

    def _parse_issues(
        self, payload: Dict[str, Any], df: pd.DataFrame
    ) -> "tuple[List[Any], List[str]]":
        from dqengine.models.schemas import RepairIssue

        raw_issues = payload.get("issues")
        if not isinstance(raw_issues, list):
            return [], ["LLM 未返回 issues 结构"]

        issues: List[Any] = []
        warnings: List[str] = []
        for item in raw_issues:
            if not isinstance(item, dict):
                continue
            column = str(item.get("column", ""))
            action = str(item.get("action", "")).strip()
            if column and column not in df.columns:
                if action in ("deduplicate", "standardize_date", "manual"):
                    # 数据集级动作不依赖具体列, 列名不符时归一为整体建议
                    column = "(数据集整体)"
                else:
                    warnings.append(f"忽略未知列 '{column}' 的建议")
                    continue
            if action not in ACTIONS:
                warnings.append(f"列 '{column}': 不支持的修复动作 '{action}' 已跳过")
                continue
            severity = str(item.get("severity", "medium")).lower()
            if severity not in ("high", "medium", "low"):
                severity = "medium"
            params = item.get("params")
            issues.append(
                RepairIssue(
                    column=column or "(数据集整体)",
                    issue=str(item.get("issue", "")),
                    severity=severity,
                    action=action,
                    params=params if isinstance(params, dict) else {},
                    reasoning=str(item.get("reasoning", "")),
                )
            )
        return issues, warnings

    def _build_cleaning_config(
        self, issues: List[Any], warnings: List[str]
    ) -> Dict[str, Any]:
        """把建议动作映射为 CleaningConfig 兼容片段 (本地合成, 非LLM生成)."""
        config: Dict[str, Any] = {}
        for issue in issues:
            action = issue.action
            if action in _NULL_ACTIONS and "missing" not in config:
                missing: Dict[str, Any] = {"strategy": _NULL_ACTIONS[action]}
                if action == "fill_constant":
                    constant = issue.params.get("constant_value")
                    if constant is None:
                        warnings.append(f"列 '{issue.column}': fill_constant 缺少 constant_value, 填充策略降级为 mean")
                        missing["strategy"] = "mean"
                    else:
                        missing["constant_value"] = str(constant)
                config["missing"] = missing
            elif action in _OUTLIER_ACTIONS and "outlier" not in config:
                config["outlier"] = {
                    "enabled": True,
                    "action": _OUTLIER_ACTIONS[action],
                }
            elif action == "deduplicate" and "duplicate" not in config:
                config["duplicate"] = {"enabled": True, "keep": "first"}
            elif action == "standardize_date" and "date" not in config:
                fmt = issue.params.get("target_format")
                date_cfg: Dict[str, Any] = {"enabled": True}
                if isinstance(fmt, str) and fmt:
                    date_cfg["target_format"] = fmt
                config["date"] = date_cfg
        return config
