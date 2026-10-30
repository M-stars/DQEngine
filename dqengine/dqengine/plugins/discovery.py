"""插件发现助手 - 内置插件与用户插件的统一发现/路由入口.

DataLoader (URI 路由) 与 BatchProcessor (分布式后端) 通过本模块
按需发现连接器/后端插件; 未安装对应可选依赖时内置插件加载失败
会被注册表静默跳过, 核心功能不受影响.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from dqengine.models.schemas import PluginInfo, PluginType
from dqengine.plugins.base import BaseBackend, BaseConnector
from dqengine.registry.plugin_registry import PluginRegistry, get_plugin_registry
from dqengine.utils.logger import get_logger

logger = get_logger(__name__)

# 包内置插件目录 (sql_connector / dask_backend 等随包发布)
BUILTIN_PLUGINS_DIR = Path(__file__).resolve().parent / "builtin"

_lock = threading.Lock()
_ensured = False
_connector_cache: dict = {}
_backend_cache: dict = {}


def ensure_plugins_discovered() -> PluginRegistry:
    """确保内置插件与当前工作目录下用户插件已加载 (进程内仅一次).

    用户插件目录为当前工作目录下的 plugins/ (与 `dq plugins` 的
    默认扫描路径一致), 放入 .py 文件即可被路由发现.

    Returns:
        已完成发现的 PluginRegistry 全局单例.
    """
    global _ensured
    if _ensured:
        return get_plugin_registry()

    with _lock:
        if _ensured:
            return get_plugin_registry()
        registry = get_plugin_registry()
        try:
            registry.discover(BUILTIN_PLUGINS_DIR)
        except Exception as e:
            logger.error("内置插件扫描失败: %s", e)
        user_dir = Path("plugins")
        if user_dir.exists():
            try:
                registry.discover(user_dir)
            except Exception as e:
                logger.error("用户插件目录扫描失败 (%s): %s", user_dir, e)
        _ensured = True
        return registry


def reset_discovery() -> None:
    """重置发现状态, 下次 ensure 时重新扫描 (供动态加载插件的场景)."""
    global _ensured
    with _lock:
        _ensured = False
        _connector_cache.clear()
        _backend_cache.clear()


def _find_plugin_class(module_or_cls: object, base: type) -> Optional[type]:
    """从注册表存储的模块/类中定位指定基类的插件子类.

    文件加载的插件在注册表中存的是模块, 需在模块内找到定义于该
    模块 (排除从基类模块 import 进来的符号) 的基类子类.
    """
    if isinstance(module_or_cls, type):
        return module_or_cls if issubclass(module_or_cls, base) else None
    module_name = getattr(module_or_cls, "__name__", "")
    for attr in vars(module_or_cls).values():
        if (
            isinstance(attr, type)
            and attr is not base
            and issubclass(attr, base)
            and attr.__module__ == module_name
        ):
            return attr
    return None


def find_connector(uri: str) -> Optional[BaseConnector]:
    """按 URI scheme 查找并实例化连接器插件.

    Args:
        uri: 形如 ``scheme://...`` 的数据源连接串.

    Returns:
        匹配的 BaseConnector 实例; 无匹配返回 None.
    """
    registry = ensure_plugins_discovered()
    if "://" not in uri:
        return None
    scheme = uri.split("://", 1)[0].strip().lower()
    if not scheme:
        return None

    if scheme in _connector_cache:
        return _connector_cache[scheme]

    for info in registry.get_by_type(PluginType.LOADER):
        cls = _find_plugin_class(registry.get_instance(info.name), BaseConnector)
        if cls is None or scheme not in tuple(getattr(cls, "SCHEMES", ())):
            continue
        try:
            connector = cls()
        except Exception as e:
            logger.error("实例化连接器插件 %s 失败: %s", info.name, e)
            continue
        _connector_cache[scheme] = connector
        return connector
    return None


def find_backend(name: str) -> Optional[BaseBackend]:
    """按名称查找并实例化执行后端插件.

    Args:
        name: 后端名称 (如 ``dask``).

    Returns:
        匹配的 BaseBackend 实例; 无匹配返回 None.
    """
    registry = ensure_plugins_discovered()
    name = name.strip().lower()

    if name in _backend_cache:
        return _backend_cache[name]

    for info in registry.get_by_type(PluginType.BACKEND):
        cls = _find_plugin_class(registry.get_instance(info.name), BaseBackend)
        if cls is None or getattr(cls, "NAME", "") != name:
            continue
        try:
            backend = cls()
        except Exception as e:
            logger.error("实例化后端插件 %s 失败: %s", info.name, e)
            continue
        _backend_cache[name] = backend
        return backend
    return None


def list_available_backends() -> list:
    """列出当前可实例化的后端名称 (供 CLI 提示)."""
    registry = ensure_plugins_discovered()
    names = []
    for info in registry.get_by_type(PluginType.BACKEND):
        cls = _find_plugin_class(registry.get_instance(info.name), BaseBackend)
        if cls is not None and getattr(cls, "NAME", ""):
            names.append(cls.NAME)
    return sorted(names)


__all__ = [
    "BUILTIN_PLUGINS_DIR",
    "ensure_plugins_discovered",
    "reset_discovery",
    "find_connector",
    "find_backend",
    "list_available_backends",
    "PluginInfo",
]
