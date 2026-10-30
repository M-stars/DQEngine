"""内置插件: Dask 分布式执行后端.

依赖可选: 未安装 dask 时本模块 import 即失败,
PluginRegistry 会跳过该插件, 本地线程池执行不受影响.

调度策略:
    - 配置 ``scheduler`` (如 tcp://host:8786) 时连接外部集群
    - 否则使用本地进程集群 (绕开 GIL, 适合 CPU 密集的清洗/验证)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence

import pandas as pd

from dqengine.models.schemas import PluginInfo, PluginType
from dqengine.plugins.base import BaseBackend
from dqengine.utils.logger import get_logger

logger = get_logger(__name__)


class DaskBackend(BaseBackend):
    """Dask 分布式后端 — 文件扇出与 DataFrame 分区分片.

    config 键:
        scheduler: 集群调度器地址 (缺省用本地进程集群)
        n_workers: 本地集群 worker 数 (缺省 min(CPU, 4))
    """

    PLUGIN_INFO = PluginInfo(
        name="dask_backend",
        plugin_type=PluginType.BACKEND,
        version="0.1.0",
        description="Dask 分布式执行后端 (本地集群或外部调度器), 依赖 dask",
        dependencies=["dask", "distributed"],
    )

    NAME = "dask"

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        self._client = None

    # ------------------------------------------------------------------
    # 任务扇出
    # ------------------------------------------------------------------

    def _get_client(self):
        """获取或创建 distributed Client (懒加载, 实例级复用)."""
        try:
            from distributed import Client, LocalCluster
        except ImportError:
            raise ImportError(
                '分布式后端需要 dask + distributed: pip install "dqengine[dask]"'
            )

        if self._client is not None:
            return self._client

        # 调度器优先级: 插件 config > 环境变量 (供 CLI 免配置直连集群)
        import os

        scheduler = self.config.get("scheduler") or os.environ.get(
            "DQENGINE_DASK_SCHEDULER"
        )
        if scheduler:
            logger.info("连接 Dask 集群: %s", scheduler)
            self._client = Client(scheduler)
        else:
            import os

            n_workers = int(self.config.get("n_workers", min(os.cpu_count() or 2, 4)))
            logger.info("启动本地 Dask 集群 (workers=%d)", n_workers)
            cluster = LocalCluster(
                n_workers=n_workers, threads_per_worker=1, processes=True
            )
            self._client = Client(cluster)
        return self._client

    def map(self, fn: Callable, items: Sequence[Any]) -> List[Any]:
        """任务扇出到集群/本地进程, 结果按输入顺序返回."""
        items = list(items)
        if not items:
            return []
        client = self._get_client()
        futures = client.map(fn, items)
        return client.gather(futures)

    # ------------------------------------------------------------------
    # DataFrame 分区分片
    # ------------------------------------------------------------------

    def _to_dask(self, source: Any, npartitions: int, **kwargs):
        """把数据源转成 dask DataFrame.

        支持已加载的 pandas DataFrame、dask DataFrame 以及
        .csv / .parquet 文件路径 (文件路径模式可获得超内存分片能力).
        """
        import dask.dataframe as dd

        if hasattr(source, "partitions"):  # 已是 dask 集合
            return source
        if isinstance(source, pd.DataFrame):
            return dd.from_pandas(source, npartitions=max(1, npartitions or 2))

        path = Path(str(source))
        suffix = path.suffix.lower()
        if suffix == ".parquet":
            return dd.read_parquet(path, **kwargs)
        if suffix == ".csv":
            blocksize = None
            if npartitions and npartitions > 0 and path.exists():
                # 按期望分区数反推块大小, 下限 1MB
                blocksize = max(1, path.stat().st_size // npartitions // 1024) * 1024
                blocksize = max(blocksize, 1024 * 1024)
            return dd.read_csv(path, blocksize=blocksize, **kwargs)
        raise ValueError(
            f"分布式分片不支持格式: {suffix} (支持 .csv / .parquet 或传入 DataFrame); "
            "其他格式请先本地加载后再用 DataFrame 模式"
        )

    def map_partitions(
        self,
        source: Any,
        npartitions: int,
        fn: Callable,
        merge: Callable,
        **kwargs,
    ) -> Any:
        """分区并行执行 fn(partition, row_offset), 结果交给 merge 合并.

        分区以 dask.delayed 任务形式调度: fn 返回任意对象 (如违规
        列表) 均可, 不受 DataFrame meta 推断限制. 分布式调度时各
        分区在 worker 进程上执行, 主进程只承担合并开销.
        """
        import dask

        ddf = self._to_dask(source, npartitions, **kwargs)
        parts = ddf.to_delayed()
        n_parts = len(parts)
        logger.info("分区分片: %d 个分区 (期望 %d)", n_parts, npartitions or n_parts)

        # 各分区起始行号: 全局行号对齐由任务侧完成
        sizes = dask.compute(*[dask.delayed(len)(p) for p in parts])
        offsets = []
        acc = 0
        for size in sizes:
            offsets.append(acc)
            acc += size

        tasks = [
            dask.delayed(fn)(p, row_offset=off) for p, off in zip(parts, offsets)
        ]
        results = dask.compute(*tasks)
        return merge(list(results))
