"""插件系统测试."""

import pytest
import pandas as pd

from dqengine.models.schemas import PluginInfo, PluginType, RuleViolation
from dqengine.plugins.base import BasePlugin, BaseValidator, BaseCleaner, BaseScorer
from dqengine.registry.plugin_registry import PluginRegistry, get_plugin_registry


class TestBasePlugin:
    """BasePlugin 单元测试."""

    def test_plugin_creation(self):
        """测试插件创建."""

        class TestPlugin(BaseValidator):
            PLUGIN_INFO = PluginInfo(
                name="test_plugin",
                plugin_type=PluginType.VALIDATOR,
                description="测试插件",
            )

            def validate(self, df, column):
                return []

        plugin = TestPlugin()
        assert plugin.name == "test_plugin"
        assert plugin.plugin_type == PluginType.VALIDATOR
        assert plugin.enabled is True

    def test_plugin_enable_disable(self):
        """测试插件启停."""

        class TestPlugin(BaseValidator):
            PLUGIN_INFO = PluginInfo(
                name="test_enable",
                plugin_type=PluginType.VALIDATOR,
                description="测试启停",
            )

            def validate(self, df, column):
                return []

        plugin = TestPlugin()
        assert plugin.enabled

        plugin.disable()
        assert not plugin.enabled

        plugin.enable()
        assert plugin.enabled

    def test_base_validator_raises(self):
        """测试抽象基类实例化报错."""
        with pytest.raises(TypeError):
            BaseValidator()

    def test_base_cleaner_raises(self):
        """测试抽象清洗器实例化报错."""
        with pytest.raises(TypeError):
            BaseCleaner()

    def test_base_scorer_raises(self):
        """测试抽象评分器实例化报错."""
        with pytest.raises(TypeError):
            BaseScorer()


class TestPluginRegistry:
    """PluginRegistry 单元测试."""

    @pytest.fixture
    def registry(self):
        """创建干净的注册中心."""
        reg = PluginRegistry()
        return reg

    def test_empty_registry(self, registry):
        """测试空注册中心."""
        assert len(registry.list_plugins()) == 0

    def test_list_by_type_empty(self, registry):
        """测试按类型列出空注册中心."""
        assert registry.get_by_type(PluginType.VALIDATOR) == []

    def test_is_loaded(self, registry):
        """测试is_loaded."""
        assert not registry.is_loaded("nonexistent")

    def test_get_none(self, registry):
        """测试获取不存在的插件."""
        assert registry.get("nonexistent") is None


class TestCustomPhoneValidator:
    """自定义手机号验证器测试."""

    def test_valid_phone(self):
        """测试合法手机号."""
        from dqengine.plugins.custom_phone_validator import CustomPhoneValidator

        validator = CustomPhoneValidator()
        df = pd.DataFrame({"phone": ["13800138000", "13912345678"]})
        violations = validator.validate(df, "phone")
        assert len(violations) == 0

    def test_invalid_phone(self):
        """测试不合法手机号."""
        from dqengine.plugins.custom_phone_validator import CustomPhoneValidator

        validator = CustomPhoneValidator()
        df = pd.DataFrame({"phone": ["12345", "abc", "138001380001"]})
        violations = validator.validate(df, "phone")
        assert len(violations) == 3

    def test_mixed_phones(self):
        """测试混合手机号."""
        from dqengine.plugins.custom_phone_validator import CustomPhoneValidator

        validator = CustomPhoneValidator()
        df = pd.DataFrame({"phone": ["13800138000", "invalid", "13912345678"]})
        violations = validator.validate(df, "phone")
        assert len(violations) == 1

    def test_missing_column(self):
        """测试不存在的列."""
        from dqengine.plugins.custom_phone_validator import CustomPhoneValidator

        validator = CustomPhoneValidator()
        df = pd.DataFrame({"other": ["data"]})
        violations = validator.validate(df, "phone")
        assert len(violations) == 1
        assert "不存在" in violations[0].message
