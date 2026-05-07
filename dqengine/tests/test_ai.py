"""AI 规则生成测试."""

import numpy as np
import pandas as pd
import pytest

from dqengine.ai.generator import HeuristicRuleGenerator, LLMRuleGenerator


class TestHeuristicRuleGenerator:
    """统计推断规则生成器测试."""

    @pytest.fixture
    def generator(self):
        return HeuristicRuleGenerator()

    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "age": [25, 30, 35, 40, 45, 28, 33, 38, 42, 29],
            "email": [
                "a@x.com", "b@y.com", "c@z.com", "d@w.com", "e@v.com",
                "f@u.com", "g@t.com", "h@s.com", "i@r.com", "j@q.com",
            ],
            "name": ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
            "score": [85.5, 92.0, 78.3, 88.1, 95.2, 70.0, 82.5, 91.0, 87.3, 79.8],
            "category": ["X", "Y", "X", "Y", "Z", "X", "Y", "Z", "X", "Y"],
            "all_null": [np.nan] * 10,
        })

    def test_generate_returns_ruleset(self, generator, sample_df):
        result = generator.generate(sample_df)
        assert result.generated_by == "heuristic"
        assert result.generation_time_ms >= 0
        assert len(result.columns) > 0

    def test_type_rule_generated(self, generator, sample_df):
        result = generator.generate(sample_df)
        age_rules = result.columns.get("age", [])
        type_rules = [r for r in age_rules if r.rule_type == "type"]
        assert len(type_rules) > 0
        assert type_rules[0].params["expected_type"] == "int"

    def test_null_rule_on_non_null_column(self, generator, sample_df):
        result = generator.generate(sample_df)
        email_rules = result.columns.get("email", [])
        null_rules = [r for r in email_rules if r.rule_type == "nullable"]
        assert len(null_rules) > 0
        assert not null_rules[0].params["nullable"]

    def test_range_rule_on_numeric_column(self, generator, sample_df):
        result = generator.generate(sample_df)
        age_rules = result.columns.get("age", [])
        range_rules = [r for r in age_rules if r.rule_type == "range"]
        assert len(range_rules) > 0
        assert "min" in range_rules[0].params
        assert "max" in range_rules[0].params

    def test_regex_rule_for_email(self, generator, sample_df):
        result = generator.generate(sample_df)
        email_rules = result.columns.get("email", [])
        regex_rules = [r for r in email_rules if r.rule_type == "regex"]
        assert len(regex_rules) > 0
        assert any("email" in r.params.get("pattern_name", "") for r in regex_rules)

    def test_unique_rule_on_unique_column(self, generator, sample_df):
        result = generator.generate(sample_df)
        name_rules = result.columns.get("name", [])
        unique_rules = [r for r in name_rules if r.rule_type == "unique"]
        assert len(unique_rules) > 0
        assert unique_rules[0].params["should_be_unique"]

    def test_allowed_values_on_low_cardinality(self, generator, sample_df):
        result = generator.generate(sample_df)
        cat_rules = result.columns.get("category", [])
        allowed_rules = [r for r in cat_rules if r.rule_type == "allowed_values"]
        assert len(allowed_rules) > 0
        assert len(allowed_rules[0].params.get("values", [])) > 0

    def test_high_null_column_warning(self, generator, sample_df):
        result = generator.generate(sample_df)
        all_null_rules = result.columns.get("all_null", [])
        null_rules = [r for r in all_null_rules if r.rule_type == "nullable"]
        assert len(null_rules) > 0
        # 高缺失应有警告
        has_warning = any("all_null" in w for w in result.warnings)
        assert has_warning

    def test_specific_columns(self, generator, sample_df):
        result = generator.generate(sample_df, columns=["age", "score"])
        assert "age" in result.columns
        assert "score" in result.columns
        assert "name" not in result.columns

    def test_non_existent_column(self, generator, sample_df):
        result = generator.generate(sample_df, columns=["nonexistent"])
        assert any("nonexistent" in w for w in result.warnings)


class TestLLMRuleGenerator:
    """LLM 规则生成器 Stub 测试."""

    def test_stub_returns_empty(self):
        gen = LLMRuleGenerator(model_name="gpt-4o")
        result = gen.generate(pd.DataFrame({"a": [1, 2, 3]}))
        assert result.columns == {}
        assert "尚未实现" in result.warnings[0]
