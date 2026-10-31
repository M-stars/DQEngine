"""LLM 集成测试: Provider 层 / LLMRuleGenerator / NLRuleParser / RepairAdvisor / CLI.

全部使用 Fake Provider, 不发起网络请求.
"""

import json
from unittest import mock

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from dqengine.ai.generator import LLMRuleGenerator
from dqengine.ai.llm import (
    LLMAPIError,
    LLMProviderBase,
    OpenAIProvider,
    OllamaProvider,
    extract_json,
    make_provider,
    resolve_api_key,
)
from dqengine.ai.nl_rules import NLRuleParser
from dqengine.ai.repair_advisor import RepairAdvisor
from dqengine.rules.validator import RuleValidator


class FakeLLM(LLMProviderBase):
    """可控回复的假 Provider."""

    name = "fake"
    model = "fake-model"

    def __init__(self, reply: str = "{}") -> None:
        self.reply = reply
        self.calls: list = []

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        self.calls.append({"system": system, "user": user, "json_mode": json_mode})
        return self.reply


SAMPLE_DF = pd.DataFrame(
    {
        "age": [25, 30, 35, 40, 45],
        "email": ["a@x.com", "b@y.com", "c@z.com", "d@w.com", "e@v.com"],
        "city": ["北京", "上海", "北京", "广州", "上海"],
    }
)


# ============================================================================
# Provider 层
# ============================================================================


