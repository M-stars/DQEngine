"""服务容器 — 轻量级依赖注入."""

from __future__ import annotations

from typing import Any, Callable, Dict, Type, TypeVar

T = TypeVar("T")


class ServiceContainer:
    """轻量级服务容器 (DI Container).

    支持:
    - 单例注册 (singleton)
    - 工厂注册 (factory)
    - 延迟初始化 (lazy)

    Usage:
        container = ServiceContainer()
        container.register_singleton(DataLoader, DataLoader())
        loader = container.resolve(DataLoader)
    """

    def __init__(self) -> None:
        self._singletons: Dict[Type, Any] = {}
        self._factories: Dict[Type, Callable[[], Any]] = {}
        self._aliases: Dict[str, Type] = {}

    def register_singleton(self, service_type: Type[T], instance: T) -> None:
        """注册单例服务."""
        self._singletons[service_type] = instance

    def register_factory(self, service_type: Type[T], factory: Callable[[], T]) -> None:
        """注册工厂函数."""
        self._factories[service_type] = factory

    def register_alias(self, alias: str, service_type: Type) -> None:
        """注册类型别名."""
        self._aliases[alias] = service_type

    def resolve(self, service_type: Type[T]) -> T:
        """解析服务实例."""
        # 先查单例
        if service_type in self._singletons:
            return self._singletons[service_type]
        # 再查工厂
        if service_type in self._factories:
            instance = self._factories[service_type]()
            self._singletons[service_type] = instance
            return instance
        raise KeyError(f"服务未注册: {service_type.__name__}")

    def resolve_by_name(self, alias: str) -> Any:
        """通过别名解析服务."""
        if alias in self._aliases:
            return self.resolve(self._aliases[alias])
        raise KeyError(f"别名未注册: {alias}")

    def has(self, service_type: Type) -> bool:
        """检查服务是否已注册."""
        return service_type in self._singletons or service_type in self._factories


# 全局容器单例
_GLOBAL_CONTAINER = ServiceContainer()


def get_container() -> ServiceContainer:
    """获取全局服务容器."""
    return _GLOBAL_CONTAINER
