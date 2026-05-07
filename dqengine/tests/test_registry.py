"""注册中心测试."""

import pytest

from dqengine.registry.pattern_registry import PatternRegistry, get_pattern_registry
from dqengine.models.schemas import SemanticType, SemanticPattern


class TestPatternRegistry:
    """PatternRegistry 单元测试."""

    @pytest.fixture
    def registry(self):
        return PatternRegistry()

    def test_match_email_column(self, registry):
        """测试匹配邮箱字段名."""
        matches = registry.match_column("email_addr")
        assert len(matches) > 0
        assert matches[0].semantic_type == SemanticType.EMAIL

    def test_match_phone_column(self, registry):
        """测试匹配手机号字段名 (中文)."""
        matches = registry.match_column("手机号")
        assert len(matches) > 0
        assert matches[0].semantic_type == SemanticType.PHONE_NUMBER

    def test_match_case_insensitive(self, registry):
        """测试大小写不敏感."""
        matches = registry.match_column("Email")
        assert len(matches) > 0
        assert matches[0].semantic_type == SemanticType.EMAIL

    def test_no_match(self, registry):
        """测试无匹配."""
        matches = registry.match_column("xyz_unknown_field")
        assert len(matches) == 0

    def test_get_all_sorted_by_priority(self, registry):
        """测试按优先级排序."""
        patterns = registry.get_all()
        for i in range(len(patterns) - 1):
            assert patterns[i].priority >= patterns[i + 1].priority

    def test_get_builtin(self, registry):
        """测试内置模式."""
        builtin = registry.get_builtin()
        assert len(builtin) > 10

    def test_get_by_type(self, registry):
        """测试按类型获取."""
        email_patterns = registry.get_by_type(SemanticType.EMAIL)
        assert len(email_patterns) > 0
        assert all(p.semantic_type == SemanticType.EMAIL for p in email_patterns)

    def test_register_custom(self, registry):
        """测试注册自定义模式."""
        custom = SemanticPattern(
            name="test_custom",
            semantic_type=SemanticType.NAME,
            column_patterns=["custom_field"],
            priority=20,
        )
        registry.register(custom)

        matches = registry.match_column("custom_field")
        assert len(matches) > 0
        assert matches[0].name == "test_custom"

    def test_unregister(self, registry):
        """测试注销模式."""
        custom = SemanticPattern(
            name="to_remove",
            semantic_type=SemanticType.UNKNOWN,
            column_patterns=["removable"],
            priority=1,
        )
        registry.register(custom)
        assert len(registry.get_custom()) == 1

        removed = registry.unregister("to_remove")
        assert removed
        assert len(registry.get_custom()) == 0

    def test_unregister_nonexistent(self, registry):
        """测试注销不存在的模式."""
        assert not registry.unregister("nonexistent")

    def test_get_custom_empty(self, registry):
        """测试空自定义模式."""
        assert registry.get_custom() == []

    def test_global_singleton(self):
        """测试全局单例."""
        r1 = get_pattern_registry()
        r2 = get_pattern_registry()
        assert r1 is r2


class TestPatternRegistryPatterns:
    """测试具体模式的匹配行为."""

    @pytest.fixture
    def registry(self):
        return PatternRegistry()

    @pytest.mark.parametrize("col_name,expected_type", [
        ("email", SemanticType.EMAIL),
        ("E-mail", SemanticType.EMAIL),
        ("phone", SemanticType.PHONE_NUMBER),
        ("mobile", SemanticType.PHONE_NUMBER),
        ("电话", SemanticType.PHONE_NUMBER),
        ("date", SemanticType.DATETIME),
        ("created_at", SemanticType.DATETIME),
        ("price", SemanticType.CURRENCY),
        ("salary", SemanticType.CURRENCY),
        ("uuid", SemanticType.UUID),
        ("ip_address", SemanticType.IP_ADDRESS),
        ("url", SemanticType.URL),
        ("id", SemanticType.UUID),  # UUID优先级高于ID
        ("country", SemanticType.COUNTRY),
        ("city", SemanticType.CITY),
        ("age", SemanticType.AGE),
        ("gender", SemanticType.GENDER),
        ("name", SemanticType.NAME),
    ])
    def test_column_name_matching(self, registry, col_name, expected_type):
        """参数化测试字段名匹配."""
        matches = registry.match_column(col_name)
        assert len(matches) > 0
        assert matches[0].semantic_type == expected_type
