"""repair/ 模块回归测试: 日期标准化 / 缺失填充 / 异常值 / 去重.

重点兜底 v1.0.0 的 P0/P1 修复: 数值列不被日期标准化毁掉、nullable Int64
填充不崩、重复索引异常值不误删、threshold<=0 不清空数据集.
"""

import numpy as np
import pandas as pd
import pytest

from dqengine.repair.date_standardizer import DateStandardizer
from dqengine.repair.duplicate import DuplicateCleaner
from dqengine.repair.missing_value import MissingValueCleaner
from dqengine.repair.outlier import OutlierDetector


@pytest.fixture
def df_mixed():
    return pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "join_date": ["2024-01-15", "2024/02/20", "15-03-2024", None, "2024-05-01"],
            "amount": [100.0, 200.0, None, 400.0, 500.0],
        }
    )


# ---- 日期标准化 ----


class TestDateStandardizer:
    def test_formats_normalized(self):
        df = pd.DataFrame({"d": ["2024/01/15", "2024/02/20", "2024/03/05"]})
        out, result = DateStandardizer().standardize(df)
        assert result.operation == "date_standardization"
        assert result.changes_made == 3
        assert out.loc[0, "d"] == "2024-01-15"
        assert out.loc[2, "d"] == "2024-03-05"

    def test_mixed_separators_column_skipped_not_cleared(self):
        """混合分隔符列 pandas 无法整体推断格式, 保守跳过且不清空原值."""
        original = ["2024-01-15", "2024/02/20", "2024.03.05"]
        out, result = DateStandardizer().standardize(pd.DataFrame({"d": original}))
        assert out["d"].tolist() == original  # 原值原样保留, 不静默清空
        assert result.changes_made == 0

    def test_numeric_columns_untouched(self):
        """P0 回归: 数值列 (时间戳/序号) 不得被日期标准化毁成 1970-01-01."""
        df = pd.DataFrame(
            {
                "seq": [1, 2, 3, 4],
                "epoch": [1700000000, 1700000001, 1700000002, 1700000003],
                "d": ["2024-01-01", "2024-01-02", None, "2024-01-04"],
            }
        )
        out, _ = DateStandardizer().standardize(df)
        assert out["seq"].tolist() == [1, 2, 3, 4]
        assert out["epoch"].tolist() == [1700000000, 1700000001, 1700000002, 1700000003]
        # 数值列不应出现任何日期字符串
        assert not out["epoch"].astype(str).str.startswith("1970").any()

    def test_unparseable_values_not_cleared(self):
        """P0 回归: 无法解析的合法文本不得被静默清空."""
        df = pd.DataFrame({"note": ["hello", "world"], "d": ["2024-01-01", "2024-01-02"]})
        out, _ = DateStandardizer().standardize(df)
        assert out["note"].tolist() == ["hello", "world"]

    def test_custom_target_format(self):
        df = pd.DataFrame({"d": ["2024-01-15"]})
        out, _ = DateStandardizer().standardize(df, target_format="%Y/%m/%d")
        assert out.loc[0, "d"] == "2024/01/15"

    def test_missing_date_column_left_as_na(self):
        df = pd.DataFrame({"d": ["2024-01-01", None]})
        out, _ = DateStandardizer().standardize(df)
        assert pd.isna(out.loc[1, "d"])


# ---- 缺失值 ----


