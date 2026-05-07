"""插件注册中心 - 管理插件的发现、加载、启停."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from dqengine.models.schemas import PluginInfo, PluginType
from dqengine.utils.logger import get_logger

logger = get_logger(__name__)


class PluginRegistry:
    """插件注册中心.

    特性:
        - 自动发现 plugins/ 目录下的所有 .py 文件
        - 支持热插拔 (加载/卸载)
        - 插件类型校验
        - 版本管理

    使用方式:
        registry = get_plugin_registry()
        registry.discover("plugins/")
        plugins = registry.list_plugins()
    """

    def __init__(self) -> None:
        self._plugins: Dict[str, PluginInfo] = {}  # name -> info
        self._instances: Dict[str, Any] = {}        # name -> instance

    def discover(self, plugins_dir: "str | Path" = "plugins") -> List[PluginInfo]:
        """自动发现并加载插件目录中的所有插件.

        Args:
            plugins_dir: 插件目录路径.

        Returns:
            新发现的插件信息列表.
        """
        dir_path = Path(plugins_dir)
        if not dir_path.exists():
            logger.warning("插件目录不存在: %s", dir_path)
            return []

        discovered: List[PluginInfo] = []

        for py_file in sorted(dir_path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue

            try:
                plugin_info = self._load_plugin_from_file(py_file)
                if plugin_info:
                    self._plugins[plugin_info.name] = plugin_info
                    discovered.append(plugin_info)
                    logger.info("插件已加载: %s (类型: %s)", plugin_info.name, plugin_info.plugin_type.value)
            except Exception as e:
                logger.error("加载插件失败 %s: %s", py_file.name, str(e))

        return discovered

    def _load_plugin_from_file(self, file_path: Path) -> Optional[PluginInfo]:
        """从文件加载单个插件.

        Args:
            file_path: 插件 .py 文件路径.

        Returns:
            PluginInfo 或 None.
        """
        module_name = f"dqengine_plugin_{file_path.stem}"

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            logger.warning("无法解析插件文件: %s", file_path)
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # 查找插件信息
        plugin_info = getattr(module, "PLUGIN_INFO", None)
        if plugin_info is None or not isinstance(plugin_info, PluginInfo):
            # 尝试从类中推断
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and hasattr(attr, "PLUGIN_INFO"):
                    plugin_info = getattr(attr, "PLUGIN_INFO")
                    break
            else:
                logger.warning("插件 %s 未定义 PLUGIN_INFO", file_path.name)
                return None

        # 存储模块引用以便后续实例化
        plugin_info.file_path = str(file_path)
        self._instances[plugin_info.name] = module

        return plugin_info

    def register(self, plugin_cls: Type) -> PluginInfo:
        """手动注册一个插件类.

        Args:
            plugin_cls: 插件类 (必须定义 PLUGIN_INFO).

        Returns:
            PluginInfo 实例.
        """
        if not hasattr(plugin_cls, "PLUGIN_INFO"):
            raise ValueError(f"插件类 {plugin_cls.__name__} 缺少 PLUGIN_INFO 属性")

        info = plugin_cls.PLUGIN_INFO
        self._plugins[info.name] = info
        self._instances[info.name] = plugin_cls
        logger.info("插件手动注册: %s", info.name)
        return info

    def unregister(self, name: str) -> bool:
        """卸载插件.

        Args:
            name: 插件名称.

        Returns:
            是否成功卸载.
        """
        if name in self._plugins:
            del self._plugins[name]
            self._instances.pop(name, None)
            logger.info("插件已卸载: %s", name)
            return True
        return False

    def get(self, name: str) -> Optional[PluginInfo]:
        """获取指定插件信息.

        Args:
            name: 插件名称.

        Returns:
            PluginInfo 或 None.
        """
        return self._plugins.get(name)

    def get_instance(self, name: str) -> Any:
        """获取插件模块/类实例.

        Args:
            name: 插件名称.

        Returns:
            插件模块或类.
        """
        return self._instances.get(name)

    def list_plugins(self, plugin_type: Optional[PluginType] = None) -> List[PluginInfo]:
        """列出所有已加载的插件.

        Args:
            plugin_type: 按类型过滤.

        Returns:
            插件信息列表.
        """
        if plugin_type:
            return [p for p in self._plugins.values() if p.plugin_type == plugin_type]
        return list(self._plugins.values())

    def get_by_type(self, plugin_type: PluginType) -> List[PluginInfo]:
        """按类型获取插件列表.

        Args:
            plugin_type: 插件类型.

        Returns:
            插件信息列表.
        """
        return self.list_plugins(plugin_type)

    def is_loaded(self, name: str) -> bool:
        """检查插件是否已加载.

        Args:
            name: 插件名称.

        Returns:
            是否已加载.
        """
        return name in self._plugins


# 全局单例
_plugin_registry: Optional[PluginRegistry] = None


def get_plugin_registry() -> PluginRegistry:
    """获取全局 PluginRegistry 单例."""
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry()
    return _plugin_registry
