"""分布式后端插件测试 (Dask 后端 + 分区合并语义对拍).

核心约定: 分布式执行结果必须与单机执行完全一致 (对拍验证).
依赖 dask; 未安装时跳过.
"""

import functools

import pandas as pd
import pytest

dask = pytest.importorskip("dask")

from dqengine.distributed.parallel import (  # noqa: E402
    batch_task_adapter,
    merge_validation_results,
    process_file_task,
    validate_partition,
)
from dqengine.plugins.discovery import find_backend  # noqa: E402
from dqengine.rules.validator import RuleValidator  # noqa: E402


@pytest.fixture(scope="module")
def backend():
    b = find_backend("dask")
    if b is None:
        pytest.skip("dask 后端插件未加载")
    return b


RULES_YAML = """
columns:
  age:
    min: 0
    max: 120
    not_null: true
  city:
    allowed_values: [BJ, SH, GZ, SZ]
"""


@pytest.fixture
def messy_df():
    """违规行分散在各区间的数据集 (空值/超界/非法枚举)."""
    return pd.DataFrame(
        {
            "age": [15, 200, 30, None, 45] * 200,
            "city": ["BJ", "SH", "GZ", "BAD"] * 250,
        }
    )


@pytest.fixture
def rules_list(tmp_path):
    p = tmp_path / "rules.yaml"
    p.write_text(RULES_YAML, encoding="utf-8")
    return RuleValidator().load_rules(str(p))


def _violations_keyed(result):
    return sorted(
        (v.column, v.rule_type, v.row_index, str(v.value)) for v in result.violations
    )


class TestPartitionMerge:
    def test_merge_matches_local_validation(self, backend, messy_df, rules_list):
        """分区分片结果与单机整表验证完全一致 (行号含全局偏移)."""
        local = RuleValidator().validate(messy_df, rules_list)
        dist = backend.map_partitions(
            messy_df,
            4,
            functools.partial(validate_partition, rules=rules_list),
            functools.partial(merge_validation_results, total_rules=len(rules_list)),
        )
        assert dist.passed == local.passed
        assert dist.total_rules == local.total_rules
        assert dist.failed_rules == local.failed_rules
        assert dist.passed_rules == local.passed_rules
        assert dist.total_violations == local.total_violations
        assert _violations_keyed(dist) == _violations_keyed(local)

    def test_merge_matches_local_csv_file(self, backend, tmp_path, rules_list):
        """CSV 路径分片 (dask 原生读取) 与单机加载整表验证一致."""
        csv_path = tmp_path / "data.csv"
        df = pd.DataFrame(
            {
                "age": list(range(0, 3000)) + [None] * 100,
                "city": ["BJ"] * 1550 + ["SH"] * 1550,
            }
        )
        df.to_csv(csv_path, index=False)

        local = RuleValidator().validate(df, rules_list)
        dist = backend.map_partitions(
            str(csv_path),
            3,
            functools.partial(validate_partition, rules=rules_list),
            functools.partial(merge_validation_results, total_rules=len(rules_list)),
        )
        assert _violations_keyed(dist) == _violations_keyed(local)

    def test_column_level_violation_deduplicated(self, rules_list):
        """列级违规 (列不存在) 分区执行 N 次只按规则去重, 与单机一致."""
        df = pd.DataFrame({"other": [1, 2, 3, 4]})
        local = RuleValidator().validate(df, rules_list)
        per_part = [validate_partition(df, row_offset=i * 4, rules=rules_list) for i in range(4)]
        merged = merge_validation_results(per_part, total_rules=len(rules_list))
        # 规则数 3 (age range / age not_null / city allowed_values) → 各保留一条
        assert len(merged.violations) == len(local.violations) == 3
        assert all(v.row_index == -1 for v in merged.violations)

    def test_row_offset_alignment(self, rules_list):
        """分区间违规行号与单机全局行号一一对应."""
        df = pd.DataFrame({"age": [200, 30, 250, 31, 260, 32]})
        local = RuleValidator().validate(df, rules_list)
        parts = [df.iloc[0:2], df.iloc[2:4], df.iloc[4:6]]
        per_part = [
            validate_partition(p, row_offset=i * 2, rules=rules_list)
            for i, p in enumerate(parts)
        ]
        merged = merge_validation_results(per_part, total_rules=len(rules_list))
        assert _violations_keyed(merged) == _violations_keyed(local)


class TestBackendMap:
    def test_map_preserves_order(self, backend):
        results = backend.map(lambda x: x * 2, [1, 2, 3, 4, 5])
        assert results == [2, 4, 6, 8, 10]

    def test_map_empty(self, backend):
        assert backend.map(lambda x: x, []) == []

    def test_map_unsupported_partition_format(self, backend, tmp_path):
        xlsx = tmp_path / "x.xlsx"
        pd.DataFrame({"a": [1]}).to_excel(xlsx, index=False)
        with pytest.raises(ValueError, match="不支持格式"):
            backend.map_partitions(
                str(xlsx), 2, lambda df, off: df, lambda rs: rs
            )


class TestDistributedBatch:
    def test_batch_matches_sequential(self, backend, tmp_path):
        """分布式批处理与顺序批处理对拍 (行数/评分逐文件一致)."""
        from dqengine.batch.processor import BatchProcessor

        src = tmp_path / "src"
        out_seq = tmp_path / "out_seq"
        out_dist = tmp_path / "out_dist"
        src.mkdir()
        for i in range(3):
            pd.DataFrame(
                {"a": [1, None, 3, None] * 10, "b": ["x", "y", "x", "z"] * 10}
            ).to_csv(src / f"d{i}.csv", index=False)

        bp = BatchProcessor()
        seq = bp.process(src, output_dir=out_seq, use_parallel=False)
        dist = bp.process(src, output_dir=out_dist, backend="dask")

        assert seq.total_files == dist.total_files
        assert seq.succeeded == dist.succeeded
        assert seq.failed == dist.failed
        assert seq.total_rows_before == dist.total_rows_before
        assert seq.total_rows_after == dist.total_rows_after
        assert seq.average_score_after == pytest.approx(dist.average_score_after)
        for a, b in zip(seq.files, dist.files):
            assert a.rows_after == b.rows_after
            assert a.score_after == pytest.approx(b.score_after)

    def test_unknown_backend_error(self, tmp_path):
        from dqengine.batch.processor import BatchProcessor

        src = tmp_path / "src"
        src.mkdir()
        pd.DataFrame({"a": [1]}).to_csv(src / "d.csv", index=False)
        with pytest.raises(ValueError, match="未找到执行后端插件"):
            BatchProcessor().process(src, output_dir=tmp_path / "o", backend="nope")

    def test_task_adapter_unpacks(self, tmp_path):
        """任务元组适配器正确拆包调用."""
        from dqengine.models.schemas import AppConfig

        src = tmp_path / "d.csv"
        pd.DataFrame({"a": [1, 2]}).to_csv(src, index=False)
        out = tmp_path / "o"
        result = batch_task_adapter(
            (str(src), str(out), "cleaned_d.csv", AppConfig())
        )
        assert result.success
        assert result.rows_after == 2

    def test_process_file_task_rebuilds_processor(self, tmp_path):
        from dqengine.models.schemas import AppConfig

        src = tmp_path / "d.csv"
        pd.DataFrame({"a": [1, None]}).to_csv(src, index=False)
        result = process_file_task(str(src), str(tmp_path / "o"), "c.csv", AppConfig())
        assert result.success
