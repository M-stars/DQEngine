"""插件基类定义 - 定义 Validator / Cleaner / Scorer / Connector / Backend 插件接口."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, ClassVar, Dict, List, Optional, Sequence

import pandas as pd

from dqengine.models.schemas import PluginInfo, PluginType, RepairResult, RuleViolation


class BasePlugin(ABC):
    """所有插件的抽象基类.

    子类必须定义 PLUGIN_INFO 类属性.

    性能约定:
        处理 DataFrame 的 validate/clean 实现应遵循"向量化为默认、
        循环仅限违规行"——用布尔掩码 (series.notna() / 比较 / isin /
        str.contains) 做全列扫描, 只对命中的少量行构造结果对象;
        逐行 for + pd.isna(val) 的标量分派约 1µs/次, 百万行数据
        会放大为秒级开销 (核心库已按此约定改造, 见
        rules/validator.py 与 repair/outlier.py).

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


class BaseConnector(BasePlugin):
    """数据源连接器插件基类 - 通过 URI scheme 接入外部数据源.

    子类必须定义 SCHEMES 类属性, 声明可处理的 URI scheme 列表;
    DataLoader 遇到形如 ``scheme://...`` 的输入时按 scheme 路由到
    第一个匹配的连接器插件.

    依赖约定:
        连接器所需第三方依赖 (sqlalchemy 驱动等) 一律在方法内懒加载,
        并抛出带安装提示的 ImportError; 插件文件本身不得在模块顶层
        import 可选依赖, 否则未安装依赖的注册表扫描会直接失败.

    示例:
        class MyConnector(BaseConnector):
            PLUGIN_INFO = PluginInfo(
                name="my_connector",
                plugin_type=PluginType.LOADER,
                description="自定义数据源连接器",
            )
            SCHEMES = ("myproto",)

            def load(self, uri, table=None, query=None, **kwargs):
                ...
    """

    PLUGIN_INFO = PluginInfo(
        name="base_connector",
        plugin_type=PluginType.LOADER,
        description="连接器基类",
    )

    SCHEMES: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def load(
        self,
        uri: str,
        table: Optional[str] = None,
        query: Optional[str] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """从数据源加载数据.

        Args:
            uri: 数据源连接串 (密码不应出现在日志中).
            table: 表名 (table 与 query 二选一, 都缺省时的行为由连接器决定).
            query: SQL 查询语句 (优先于 table).
            **kwargs: 传递给底层读取函数的额外参数.

        Returns:
            DataFrame.
        """
        ...


class BaseBackend(BasePlugin):
    """分布式执行后端插件基类 - 将独立任务扇出到并行/分布式执行.

    后端只负责"执行", 不理解任务语义; 核心库把可序列化的函数与
    参数交给后端, 后端保证结果按输入顺序返回. 两个典型场景:

        - batch: 任务 = 每个文件的处理函数
        - validate 分区分片: 任务 = 每个分区的验证函数

    示例:
        class MyBackend(BaseBackend):
            PLUGIN_INFO = PluginInfo(
                name="my_backend",
                plugin_type=PluginType.BACKEND,
                description="自定义分布式后端",
            )
            NAME = "my_backend"
    """

    PLUGIN_INFO = PluginInfo(
        name="base_backend",
        plugin_type=PluginType.BACKEND,
        description="执行后端基类",
    )

    NAME: ClassVar[str] = ""

    @abstractmethod
    def map(self, fn: Callable, items: Sequence[Any]) -> List[Any]:
        """对一组独立任务执行 fn, 返回按输入顺序排列的结果.

        Args:
            fn: 任务函数 (必须可被后端序列化, 推荐模块级函数).
            items: 任务参数列表, 每项作为 fn 的唯一位置参数.

        Returns:
            与 items 等长的结果列表. 单个任务失败时应抛出异常或
            返回错误标记对象, 由调用方决定如何呈现.
        """
        ...

    @abstractmethod
    def map_partitions(
        self,
        source: "str | Any",
        npartitions: int,
        fn: Callable,
        merge: Callable,
        **kwargs,
    ) -> Any:
        """将数据源切分为分区, 对每个分区执行 fn 后用 merge 合并.

        Args:
            source: 数据源 (文件路径或已加载对象), 支持的分片方式
                由后端决定.
            npartitions: 期望分区数.
            fn: 分区处理函数, 签名 ``fn(df_partition, row_offset)``,
                row_offset 为该分区在原数据中的起始行号 (供全局行号
                对齐).
            merge: 合并函数, 接收各分区结果列表.
            **kwargs: 传递给分区读取的额外参数.

        Returns:
            merge 的返回值.
        """
        ...
