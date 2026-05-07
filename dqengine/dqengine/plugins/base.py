"""插件基类定义 - 定义 Validator / Cleaner / Scorer 插件接口."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import pandas as pd

from dqengine.models.schemas import PluginInfo, PluginType, RepairResult, RuleViolation


class BasePlugin(ABC):
    """所有插件的抽象基类.

    子类必须定义 PLUGIN_INFO 类属性.

    示例:
        class MyValidator(BaseValidator):
            PLUGIN_INFO = PluginInfo(
                name="my_validator",
                plugin_type=PluginType.VALIDATOR,
                description="自定义验证器",
            )
    """

    PLUGIN_INFO: PluginInfo

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """初始化插件.

        Args:
            config: 可选的插件配置参数.
        """
        self.config = config or {}
        self._enabled = True

    @property
    def enabled(self) -> bool:
        """插件是否启用."""
        return self._enabled

    def enable(self) -> None:
        """启用插件."""
        self._enabled = True

    def disable(self) -> None:
        """禁用插件."""
        self._enabled = False

    @property
    def name(self) -> str:
        """插件名称."""
        return self.PLUGIN_INFO.name

    @property
    def plugin_type(self) -> PluginType:
        """插件类型."""
        return self.PLUGIN_INFO.plugin_type

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name!r}, type={self.plugin_type.value})>"


class BaseValidator(BasePlugin):
    """验证器插件基类 - 用于自定义数据验证逻辑."""

    PLUGIN_INFO = PluginInfo(
        name="base_validator",
        plugin_type=PluginType.VALIDATOR,
        description="验证器基类",
    )

    @abstractmethod
    def validate(self, df: pd.DataFrame, column: str) -> List[RuleViolation]:
        """执行验证.

        Args:
            df: 输入 DataFrame.
            column: 待验证的字段名.

        Returns:
            RuleViolation 列表.
        """
        ...


class BaseCleaner(BasePlugin):
    """清洗器插件基类 - 用于自定义数据清洗逻辑."""

    PLUGIN_INFO = PluginInfo(
        name="base_cleaner",
        plugin_type=PluginType.CLEANER,
        description="清洗器基类",
    )

    @abstractmethod
    def clean(self, df: pd.DataFrame, column: Optional[str] = None) -> tuple[pd.DataFrame, RepairResult]:
        """执行清洗.

        Args:
            df: 输入 DataFrame.
            column: 待清洗的字段名 (None 表示全部).

        Returns:
            (清洗后的 DataFrame, RepairResult) 元组.
        """
        ...


class BaseScorer(BasePlugin):
    """评分器插件基类 - 用于自定义质量评分维度."""

    PLUGIN_INFO = PluginInfo(
        name="base_scorer",
        plugin_type=PluginType.SCORER,
        description="评分器基类",
    )

    @abstractmethod
    def score(self, df: pd.DataFrame, profile: Any) -> Dict[str, Any]:
        """计算质量评分维度.

        Args:
            df: 输入 DataFrame.
            profile: ProfileResult 实例.

        Returns:
            包含 name, score, weight, description 的字典.
        """
        ...
