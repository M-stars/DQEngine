"""配置系统测试."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from dqengine.services.config_manager import ConfigManager
from dqengine.models.schemas import AppConfig, CleaningConfig, ReportConfig


class TestConfigManager:
    """ConfigManager 单元测试."""

    @pytest.fixture
    def cm(self):
        return ConfigManager()

    @pytest.fixture
    def sample_config_dict(self):
        return {
            "cleaning": {
                "missing": {"strategy": "median", "enabled": True},
                "duplicate": {"enabled": False},
                "outlier": {"method": "zscore", "threshold": 3.0},
                "date": {"target_format": "%Y/%m/%d"},
            },
            "report": {
                "formats": ["html", "json"],
                "output_dir": "my_reports",
            },
            "log_level": "DEBUG",
        }

    def test_load_config(self, cm, sample_config_dict):
        """测试加载配置文件."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(sample_config_dict, f)
            config_path = f.name

        try:
            config = cm.load(config_path)
            assert isinstance(config, AppConfig)
            assert config.cleaning.missing.strategy == "median"
            assert config.cleaning.duplicate.enabled is False
            assert config.cleaning.outlier.method == "zscore"
            assert config.report.formats == ["html", "json"]
            assert config.log_level == "DEBUG"
        finally:
            os.unlink(config_path)

    def test_default_config(self, cm):
        """测试默认配置."""
        config = cm.DEFAULT_CONFIG
        assert config.cleaning.missing.strategy == "mean"
        assert config.cleaning.duplicate.enabled is True
        assert config.cleaning.outlier.method == "iqr"

    def test_export_config(self, cm):
        """测试配置导出."""
        config = AppConfig()
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            config_path = f.name

        try:
            exported = cm.export(config, config_path)
            assert Path(config_path).exists()

            loaded = cm.load(config_path)
            assert loaded.cleaning.missing.strategy == "mean"
        finally:
            os.unlink(config_path)

    def test_partial_config(self, cm):
        """测试部分配置合并."""
        partial = {"cleaning": {"missing": {"strategy": "mode"}}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(partial, f)
            config_path = f.name

        try:
            config = cm.load(config_path)
            # 自定义值
            assert config.cleaning.missing.strategy == "mode"
            # 默认值保持不变
            assert config.cleaning.duplicate.enabled is True
            assert config.cleaning.outlier.method == "iqr"
        finally:
            os.unlink(config_path)

    def test_get_cleaning_config(self, cm):
        """测试获取清洗配置."""
        config = AppConfig()
        cleaning = cm.get_cleaning_config(config)
        assert isinstance(cleaning, CleaningConfig)
        assert cleaning.missing.strategy == "mean"

    def test_get_report_config(self, cm):
        """测试获取报告配置."""
        config = AppConfig()
        report = cm.get_report_config(config)
        assert isinstance(report, ReportConfig)
        assert "html" in report.formats

    def test_file_not_found(self, cm):
        """测试配置文件不存在."""
        with pytest.raises(FileNotFoundError):
            cm.load("nonexistent.yaml")
