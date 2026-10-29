"""YAML rule-based data validation engine."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from dqengine.models.schemas import ValidationRule, ValidationResult, RuleViolation


class RuleValidator:
    """Validate a DataFrame against rules defined in a YAML file.

    Supported rule types:
        - min / max: numeric range validation
        - regex: pattern matching (e.g., email, phone)
        - not_null: non-null check
        - allowed_values: discrete value set check

    Usage:
        validator = RuleValidator()
        result = validator.validate(df, "rules.yaml")
    """

    def load_rules(self, rules_path: "str | Path") -> list[ValidationRule]:
        """Parse a YAML rules file into ValidationRule objects.

        Args:
            rules_path: Path to a YAML file with validation rules.

        Returns:
            List of ValidationRule objects.
        """
        path = Path(rules_path)
        if not path.exists():
            raise FileNotFoundError(f"Rules file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        return self._parse_rules(raw)

    def validate(
        self, df: pd.DataFrame, rules: "str | Path | list[ValidationRule]"
    ) -> ValidationResult:
        """Validate a DataFrame against rules.

        Args:
            df: Input DataFrame.
            rules: Path to YAML rules file or list of ValidationRule objects.

        Returns:
            ValidationResult with pass/fail status and violations.
        """
        if isinstance(rules, (str, Path)):
            parsed_rules = self.load_rules(rules)
        else:
            parsed_rules = rules

        all_violations: list[RuleViolation] = []

        for rule in parsed_rules:
            violations = self._check_rule(df, rule)
            all_violations.extend(violations)

        total = len(parsed_rules)
        failed_rules = len(set(v.column + v.rule_type for v in all_violations))
        passed_rules = total - failed_rules

        return ValidationResult(
            passed=len(all_violations) == 0,
            total_rules=total,
            passed_rules=passed_rules,
            failed_rules=failed_rules,
            total_violations=len(all_violations),
            violations=all_violations,
        )

    def _parse_rules(self, raw: dict) -> list[ValidationRule]:
        """Convert YAML dict to list of ValidationRule objects."""
        rules: list[ValidationRule] = []

        # 空 YAML 解析为 None, 顶层为列表等其他形态也无法提取 columns 键
        if not isinstance(raw, dict):
            return []

        columns_rules = raw.get("columns", {})
        for col_name, col_rules in columns_rules.items():
            if not isinstance(col_rules, dict):
                continue

            # Range rules
            if "min" in col_rules or "max" in col_rules:
                params = {}
                if "min" in col_rules:
                    params["min"] = col_rules["min"]
                if "max" in col_rules:
                    params["max"] = col_rules["max"]
                rules.append(
                    ValidationRule(column=col_name, rule_type="range", params=params)
                )

            # Regex rule
            if "regex" in col_rules:
                rules.append(
                    ValidationRule(
                        column=col_name,
                        rule_type="regex",
                        params={"pattern": col_rules["regex"]},
                    )
                )

            # Not-null rule
            if col_rules.get("not_null", False):
                rules.append(
                    ValidationRule(column=col_name, rule_type="not_null", params={})
                )

            # Allowed values
            if "allowed_values" in col_rules:
                rules.append(
                    ValidationRule(
                        column=col_name,
                        rule_type="allowed_values",
                        params={"values": col_rules["allowed_values"]},
                    )
                )

        return rules

    def _check_rule(
        self, df: pd.DataFrame, rule: ValidationRule
    ) -> list[RuleViolation]:
        """Execute a single validation rule against the DataFrame."""
        if rule.column not in df.columns:
            return [
                RuleViolation(
                    column=rule.column,
                    rule_type=rule.rule_type,
                    row_index=-1,
                    value=None,
                    message=f"Column '{rule.column}' not found in data",
                )
            ]

        if rule.rule_type == "range":
            return self._check_range(df, rule)
        elif rule.rule_type == "regex":
            return self._check_regex(df, rule)
        elif rule.rule_type == "not_null":
            return self._check_not_null(df, rule)
        elif rule.rule_type == "allowed_values":
            return self._check_allowed_values(df, rule)
        else:
            return []

    def _check_range(
        self, df: pd.DataFrame, rule: ValidationRule
    ) -> list[RuleViolation]:
        """Validate numeric range."""
        violations = []
        series = pd.to_numeric(df[rule.column], errors="coerce")

        # 阈值规整为数值: YAML 中带引号的数字 ("18") 否则会与数值比较失败
        try:
            min_val = (
                float(rule.params["min"]) if rule.params.get("min") is not None else None
            )
            max_val = (
                float(rule.params["max"]) if rule.params.get("max") is not None else None
            )
        except (TypeError, ValueError) as e:
            return [
                RuleViolation(
                    column=rule.column,
                    rule_type="range",
                    row_index=-1,
                    value=None,
                    message=f"规则阈值必须是数值: {e}",
                )
            ]

        # 按位置遍历: 重复/非整数索引标签下 series[label] 会返回多值
        # Series 或抛 int() 转换错误
        for pos, (idx, val) in enumerate(series.items()):
            if pd.isna(val):
                original = df[rule.column].iloc[pos]
                if not pd.isna(original):
                    # 原值存在但无法转为数值: 非数值垃圾必须报违规,
                    # 否则 "abc" 会静默通过 min/max 校验
                    violations.append(
                        RuleViolation(
                            column=rule.column,
                            rule_type="range",
                            row_index=pos,
                            value=str(original),
                            message=f"Value '{original}' is not numeric",
                        )
                    )
                continue
            if min_val is not None and val < min_val:
                violations.append(
                    RuleViolation(
                        column=rule.column,
                        rule_type="range",
                        row_index=pos,
                        value=float(val),
                        message=f"Value {val} < min({min_val})",
                    )
                )
            elif max_val is not None and val > max_val:
                violations.append(
                    RuleViolation(
                        column=rule.column,
                        rule_type="range",
                        row_index=pos,
                        value=float(val),
                        message=f"Value {val} > max({max_val})",
                    )
                )
        return violations

    def _check_regex(
        self, df: pd.DataFrame, rule: ValidationRule
    ) -> list[RuleViolation]:
        """Validate against a regex pattern."""
        violations = []
        pattern = rule.params.get("pattern", "")

        # Named patterns
        named_patterns = {
            "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
            # 要求至少 4 位数字, 否则 "-------"/连续空格等纯符号串也会通过
            "phone": r"^(?=(?:\D*\d){4})\+?[\d\s\-()]{7,20}$",
            "url": r"^https?://[^\s/$.?#].[^\s]*$",
            "date": r"^\d{4}-\d{2}-\d{2}$",
        }

        if pattern in named_patterns:
            pattern = named_patterns[pattern]

        try:
            compiled = re.compile(pattern)
        except re.error:
            return [
                RuleViolation(
                    column=rule.column,
                    rule_type="regex",
                    row_index=-1,
                    value=pattern,
                    message=f"Invalid regex pattern: {pattern}",
                )
            ]

        for pos, (idx, val) in enumerate(df[rule.column].items()):
            if pd.isna(val):
                continue
            if not compiled.search(str(val)):
                violations.append(
                    RuleViolation(
                        column=rule.column,
                        rule_type="regex",
                        row_index=pos,
                        value=str(val),
                        message=f"'{val}' does not match pattern '{rule.params.get('pattern')}'",
                    )
                )
        return violations

    def _check_not_null(
        self, df: pd.DataFrame, rule: ValidationRule
    ) -> list[RuleViolation]:
        """Validate non-null constraint."""
        violations = []
        for pos, (idx, val) in enumerate(df[rule.column].items()):
            if pd.isna(val):
                violations.append(
                    RuleViolation(
                        column=rule.column,
                        rule_type="not_null",
                        row_index=pos,
                        value=None,
                        message=f"Null value found at row {idx}",
                    )
                )
        return violations

    def _check_allowed_values(
        self, df: pd.DataFrame, rule: ValidationRule
    ) -> list[RuleViolation]:
        """Validate against a set of allowed values."""
        violations = []
        allowed: set[Any] = set(rule.params.get("values", []))

        for pos, (idx, val) in enumerate(df[rule.column].items()):
            if pd.isna(val):
                continue
            if val not in allowed:
                violations.append(
                    RuleViolation(
                        column=rule.column,
                        rule_type="allowed_values",
                        row_index=pos,
                        value=str(val),
                        message=f"'{val}' not in allowed values: {allowed}",
                    )
                )
        return violations
