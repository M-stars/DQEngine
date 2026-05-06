"""Tests for the RuleValidator module."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from dqengine.rules.validator import RuleValidator


class TestRuleValidator:
    def test_load_rules(self, tmp_path: Path) -> None:
        """Load rules from a YAML file."""
        yaml_content = """
columns:
  age:
    min: 0
    max: 120
  email:
    regex: email
"""
        rules_file = tmp_path / "rules.yaml"
        rules_file.write_text(yaml_content, encoding="utf-8")

        validator = RuleValidator()
        rules = validator.load_rules(rules_file)

        assert len(rules) == 2
        assert rules[0].column == "age"
        assert rules[0].rule_type == "range"
        assert rules[1].column == "email"
        assert rules[1].rule_type == "regex"

    def test_range_validation(self) -> None:
        """Validate numeric range constraints."""
        df = pd.DataFrame({"age": [25, -5, 150, 30]})
        validator = RuleValidator()

        result = validator.validate(df, rules=str(
            Path(__file__).parent.parent / "configs" / "rules.yaml"
        ))
        # Should have violations for age < 0 and age > 120
        age_violations = [v for v in result.violations if v.column == "age"]
        assert len(age_violations) == 2

    def test_regex_validation(self) -> None:
        """Validate regex pattern matching."""
        df = pd.DataFrame({
            "email": ["alice@example.com", "invalid-email", "bob@test.org"]
        })
        validator = RuleValidator()
        rules = validator.load_rules(
            Path(__file__).parent.parent / "configs" / "rules.yaml"
        )
        email_rules = [r for r in rules if r.column == "email"]

        result = validator.validate(df, rules=email_rules)
        violations = [v for v in result.violations if v.column == "email"]
        assert len(violations) == 1

    def test_not_null_validation(self) -> None:
        """Validate not-null constraints."""
        df = pd.DataFrame({"name": ["Alice", None, "Bob"]})
        validator = RuleValidator()
        rules = validator.load_rules(
            Path(__file__).parent.parent / "configs" / "rules.yaml"
        )
        name_rules = [r for r in rules if r.column == "name"]

        result = validator.validate(df, rules=name_rules)
        violations = [v for v in result.violations if v.column == "name"]
        assert len(violations) == 1

    def test_allowed_values_validation(self) -> None:
        """Validate allowed values constraints."""
        df = pd.DataFrame({"gender": ["Male", "Female", "Unknown", "Male"]})
        validator = RuleValidator()
        rules = validator.load_rules(
            Path(__file__).parent.parent / "configs" / "rules.yaml"
        )
        gender_rules = [r for r in rules if r.column == "gender"]

        result = validator.validate(df, rules=gender_rules)
        violations = [v for v in result.violations if v.column == "gender"]
        assert len(violations) == 1

    def test_missing_column(self) -> None:
        """Gracefully handle rules for columns not in the DataFrame."""
        from dqengine.models.schemas import ValidationRule

        df = pd.DataFrame({"x": [1, 2, 3]})
        rules = [ValidationRule(column="nonexistent", rule_type="not_null", params={})]
        validator = RuleValidator()
        result = validator.validate(df, rules=rules)

        assert not result.passed
        assert len(result.violations) == 1

    def test_all_pass(self) -> None:
        """All rules pass for clean data."""
        df = pd.DataFrame({"age": [25, 30, 45]})
        from dqengine.models.schemas import ValidationRule

        rules = [ValidationRule(column="age", rule_type="range", params={"min": 0, "max": 120})]
        validator = RuleValidator()
        result = validator.validate(df, rules=rules)

        assert result.passed
        assert len(result.violations) == 0
