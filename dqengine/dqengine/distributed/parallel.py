"""分布式任务函数 - 供后端插件扇出的可序列化任务与合并逻辑.

约定:
    - 任务函数必须是模块级函数 (按引用序列化), 参数只含可序列化对象
    - 分布式 worker 端需要能 import dqengine
    - 合并语义必须与单机执行等价 (有对拍测试保证, 见 tests/test_distributed.py)
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

import pandas as pd

from dqengine.models.schemas import ValidationResult
from dqengine.utils.logger import get_logger

logger = get_logger(__name__)


def validate_partition(
    df: pd.DataFrame, row_offset: int = 0, rules: Sequence = ()
) -> ValidationResult:
    """验证单个分区, 违规行号按分区偏移校正为全局行号.

    后端以 ``fn(partition, row_offset=...)`` 形式调用; rules 通过
    functools.partial 固定注入.

    Args:
        df: 分区 DataFrame.
        row_offset: 分区在原数据中的起始行号.
        rules: ValidationRule 列表 (pydantic 模型, 可序列化).

    Returns:
        该分区的 ValidationResult (行号已全局化).
    """
    from dqengine.rules.validator import RuleValidator

    result = RuleValidator().validate(df, list(rules))
    if row_offset and result.violations:
        violations = [
            v.model_copy(update={"row_index": v.row_index + row_offset})
            if v.row_index >= 0
            else v
            for v in result.violations
        ]
        result = result.model_copy(update={"violations": violations})
    return result


def merge_validation_results(
    results: List[ValidationResult], total_rules: int
) -> ValidationResult:
    """合并各分区验证结果, 语义与单机整表验证一致.

    行级违规直接拼接; 列级违规 (row_index<0, 如列不存在/阈值非法)
    按去重保留 —— 单机下每条规则只产生一条, 分区执行会产生 N 条.
    """
    all_violations = []
    seen_column_level = set()
    for r in results:
        for v in r.violations:
            if v.row_index < 0:
                key = (v.column, v.rule_type, v.message)
                if key in seen_column_level:
                    continue
                seen_column_level.add(key)
            all_violations.append(v)

    failed_rules = len(set(v.column + v.rule_type for v in all_violations))
    return ValidationResult(
        passed=len(all_violations) == 0,
        total_rules=total_rules,
        passed_rules=total_rules - failed_rules,
        failed_rules=failed_rules,
        total_violations=len(all_violations),
        violations=all_violations,
    )


def process_file_task(
    file_path: str, out_dir: str, clean_name: str, config
):
    """批处理单文件任务 (worker 端自行构建处理器, 错误隔离).

    Args:
        file_path: 源文件路径.
        out_dir: 输出目录.
        clean_name: 输出文件名.
        config: AppConfig (可序列化).

    Returns:
        BatchFileResult.
    """
    from dqengine.batch.processor import BatchProcessor

    # worker 端输出目录自建: 不依赖主进程预创建 (远程集群共享盘时序无关)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    processor = BatchProcessor(config=config, max_workers=1)
    return processor._process_single_file(
        Path(file_path), Path(out_dir), clean_name
    )


def batch_task_adapter(task: tuple):
    """后端 map 单参数契约适配: 拆包批处理任务元组."""
    return process_file_task(*task)
