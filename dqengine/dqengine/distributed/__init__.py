"""分布式执行支持 - 任务函数与合并逻辑 (执行由后端插件承担)."""

from dqengine.distributed.parallel import (
    batch_task_adapter,
    merge_validation_results,
    process_file_task,
    validate_partition,
)

__all__ = [
    "batch_task_adapter",
    "merge_validation_results",
    "process_file_task",
    "validate_partition",
]