class TestResolveApiKey:
    def test_explicit_wins(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        assert resolve_api_key("explicit") == "explicit"

    def test_env_fallback(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("DQENGINE_LLM_API_KEY", "dq-key")
        assert resolve_api_key() == "dq-key"

    def test_openai_env_fallback(self, monkeypatch):
        monkeypatch.delenv("DQENGINE_LLM_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "oa-key")
        assert resolve_api_key() == "oa-key"

    def test_missing(self, monkeypatch):
        monkeypatch.delenv("DQENGINE_LLM_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert resolve_api_key() is None


class TestOpenAIProvider:
    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("DQENGINE_LLM_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(LLMAPIError, match="API Key"):
            OpenAIProvider()

    def test_payload_and_response(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        captured = {}

        def fake_post(url, payload, headers, timeout):
            captured.update({"url": url, "payload": payload, "headers": headers})
            return {"choices": [{"message": {"content": "hello"}}]}

        with mock.patch("dqengine.ai.llm._post_json", side_effect=fake_post):
            provider = OpenAIProvider(model="test-model", base_url="https://api.x.com/v1/")
            assert provider.chat("sys", "usr", json_mode=True) == "hello"

        assert captured["url"] == "https://api.x.com/v1/chat/completions"
        assert captured["payload"]["model"] == "test-model"
        assert captured["payload"]["response_format"] == {"type": "json_object"}
        assert captured["payload"]["messages"][0] == {"role": "system", "content": "sys"}
        assert captured["headers"]["Authorization"] == "Bearer k"

    def test_no_json_mode_flag(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        captured = {}

        def fake_post(url, payload, headers, timeout):
            captured["payload"] = payload
            return {"choices": [{"message": {"content": "ok"}}]}

        with mock.patch("dqengine.ai.llm._post_json", side_effect=fake_post):
            OpenAIProvider().chat("s", "u", json_mode=False)
        assert "response_format" not in captured["payload"]

    def test_bad_response_shape(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        with mock.patch("dqengine.ai.llm._post_json", return_value={"nope": 1}):
            with pytest.raises(LLMAPIError, match="响应格式异常"):
                OpenAIProvider().chat("s", "u")


class TestOllamaProvider:
    def test_payload(self):
        captured = {}

        def fake_post(url, payload, headers, timeout):
            captured.update({"url": url, "payload": payload})
            return {"message": {"content": "hi"}}

        with mock.patch("dqengine.ai.llm._post_json", side_effect=fake_post):
            provider = OllamaProvider(model="m")
            assert provider.chat("s", "u", json_mode=True) == "hi"

        assert captured["url"].endswith("/api/chat")
        assert captured["payload"]["stream"] is False
        assert captured["payload"]["format"] == "json"

    def test_ollama_host_env(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://gpu-box:11434/")
        assert OllamaProvider().base_url == "http://gpu-box:11434"


class TestMakeProvider:
    def test_openai(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        p = make_provider("openai", model="m1")
        assert isinstance(p, OpenAIProvider)
        assert p.model == "m1"

    def test_ollama(self):
        assert isinstance(make_provider("ollama", model="m2"), OllamaProvider)

    def test_unknown(self):
        with pytest.raises(LLMAPIError, match="未知 LLM Provider"):
            make_provider("anthropic")


class TestExtractJson:
    def test_plain(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_fenced(self):
        text = "好的, 以下是结果:\n```json\n{\"a\": {\"b\": 2}}\n```\n以上。"
        assert extract_json(text) == {"a": {"b": 2}}

    def test_braces_inside_string(self):
        text = '{"s": "包含 } 和 { 的字符串", "n": 1}'
        assert extract_json(text)["n"] == 1

    def test_surrounding_chatter(self):
        text = '前言 {"columns": {}} 后记'
        assert extract_json(text) == {"columns": {}}

    def test_empty(self):
        with pytest.raises(ValueError):
            extract_json("")

    def test_no_json(self):
        with pytest.raises(ValueError):
            extract_json("没有任何 JSON")

    def test_truncated(self):
        with pytest.raises(ValueError):
            extract_json('{"a": {"b": 1}')

    def test_top_level_not_object(self):
        with pytest.raises(ValueError):
            extract_json("[1, 2]")


# ============================================================================
# LLMRuleGenerator
# ============================================================================


class TestLLMRuleGenerator:
    def test_basic_rules(self):
        reply = json.dumps(
            {
                "columns": {
                    "age": [
                        {"rule_type": "range", "params": {"min": 0, "max": 150}, "confidence": 0.9, "reasoning": "年龄"}
                    ],
                    "email": [
                        {"rule_type": "regex", "params": {"pattern": "^.+@.+$"}, "confidence": 0.95, "reasoning": "邮箱"}
                    ],
                }
            }
        )
        provider = FakeLLM(reply)
        result = LLMRuleGenerator(provider=provider).generate(SAMPLE_DF)

        assert result.generated_by == "llm:fake-model"
        assert "age" in result.columns and "email" in result.columns
        assert result.columns["age"][0].rule_type == "range"
        assert result.warnings == []
        # 画像调用参数: json_mode 开启, prompt 含列名
        assert provider.calls[0]["json_mode"] is True
        assert "age" in provider.calls[0]["user"]
        assert "email" in provider.calls[0]["user"]

    def test_fenced_reply(self):
        reply = "```json\n" + json.dumps({"columns": {"age": [{"rule_type": "range", "params": {"min": 0, "max": 100}, "confidence": 0.8}]}}) + "\n```"
        result = LLMRuleGenerator(provider=FakeLLM(reply)).generate(SAMPLE_DF)
        assert result.columns["age"][0].params["max"] == 100

    def test_unsupported_rule_type_skipped(self):
        reply = json.dumps(
            {
                "columns": {
                    "age": [
                        {"rule_type": "fuzzy_match", "params": {}, "confidence": 0.9},
                        {"rule_type": "range", "params": {"min": 0, "max": 100}, "confidence": 0.8},
                    ]
                }
            }
        )
        result = LLMRuleGenerator(provider=FakeLLM(reply)).generate(SAMPLE_DF)
        types = [r.rule_type for r in result.columns["age"]]
        assert types == ["range"]
        assert any("fuzzy_match" in w for w in result.warnings)

    def test_unknown_column_ignored(self):
        reply = json.dumps(
            {
                "columns": {
                    "ghost": [{"rule_type": "range", "params": {"min": 0, "max": 1}, "confidence": 0.9}],
                    "age": [{"rule_type": "range", "params": {"min": 0, "max": 100}, "confidence": 0.8}],
                }
            }
        )
        result = LLMRuleGenerator(provider=FakeLLM(reply)).generate(SAMPLE_DF)
        assert "ghost" not in result.columns
        assert "age" in result.columns
        assert any("ghost" in w for w in result.warnings)

    def test_confidence_clamped(self):
        reply = json.dumps(
            {
                "columns": {
                    "age": [
                        {"rule_type": "range", "params": {}, "confidence": 7.5},
                        {"rule_type": "range", "params": {}, "confidence": "bad"},
                    ]
                }
            }
        )
        result = LLMRuleGenerator(provider=FakeLLM(reply)).generate(SAMPLE_DF)
        confidences = [r.confidence for r in result.columns["age"]]
        assert confidences[0] == 1.0
        assert confidences[1] == 0.5  # 非法值回退缺省

    def test_invalid_json_raises(self):
        with pytest.raises(LLMAPIError, match="无法解析"):
            LLMRuleGenerator(provider=FakeLLM("这不是 JSON")).generate(SAMPLE_DF)

    def test_missing_columns_structure(self):
        result = LLMRuleGenerator(provider=FakeLLM('{"foo": 1}')).generate(SAMPLE_DF)
        assert result.columns == {}
        assert any("columns" in w for w in result.warnings)

    def test_profile_only_summary_not_full_data(self):
        """发送给 LLM 的画像只含统计摘要与少量样本, 不含整表数据."""
        big = pd.DataFrame({"secret": [f"row-{i}-/confidential" for i in range(1000)]})
        provider = FakeLLM('{"columns": {}}')
        LLMRuleGenerator(provider=provider, sample_rows=3).generate(big)
        prompt = provider.calls[0]["user"]
        assert "row-0" in prompt  # 样本值允许出现
        assert "row-10" not in prompt  # 整表不允许
        assert "null_rate" in prompt

    def test_explicit_missing_column_warns(self):
        result = LLMRuleGenerator(provider=FakeLLM('{"columns": {}}')).generate(SAMPLE_DF, columns=["nope"])
        assert any("nope" in w for w in result.warnings)


# ============================================================================
# NLRuleParser
# ============================================================================


class TestNLRuleParser:
    def test_basic_parse(self):
        reply = json.dumps(
            {
                "columns": {
                    "age": {"min": 0, "max": 150, "not_null": True},
                    "email": {"regex": "^.+@.+$", "not_null": True},
                }
            }
        )
        parser = NLRuleParser(FakeLLM(reply))
        rules = parser.parse("age 在 0-150 之间, email 是邮箱")
        assert rules["columns"]["age"] == {"min": 0, "max": 150, "not_null": True}
        assert rules["columns"]["email"]["regex"] == "^.+@.+$"
        assert parser.warnings == []

    def test_unknown_column_dropped_with_df(self):
        reply = json.dumps(
            {
                "columns": {
                    "ghost": {"not_null": True},
                    "age": {"min": 0, "max": 100},
                }
            }
        )
        parser = NLRuleParser(FakeLLM(reply))
        rules = parser.parse("规则", df=SAMPLE_DF)
        assert "ghost" not in rules["columns"]
        assert "age" in rules["columns"]
        assert any("ghost" in w for w in parser.warnings)

    def test_allowed_values_stringified(self):
        reply = json.dumps({"columns": {"city": {"allowed_values": ["北京", "上海", 3]}}})
        parser = NLRuleParser(FakeLLM(reply))
        rules = parser.parse("city 只能是北京上海", df=SAMPLE_DF)
        assert rules["columns"]["city"]["allowed_values"] == ["北京", "上海", "3"]

    def test_bad_min_skipped(self):
        reply = json.dumps({"columns": {"age": {"min": "abc", "max": 100}}})
        parser = NLRuleParser(FakeLLM(reply))
        rules = parser.parse("规则", df=SAMPLE_DF)
        assert rules["columns"]["age"] == {"max": 100}
        assert any("min" in w for w in parser.warnings)

    def test_unsupported_keys_dropped(self):
        reply = json.dumps({"columns": {"age": {"min": 0, "fuzzy": True, "custom": "x"}}})
        parser = NLRuleParser(FakeLLM(reply))
        rules = parser.parse("规则", df=SAMPLE_DF)
        assert rules["columns"]["age"] == {"min": 0}

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="不能为空"):
            NLRuleParser(FakeLLM()).parse("  ")

    def test_invalid_json_raises(self):
        with pytest.raises(LLMAPIError):
            NLRuleParser(FakeLLM("oops")).parse("规则")

    def test_roundtrip_to_rule_validator(self, tmp_path):
        """关键回归: NL 生成的规则 YAML 必须能被 RuleValidator 直接消费 (不假通过)."""
        reply = json.dumps(
            {
                "columns": {
                    "age": {"min": 0, "max": 150},
                    "email": {"regex": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", "not_null": True},
                }
            }
        )
        rules = NLRuleParser(FakeLLM(reply)).parse("描述", df=SAMPLE_DF)
        rules_path = tmp_path / "nl_rules.yaml"
        rules_path.write_text(yaml.dump(rules, allow_unicode=True), encoding="utf-8")

        validator = RuleValidator()
        bad_df = pd.DataFrame({"age": [200, -5], "email": ["not-an-email", None]})
        result = validator.validate(bad_df, rules_path)

        assert result.total_rules > 0
        # 两条规则都应产生违规, 而不是静默通过
        assert result.failed_rules >= 2
        columns_hit = {v.column for v in result.violations} if result.violations else set()
        assert {"age", "email"} <= columns_hit

        # 合法数据应全部通过
        good_df = pd.DataFrame({"age": [25, 30], "email": ["a@x.com", "b@y.com"]})
        ok_result = validator.validate(good_df, rules_path)
        assert ok_result.failed_rules == 0


# ============================================================================
# RepairAdvisor
# ============================================================================


class TestRepairAdvisor:
    def test_basic_suggestions(self):
        reply = json.dumps(
            {
                "issues": [
                    {"column": "age", "issue": "存在缺失", "severity": "high", "action": "fill_median", "reasoning": "中位数稳健"},
                    {"column": "city", "issue": "枚举值异常", "severity": "low", "action": "manual", "reasoning": "需人工确认"},
                ]
            }
        )
        df = SAMPLE_DF.copy()
        df.loc[0, "age"] = None
        suggestion = RepairAdvisor(FakeLLM(reply)).suggest(df)

        assert suggestion.generated_by == "llm:fake-model"
        assert len(suggestion.issues) == 2
        assert suggestion.issues[0].severity == "high"
        # cleaning_config 映射
        assert suggestion.cleaning_config["missing"] == {"strategy": "median"}
        assert "outlier" not in suggestion.cleaning_config  # manual 不映射

    def test_action_whitelist(self):
        reply = json.dumps(
            {
                "issues": [
                    {"column": "age", "issue": "x", "action": "drop_database", "reasoning": ""},
                    {"column": "age", "issue": "x", "action": "fill_mean", "reasoning": ""},
                ]
            }
        )
        suggestion = RepairAdvisor(FakeLLM(reply)).suggest(SAMPLE_DF)
        assert [i.action for i in suggestion.issues] == ["fill_mean"]
        assert any("drop_database" in w for w in suggestion.warnings)

    def test_unknown_column_warning(self):
        reply = json.dumps(
            {"issues": [{"column": "ghost", "issue": "x", "action": "fill_mean", "reasoning": ""}]}
        )
        suggestion = RepairAdvisor(FakeLLM(reply)).suggest(SAMPLE_DF)
        assert suggestion.issues == []
        assert any("ghost" in w for w in suggestion.warnings)

    def test_config_mapping_all_actions(self):
        reply = json.dumps(
            {
                "issues": [
                    {"column": "", "issue": "", "action": "deduplicate", "reasoning": ""},
                    {"column": "age", "issue": "", "action": "remove_outliers", "reasoning": ""},
                    {"column": "", "issue": "", "action": "standardize_date", "params": {"target_format": "%Y/%m/%d"}, "reasoning": ""},
                    {"column": "city", "issue": "", "action": "fill_constant", "params": {"constant_value": 0}, "reasoning": ""},
                ]
            }
        )
        suggestion = RepairAdvisor(FakeLLM(reply)).suggest(SAMPLE_DF)
        cfg = suggestion.cleaning_config
        assert cfg["duplicate"] == {"enabled": True, "keep": "first"}
        assert cfg["outlier"] == {"enabled": True, "action": "remove"}
        assert cfg["date"] == {"enabled": True, "target_format": "%Y/%m/%d"}
        assert cfg["missing"] == {"strategy": "constant", "constant_value": "0"}

    def test_dataset_level_action_with_ghost_column(self):
        """数据集级动作在列名对不上时归一为整体建议, 不丢弃."""
        reply = json.dumps(
            {"issues": [{"column": "dataset", "issue": "重复行", "action": "deduplicate", "reasoning": ""}]}
        )
        suggestion = RepairAdvisor(FakeLLM(reply)).suggest(SAMPLE_DF)
        assert len(suggestion.issues) == 1
        assert suggestion.issues[0].column == "(数据集整体)"
        assert suggestion.cleaning_config["duplicate"]["enabled"] is True

    def test_fill_constant_without_value_degrades(self):
        reply = json.dumps(
            {"issues": [{"column": "age", "issue": "", "action": "fill_constant", "params": {}, "reasoning": ""}]}
        )
        suggestion = RepairAdvisor(FakeLLM(reply)).suggest(SAMPLE_DF)
        assert suggestion.cleaning_config["missing"] == {"strategy": "mean"}
        assert any("constant_value" in w for w in suggestion.warnings)

    def test_duplicate_category_keeps_first(self):
        reply = json.dumps(
            {
                "issues": [
                    {"column": "age", "issue": "", "action": "fill_mean", "reasoning": ""},
                    {"column": "email", "issue": "", "action": "drop_null", "reasoning": ""},
                ]
            }
        )
        suggestion = RepairAdvisor(FakeLLM(reply)).suggest(SAMPLE_DF)
        assert suggestion.cleaning_config["missing"] == {"strategy": "mean"}  # 只取第一条

    def test_invalid_json_raises(self):
        with pytest.raises(LLMAPIError):
            RepairAdvisor(FakeLLM(" bad ")).suggest(SAMPLE_DF)


# ============================================================================
# CLI
# ============================================================================


runner = CliRunner()


class TestCliAI:
    def test_generate_rules_llm_missing_key(self, monkeypatch):
        monkeypatch.delenv("DQENGINE_LLM_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from dqengine.cli.commands import app

        result = runner.invoke(app, ["ai", "generate-rules", "examples/sample.csv", "-p", "openai"])
        assert result.exit_code == 1
        assert "API Key" in result.output

    def test_generate_rules_llm_mocked(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        reply = json.dumps(
            {"columns": {"age": [{"rule_type": "range", "params": {"min": 0, "max": 150}, "confidence": 0.9}]}}
        )

        def fake_make(provider, model=None, api_key=None, base_url=None, timeout=60.0):
            assert provider == "openai"
            return FakeLLM(reply)

        with mock.patch("dqengine.ai.llm.make_provider", side_effect=fake_make):
            from dqengine.cli.commands import app

            out = tmp_path / "rules.yaml"
            result = runner.invoke(
                app,
                ["ai", "generate-rules", "examples/sample.csv", "-p", "openai", "-o", str(out)],
            )
        assert result.exit_code == 0, result.output
        saved = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert saved["columns"]["age"]["max"] == 150

    def test_parse_rules_mocked(self, tmp_path):
        reply = json.dumps({"columns": {"age": {"min": 0, "max": 150}, "email": {"not_null": True}}})
        with mock.patch(
            "dqengine.ai.llm.make_provider", return_value=FakeLLM(reply)
        ):
            from dqengine.cli.commands import app

            out = tmp_path / "nl_rules.yaml"
            result = runner.invoke(
                app,
                [
                    "ai", "parse-rules",
                    "age 在 0-150 之间, email 不能为空",
                    "-f", "examples/sample.csv",
                    "-o", str(out),
                ],
            )
        assert result.exit_code == 0, result.output
        saved = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert saved["columns"]["age"] == {"min": 0, "max": 150}

    def test_parse_rules_nothing_extracted(self):
        with mock.patch("dqengine.ai.llm.make_provider", return_value=FakeLLM('{"columns": {}}')):
            from dqengine.cli.commands import app

            result = runner.invoke(app, ["ai", "parse-rules", "随便说说"])
        assert result.exit_code == 1
        assert "未能" in result.output

    def test_suggest_fixes_mocked(self, tmp_path):
        reply = json.dumps(
            {"issues": [{"column": "age", "issue": "缺失", "severity": "high", "action": "fill_median", "reasoning": "r"}]}
        )
        with mock.patch("dqengine.ai.llm.make_provider", return_value=FakeLLM(reply)):
            from dqengine.cli.commands import app

            out = tmp_path / "fixes.yaml"
            result = runner.invoke(app, ["ai", "suggest-fixes", "examples/sample.csv", "-o", str(out)])
        assert result.exit_code == 0, result.output
        saved = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert saved["issues"][0]["action"] == "fill_median"
        assert saved["cleaning_config"]["missing"] == {"strategy": "median"}

    def test_suggest_fixes_file_missing(self):
        from dqengine.cli.commands import app

        result = runner.invoke(app, ["ai", "suggest-fixes", "no_such_file.csv"])
        assert result.exit_code == 1