class TestMissingValueCleaner:
    def test_mean_fill(self, df_mixed):
        out, result = MissingValueCleaner().clean(df_mixed, strategy="mean")
        assert result.operation == "missing_value_fill"
        assert out["amount"].isna().sum() == 0
        assert out.loc[2, "amount"] == pytest.approx(300.0)  # (100+200+400+500)/4

    def test_median_fill(self, df_mixed):
        out, _ = MissingValueCleaner().clean(df_mixed, strategy="median")
        assert out.loc[2, "amount"] == pytest.approx(300.0)

    def test_constant_fill_numeric(self, df_mixed):
        out, _ = MissingValueCleaner().clean(df_mixed, strategy="constant", constant_value=0)
        assert out["amount"].isna().sum() == 0
        assert out.loc[2, "amount"] == 0

    def test_constant_fill_text_column(self):
        df = pd.DataFrame({"s": ["a", None, "c"]})
        out, _ = MissingValueCleaner().clean(df, strategy="constant", constant_value="N/A")
        assert out["s"].tolist() == ["a", "N/A", "c"]

    def test_constant_invalid_for_numeric_column_is_recorded_skip(self, df_mixed):
        """数值列 + 非数值常量: 明确跳过并记录原因, 不静默丢数据也不崩溃."""
        _, result = MissingValueCleaner().clean(
            df_mixed, strategy="constant", constant_value="N/A"
        )
        assert "not valid for numeric column" in result.details["amount"]
        # join_date 是文本列, "N/A" 常量正常填充 1 处; amount 被跳过
        assert result.changes_made == 1
        assert result.details["join_date"] == "constant=N/A"

    def test_drop_strategy(self, df_mixed):
        out, _ = MissingValueCleaner().clean(df_mixed, strategy="drop")
        assert out["amount"].isna().sum() == 0
        assert len(out) < len(df_mixed)

    def test_nullable_int64_fill_no_crash(self):
        """P0 回归: nullable Int64 列缺失填充不得崩溃."""
        df = pd.DataFrame({"v": pd.array([1, None, 3], dtype="Int64")})
        out, _ = MissingValueCleaner().clean(df, strategy="mean")
        assert out["v"].isna().sum() == 0

    def test_all_na_column(self):
        df = pd.DataFrame({"v": [np.nan, np.nan], "k": [1, 2]})
        out, _ = MissingValueCleaner().clean(df, strategy="mean")
        assert len(out) == 2  # 全空列不清空数据集


# ---- 异常值 ----


class TestOutlierDetector:
    def test_iqr_detect(self):
        df = pd.DataFrame({"v": [10] * 20 + [10000]})
        outliers = OutlierDetector().detect(df, method="iqr", threshold=1.5)
        assert len(outliers) >= 1
        assert outliers[0].column == "v"

    def test_remove_outliers(self):
        df = pd.DataFrame({"v": [10] * 20 + [10000]})
        det = OutlierDetector()
        outliers = det.detect(df)
        out = det.remove_outliers(df, outliers)
        assert len(out) == 20
        assert out["v"].max() == 10

    def test_duplicate_index_no_crash_no_wrong_removal(self):
        """P1 回归: 重复索引下检测/移除不得崩溃或误删行."""
        df = pd.DataFrame({"v": [10.0] * 6 + [10000.0]}, index=[0, 0, 1, 1, 2, 2, 3])
        det = OutlierDetector()
        outliers = det.detect(df)
        out = det.remove_outliers(df, outliers)
        assert 10000.0 not in out["v"].values
        assert len(out) == 6  # 只删异常行, 不因索引重复多删

    def test_threshold_must_be_positive(self):
        """P1 回归: threshold<=0 不得清空数据集."""
        df = pd.DataFrame({"v": [1, 2, 3, 4, 5]})
        with pytest.raises(ValueError):
            OutlierDetector().detect(df, threshold=0)

    def test_zscore_method(self):
        df = pd.DataFrame({"v": [10.0] * 30 + [500.0]})
        outliers = OutlierDetector().detect(df, method="zscore", threshold=3)
        assert len(outliers) >= 1

    def test_non_numeric_columns_ignored(self):
        df = pd.DataFrame({"s": ["a", "b", "c"], "v": [1, 2, 3]})
        outliers = OutlierDetector().detect(df)
        assert all(o.column == "v" for o in outliers)


# ---- 去重 ----


class TestDuplicateCleaner:
    def test_keep_first(self):
        df = pd.DataFrame({"k": [1, 1, 2], "v": ["a", "a", "c"]})
        out, result = DuplicateCleaner().clean(df, keep="first")
        assert result.operation == "duplicate_removal"
        assert len(out) == 2
        assert out.loc[out["k"] == 1, "v"].iloc[0] == "a"

    def test_keep_last(self):
        df = pd.DataFrame({"k": [1, 1, 2], "v": ["a", "a", "c"]})
        out, _ = DuplicateCleaner().clean(df, keep="last")
        assert len(out) == 2
        assert out.loc[out["k"] == 1, "v"].iloc[0] == "a"

    def test_no_duplicates_no_change(self):
        df = pd.DataFrame({"k": [1, 2, 3]})
        out, result = DuplicateCleaner().clean(df)
        assert len(out) == 3
        assert result.changes_made == 0
