"""缓存层 - Memory / Redis (接口预留)."""

from __future__ import annotations

import time
from threading import Lock
from typing import Any, Dict

from dqengine.models.schemas import CacheProvider


class CacheManager:
    """统一缓存管理器.

    支持:
    - Memory: 进程内内存缓存
    - Redis: 分布式缓存 (接口预留)

    Usage:
        cache = CacheManager(CacheProvider.MEMORY)
        cache.set("key", value, ttl=300)
        value = cache.get("key")
    """

    def __init__(self, provider: CacheProvider = CacheProvider.MEMORY, **kwargs: Any) -> None:
        self.provider = provider
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()

    def get(self, key: str, default: Any = None) -> Any:
        """获取缓存值."""
        if self.provider == CacheProvider.MEMORY:
            with self._lock:
                entry = self._store.get(key)
                if entry is None:
                    return default
                if entry["expires_at"] > 0 and time.time() > entry["expires_at"]:
                    del self._store[key]
                    return default
                return entry["value"]
        elif self.provider == CacheProvider.REDIS:
            raise NotImplementedError("Redis 缓存尚未实现。请安装 redis 库。")
        return default

    def _purge_expired(self) -> None:
        """清理已过期条目 (须持锁调用).

        只在读取时淘汰会让写多读少的 TTL 键永不回收.
        """
        now = time.time()
        expired = [
            k
            for k, entry in self._store.items()
            if entry["expires_at"] > 0 and now > entry["expires_at"]
        ]
        for k in expired:
            del self._store[k]

    def set(self, key: str, value: Any, ttl: int = 0) -> None:
        """设置缓存值.

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间 (秒), 0 = 永不过期
        """
        if self.provider == CacheProvider.MEMORY:
            with self._lock:
                self._purge_expired()
                self._store[key] = {
                    "value": value,
                    "expires_at": time.time() + ttl if ttl > 0 else 0,
                }
        elif self.provider == CacheProvider.REDIS:
            raise NotImplementedError("Redis 缓存尚未实现。请安装 redis 库。")

    def delete(self, key: str) -> bool:
        """删除缓存."""
        if self.provider == CacheProvider.MEMORY:
            with self._lock:
                if key in self._store:
                    del self._store[key]
                    return True
                return False
        return False

    def exists(self, key: str) -> bool:
        """检查缓存是否存在."""
        return self.get(key) is not None

    def clear(self) -> None:
        """清空所有缓存."""
        if self.provider == CacheProvider.MEMORY:
            with self._lock:
                self._store.clear()

    def get_or_set(self, key: str, factory: callable, ttl: int = 300) -> Any:
        """获取缓存，不存在时通过 factory 生成."""
        value = self.get(key)
        if value is not None:
            return value
        value = factory()
        self.set(key, value, ttl)
        return value

    @property
    def size(self) -> int:
        """缓存条目数."""
        if self.provider == CacheProvider.MEMORY:
            self._purge_expired()
        return len(self._store)
        return 0
