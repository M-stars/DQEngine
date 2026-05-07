"""配置管理器 - 基于 Pydantic + YAML 的配置驱动治理."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from dqengine.models.schemas import AppConfig, CleaningConfig, ReportConfig
from dqengine.utils.logger import get_logger

logger = get_logger(__name__)


class ConfigManager:
    """配置管理器.

    支持:
        - 从 YAML 文件加载配置
        - Pydantic 模型验证
        - 配置合并 (默认值 + 用户配置)
        - 配置导出

    使用方式:
        cm = ConfigManager()
        config = cm.load("configs/default.yaml")
    """

    # 默认配置
    DEFAULT_CONFIG = AppConfig()

    def load(self, config_path: "str | Path") -> AppConfig:
        """从 YAML 文件加载配置.

        Args:
            config_path: YAML 配置文件路径.

        Returns:
            验证后的 AppConfig 实例.

        Raises:
            FileNotFoundError: 配置文件不存在.
            ValueError: 配置格式不正确.
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件未找到: {path}")

        logger.info("加载配置: %s", path.name)

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        return self._parse(raw)

    def _parse(self, raw: dict) -> AppConfig:
        """将 YAML 字典解析为 AppConfig.

        Args:
            raw: 原始配置字典.

        Returns:
            AppConfig 实例.
        """
        config_dict = self.DEFAULT_CONFIG.model_dump()

        # 深度合并清洗配置
        if "cleaning" in raw:
            clean_raw = raw["cleaning"]
            if "missing" in clean_raw:
                config_dict["cleaning"]["missing"].update(clean_raw["missing"])
            if "duplicate" in clean_raw:
                config_dict["cleaning"]["duplicate"].update(clean_raw["duplicate"])
            if "outlier" in clean_raw:
                config_dict["cleaning"]["outlier"].update(clean_raw["outlier"])
            if "date" in clean_raw:
                config_dict["cleaning"]["date"].update(clean_raw["date"])

        # 深度合并报告配置
        if "report" in raw:
            report_raw = raw["report"]
            if "formats" in report_raw:
                config_dict["report"]["formats"] = report_raw["formats"]
            if "output_dir" in report_raw:
                config_dict["report"]["output_dir"] = report_raw["output_dir"]
            if "include_charts" in report_raw:
                config_dict["report"]["include_charts"] = report_raw["include_charts"]
            if "include_outliers" in report_raw:
                config_dict["report"]["include_outliers"] = report_raw["include_outliers"]

        # 顶层配置
        for key in ("semantic_enabled", "plugins_dir", "log_level", "log_file"):
            if key in raw:
                config_dict[key] = raw[key]

        return AppConfig(**config_dict)

    def export(self, config: AppConfig, output_path: "str | Path") -> Path:
        """将配置导出为 YAML 文件.

        Args:
            config: AppConfig 实例.
            output_path: 输出路径.

        Returns:
            导出的文件路径.
        """
        import json
        path = Path(output_path)
        # 使用 model_dump 获取可序列化字典, 再转为 YAML
        data = json.loads(config.model_dump_json())

        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        logger.info("配置已导出: %s", path)
        return path

    def get_cleaning_config(self, config: AppConfig) -> CleaningConfig:
        """提取清洗配置.

        Args:
            config: AppConfig 实例.

        Returns:
            CleaningConfig.
        """
        return config.cleaning

    def get_report_config(self, config: AppConfig) -> ReportConfig:
        """提取报告配置.

        Args:
            config: AppConfig 实例.

        Returns:
            ReportConfig.
        """
        return config.report
