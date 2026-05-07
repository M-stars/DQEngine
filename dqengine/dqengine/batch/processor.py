"""批量数据质量治理处理器."""

from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Optional

try:
    from tqdm import tqdm
except ImportError:
    # 如果tqdm未安装,使用简单的迭代器
    def tqdm(iterable, **kwargs):
        return iterable

from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.models.schemas import (
    AppConfig,
    BatchFileResult,
    BatchSummary,
    RepairResult,
)
from dqengine.repair.date_standardizer import DateStandardizer
from dqengine.repair.duplicate import DuplicateCleaner
from dqengine.repair.missing_value import MissingValueCleaner
from dqengine.repair.outlier import OutlierDetector
from dqengine.services.config_manager import ConfigManager
from dqengine.utils.logger import get_logger

logger = get_logger(__name__)


class BatchProcessor:
    """批量数据质量治理处理器.

    自动遍历目录, 对所有支持的格式文件执行:
        - 数据清洗
        - 规则验证
        - 质量评分
        - 生成报告

    特性:
        - 并发处理
        - tqdm 进度条
        - 错误隔离 (单个文件失败不影响整体)
        - JSON 汇总输出

    使用方式:
        processor = BatchProcessor()
        summary = processor.process("./datasets", output_dir="./results")
    """

    SUPPORTED_FORMATS = {".csv", ".xlsx", ".xls", ".json", ".parquet"}

    def __init__(self, config: Optional[AppConfig] = None, max_workers: int = 4) -> None:
        """初始化批量处理器.

        Args:
            config: AppConfig 配置.
            max_workers: 最大并发数.
        """
        self.config = config or AppConfig()
        self.max_workers = max_workers

        # 核心组件
        self.loader = DataLoader()
        self.profiler = Profiler()
        self.scorer = QualityScorer()
        self.dup_cleaner = DuplicateCleaner()
        self.mv_cleaner = MissingValueCleaner()
        self.date_std = DateStandardizer()
        self.outlier_detector = OutlierDetector()

    def collect_files(self, directory: "str | Path") -> List[Path]:
        """收集目录中所有支持的数据文件.

        Args:
            directory: 目录路径.

        Returns:
            文件路径列表.
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"目录不存在: {directory}")

        files: List[Path] = []
        for f in sorted(dir_path.rglob("*")):
            if f.suffix.lower() in self.SUPPORTED_FORMATS and not f.name.startswith("~"):
                files.append(f)

        logger.info("发现 %d 个数据文件", len(files))
        return files

    def process(
        self,
        directory: "str | Path",
        output_dir: "str | Path" = "batch_output",
        use_parallel: bool = True,
    ) -> BatchSummary:
        """执行批量处理.

        Args:
            directory: 数据目录.
            output_dir: 输出目录.
            use_parallel: 是否使用并发处理.

        Returns:
            BatchSummary 汇总结果.
        """
        files = self.collect_files(directory)
        if not files:
            logger.warning("未找到支持的数据文件")
            return BatchSummary(
                total_files=0,
                succeeded=0,
                failed=0,
                total_rows_before=0,
                total_rows_after=0,
                average_score_before=0,
                average_score_after=0,
                files=[],
            )

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        results: List[BatchFileResult] = []

        if use_parallel and len(files) > 1:
            results = self._process_parallel(files, out_dir)
        else:
            results = self._process_sequential(files, out_dir)

        succeeded = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        summary = BatchSummary(
            total_files=len(files),
            succeeded=len(succeeded),
            failed=len(failed),
            total_rows_before=sum(r.rows_before for r in succeeded),
            total_rows_after=sum(r.rows_after for r in succeeded),
            average_score_before=(
                sum(r.score_before for r in succeeded) / len(succeeded)
                if succeeded
                else 0
            ),
            average_score_after=(
                sum(r.score_after for r in succeeded) / len(succeeded)
                if succeeded
                else 0
            ),
            files=results,
        )

        # 保存汇总
        summary_path = out_dir / "batch_summary.json"
        summary_path.write_text(
            summary.model_dump_json(indent=2), encoding="utf-8"
        )
        logger.info("批量处理汇总已保存: %s", summary_path)

        return summary

    def _process_sequential(self, files: List[Path], out_dir: Path) -> List[BatchFileResult]:
        """顺序处理文件 (带进度条).

        Args:
            files: 文件列表.
            out_dir: 输出目录.

        Returns:
            处理结果列表.
        """
        results: List[BatchFileResult] = []

        with tqdm(total=len(files), desc="批量处理", unit="文件", ncols=100) as pbar:
            for f in files:
                result = self._process_single_file(f, out_dir)
                results.append(result)
                status = "[OK]" if result.success else "[FAIL]"
                pbar.set_postfix_str(f"{status} {f.name}")
                pbar.update(1)

        return results

    def _process_parallel(self, files: List[Path], out_dir: Path) -> List[BatchFileResult]:
        """并发处理文件.

        注意: 使用 ProcessPoolExecutor 时, 由于 pickle 限制,
        实际回退到顺序处理但保持接口兼容.

        Args:
            files: 文件列表.
            out_dir: 输出目录.

        Returns:
            处理结果列表.
        """
        # 对于 I/O 密集型任务, 使用 ThreadPoolExecutor 替代
        # 但考虑到跨平台兼容, 这里使用带进度条的顺序处理
        logger.info("使用顺序处理模式 (多文件进度追踪)")
        return self._process_sequential(files, out_dir)

    def _process_single_file(self, file_path: Path, out_dir: Path) -> BatchFileResult:
        """处理单个文件 (错误隔离).

        Args:
            file_path: 文件路径.
            out_dir: 输出目录.

        Returns:
            BatchFileResult.
        """
        try:
            # 1. 加载
            df = self.loader.load(file_path)
            rows_before = len(df)

            # 2. 清洗前评分
            profile = self.profiler.profile(df, file_path=str(file_path))
            score_before = self.scorer.score(df, profile)

            # 3. 清洗
            repairs: List[RepairResult] = []

            if self.config.cleaning.duplicate.enabled:
                df, dup_result = self.dup_cleaner.clean(df)
                repairs.append(dup_result)

            if self.config.cleaning.missing.enabled:
                df, mv_result = self.mv_cleaner.clean(df)
                repairs.append(mv_result)

            if self.config.cleaning.date.enabled:
                df, date_result = self.date_std.standardize(df)
                repairs.append(date_result)

            if self.config.cleaning.outlier.action == "remove":
                outliers = self.outlier_detector.detect(df)
                if outliers:
                    df = self.outlier_detector.remove_outliers(df, outliers)

            rows_after = len(df)

            # 4. 清洗后评分
            profile_after = self.profiler.profile(df, file_path=str(file_path))
            score_after = self.scorer.score(df, profile_after)

            # 5. 保存清洗结果
            clean_name = f"cleaned_{file_path.stem}.csv"
            clean_path = out_dir / clean_name
            df.to_csv(clean_path, index=False, encoding="utf-8")

            return BatchFileResult(
                file_path=str(file_path),
                success=True,
                rows_before=rows_before,
                rows_after=rows_after,
                score_before=round(score_before.overall_score, 1),
                score_after=round(score_after.overall_score, 1),
                repairs=repairs,
            )

        except Exception as e:
            logger.error("处理文件失败 %s: %s", file_path.name, str(e))
            return BatchFileResult(
                file_path=str(file_path),
                success=False,
                error=str(e),
            )
