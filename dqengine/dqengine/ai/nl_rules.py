"""自然语言规则生成 — 把中文/英文的数据质量要求转成 RuleValidator 可直接消费的 YAML.

用法::

    parser = NLRuleParser(provider)
    rules = parser.parse("age 必须在 0 到 150 之间, email 必须是有效邮箱且不能为空")
    # -> {"columns": {"age": {"min": 0, "max": 150},
    #                 "email": {"regex": "...", "not_null": True}}}

输出只含 RuleValidator 支持的四类键 (min/max, regex, not_null, allowed_values),
保证 ``dq validate --rules`` 可以直接消费, 不会出现"生成了规则但验证器静默忽略"的假通过.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from dqengine.ai.llm import LLMProviderBase, LLMAPIError, extract_json

__all__ = ["NLRuleParser", "SUPPORTED_KEYS"]

SUPPORTED_KEYS = ("min", "max", "regex", "not_null", "allowed_values")

SYSTEM_PROMPT = (
    "你是数据质量规则工程师。把用户的自然语言数据质量要求, 转成如下 JSON:\n"
    '{"columns": {"列名": {"min": 数值, "max": 数值, "regex": "正则", '
    '"not_null": true/false, "allowed_values": ["v1", "v2"]}}}\n'
    "每个列只能使用这些键: min, max, regex, not_null, allowed_values。\n"
    "min/max 用于数值范围; regex 用于格式约束 (如邮箱/手机号); not_null 表示非空; "
    "allowed_values 是允许的离散取值。\n"
    "没有提到的约束不要添加。列名必须与用户给的名字完全一致。只输出 JSON, 不要其他文字。"
)


class NLRuleParser:
    """自然语言 -> 验证规则的解析器 (LLM 驱动, 输出经白名单校验)."""

    def __init__(self, provider: LLMProviderBase) -> None:
        self.provider = provider

    def parse(
        self, text: str, df: Optional[pd.DataFrame] = None
    ) -> Dict[str, Dict[str, Any]]:
        """解析自然语言规则.

        Args:
            text: 规则描述, 如 "age 在 0-150 之间, email 不能为空".
            df: 可选, 提供后会把列名/类型加入提示词并对齐校验,
                LLM 返回的未知列会丢弃并记录到 warnings.

        Returns:
            {"columns": {col: {min/max/regex/not_null/allowed_values}}} —
            可直接 yaml.safe_dump 后交给 RuleValidator.
        """
        text = (text or "").strip()
        if not text:
            raise ValueError("规则描述不能为空")

        self.warnings: List[str] = []
        user_prompt = f"数据质量要求:\n{text}"
        if df is not None:
            col_types = {col: str(df[col].dtype) for col in df.columns}
            user_prompt += f"\n\n数据实际包含的列 (列名: 类型): {col_types}"

        reply = self.provider.chat(SYSTEM_PROMPT, user_prompt, json_mode=True)
        try:
            payload = extract_json(reply)
        except ValueError as e:
            raise LLMAPIError(f"LLM 返回内容无法解析为规则 JSON: {e}") from e
        return self._normalize(payload, df)

    # ------------------------------------------------------------------

    def _normalize(
        self, payload: Dict[str, Any], df: Optional[pd.DataFrame]
    ) -> Dict[str, Dict[str, Any]]:
        raw_columns = payload.get("columns")
        if not isinstance(raw_columns, dict):
            self.warnings.append("LLM 未返回 columns 结构, 结果为空")
            return {"columns": {}}

        columns: Dict[str, Dict[str, Any]] = {}
        for col, spec in raw_columns.items():
            if not isinstance(spec, dict):
                continue
            if df is not None and col not in df.columns:
                self.warnings.append(f"忽略规则中的未知列 '{col}' (数据中不存在)")
                continue
            clean: Dict[str, Any] = {}
            for key in SUPPORTED_KEYS:
                if key not in spec:
                    continue
                value = spec[key]
                if key == "allowed_values":
                    if isinstance(value, list) and value:
                        clean[key] = [str(v) for v in value]
                    else:
                        self.warnings.append(f"列 '{col}': allowed_values 必须是非空数组, 已跳过")
                elif key == "not_null":
                    clean[key] = bool(value)
                elif key in ("min", "max"):
                    try:
                        clean[key] = float(value) if not float(value).is_integer() else int(float(value))
                    except (TypeError, ValueError):
                        self.warnings.append(f"列 '{col}': {key} 不是数值, 已跳过")
                else:  # regex
                    clean[key] = str(value)
            if clean:
                columns[col] = clean
            else:
                self.warnings.append(f"列 '{col}': 未产生任何受支持的约束, 已跳过")
        return {"columns": columns}
