"""统一日志系统 - 支持Rich控制台 + 文件日志 + 错误日志."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


class LoggerManager:
    """DQEngine 统一日志管理器.

    特性:
        - Rich 控制台彩色输出
        - 文件日志自动轮转 (10MB x 3)
        - 错误日志独立记录
        - 模块级 logger 隔离
    """

    _instance: Optional[LoggerManager] = None
    _initialized: bool = False

    LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    def __new__(cls) -> LoggerManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if LoggerManager._initialized:
            return
        LoggerManager._initialized = True

        self._log_dir = Path("logs")
        self._log_dir.mkdir(parents=True, exist_ok=True)

        self._setup_root_logger()

    def _setup_root_logger(self) -> None:
        """配置根日志器."""
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        # 控制台处理器 - INFO级别
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter("%(message)s")
        console_handler.setFormatter(console_format)
        root.addHandler(console_handler)

        # 文件日志处理器 - DEBUG级别, 自动轮转
        file_handler = RotatingFileHandler(
            self._log_dir / "dqengine.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(self.LOG_FORMAT, datefmt=self.DATE_FORMAT)
        file_handler.setFormatter(file_format)
        root.addHandler(file_handler)

        # 错误日志处理器 - ERROR级别, 独立文件
        error_handler = RotatingFileHandler(
            self._log_dir / "error.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_format)
        root.addHandler(error_handler)

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """获取模块级 logger.

        Args:
            name: 通常传入 __name__ 即可.

        Returns:
            配置好的 logger 实例.
        """
        LoggerManager()
        return logging.getLogger(name)

    @staticmethod
    def set_level(level: str) -> None:
        """动态调整控制台日志级别.

        Args:
            level: DEBUG, INFO, WARNING, ERROR, CRITICAL.
        """
        for handler in logging.getLogger().handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(
                handler, RotatingFileHandler
            ):
                handler.setLevel(getattr(logging, level.upper(), logging.INFO))


def setup_logging(level: str = "INFO") -> None:
    """初始化日志系统 (便于外部调用).

    Args:
        level: 日志级别.
    """
    LoggerManager()
    LoggerManager.set_level(level)


def get_logger(name: str) -> logging.Logger:
    """便捷获取 logger 的方法.

    Args:
        name: 模块名, 建议传入 __name__.

    Returns:
        logging.Logger 实例.
    """
    return LoggerManager.get_logger(name)
