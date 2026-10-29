"""Pipeline 代码生成器 - 根据治理策略自动生成可执行 Python Pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional


from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.models.schemas import AppConfig, PipelineConfig, PipelineStep
from dqengine.repair.date_standardizer import DateStandardizer
from dqengine.utils.logger import get_logger

logger = get_logger(__name__)


# Pipeline代码模板
PIPELINE_TEMPLATE = '''"""DQEngine 自动生成的数据治理 Pipeline.

生成时间: {generated_at}
源文件: {input_file}
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd


def load_data(file_path: str) -> pd.DataFrame:
    """加载数据文件.

    Args:
        file_path: 数据文件路径.

    Returns:
        DataFrame.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {{file_path}}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    elif suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    elif suffix == ".json":
        return pd.read_json(path)
    elif suffix == ".parquet":
        return pd.read_parquet(path)
    else:
        raise ValueError(f"不支持的格式: {{suffix}}")


def save_data(df: pd.DataFrame, file_path: str) -> None:
    """保存数据.

    Args:
        df: DataFrame.
        file_path: 输出路径.
    """
    path = Path(file_path)
    if path.suffix.lower() == ".xlsx":
        df.to_excel(path, index=False)
    elif path.suffix.lower() == ".parquet":
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False, encoding="utf-8")


{pipeline_steps}


def run_pipeline(
    input_file: str,
    output_file: str = "{output_file}",
) -> pd.DataFrame:
    """执行完整的数据治理Pipeline.

    Args:
        input_file: 输入数据文件路径.
        output_file: 输出文件路径.

    Returns:
        治理后的 DataFrame.
    """
    print(f"DQEngine Pipeline - 开始执行")
    print(f"  输入文件: {{input_file}}")

    # Step 1: 加载数据
    df = load_data(input_file)
    print(f"  已加载: {{len(df)}} 行, {{len(df.columns)}} 列")

    # Step 2-{step_count}: 执行治理步骤
{pipeline_calls}

    # 最终步骤: 保存结果
    save_data(df, output_file)
    print(f"  Pipeline 执行完成, 结果已保存到: {{output_file}}")

    return df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DQEngine Pipeline")
    parser.add_argument("input", help="输入数据文件")
    parser.add_argument("--output", "-o", default="{output_file}", help="输出文件路径")
    args = parser.parse_args()

    df = run_pipeline(args.input, args.output)
    print(f"\\n最终数据: {{len(df)}} 行, {{len(df.columns)}} 列")
'''


class PipelineGenerator:
    """Pipeline 代码生成器.

    根据当前治理策略自动生成可重复执行的 Python Pipeline 脚本.

    使用方式:
        gen = PipelineGenerator()
        gen.generate("data.csv", output_path="generated_pipeline.py")
    """

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        """初始化 Pipeline 生成器.

        Args:
            config: AppConfig 配置.
        """
        self.config = config or AppConfig()
        self.loader = DataLoader()
        self.profiler = Profiler()

    def generate(
        self,
        file_path: "str | Path",
        output_path: "str | Path" = "generated_pipeline.py",
    ) -> Path:
        """根据数据特征生成 Pipeline 脚本.

        Args:
            file_path: 输入数据文件 (用于分析字段特征).
            output_path: 输出的 Pipeline 脚本路径.

        Returns:
            生成的脚本文件路径.
        """
        path = Path(file_path)
        cleaning = self.config.cleaning

        # 分析数据特征以生成精确的步骤
        df = self.loader.load(path)
        profile = self.profiler.profile(df, file_path=str(path))

        steps: list[PipelineStep] = []

        # Step 1: 重复值移除
        if cleaning.duplicate.enabled:
            steps.append(
                PipelineStep(
                    step_name="remove_duplicates",
                    module="dqengine.repair.duplicate",
                    class_name="DuplicateCleaner",
                    method="clean",
                    parameters={"keep": cleaning.duplicate.keep},
                    description=f"移除重复行 (保留方式: {cleaning.duplicate.keep})",
                )
            )

        # Step 2: 缺失值填充
        if cleaning.missing.enabled:
            # 分析哪些列需要填充
            null_cols = [c.column_name for c in profile.columns if c.null_rate > 0]
            fill_params: dict = {"strategy": cleaning.missing.strategy}
            if cleaning.missing.constant_value is not None:
                fill_params["constant_value"] = cleaning.missing.constant_value
            steps.append(
                PipelineStep(
                    step_name="fill_missing_values",
                    module="dqengine.repair.missing_value",
                    class_name="MissingValueCleaner",
                    method="clean",
                    parameters=fill_params,
                    description=f"填充缺失值 (策略: {cleaning.missing.strategy}, "
                    f"受影响列: {len(null_cols)})",
                )
            )

        # Step 3: 日期标准化
        if cleaning.date.enabled:
            date_std = DateStandardizer()
            date_cols = date_std._detect_date_columns(df)
            steps.append(
                PipelineStep(
                    step_name="standardize_dates",
                    module="dqengine.repair.date_standardizer",
                    class_name="DateStandardizer",
                    method="standardize",
                    parameters={"target_format": cleaning.date.target_format},
                    description=f"标准化日期字段 (检测到 {len(date_cols)} 列: {date_cols})",
                )
            )

        # Step 4: 异常值检测
        if cleaning.outlier.enabled:
            steps.append(
                PipelineStep(
                    step_name="detect_outliers",
                    module="dqengine.repair.outlier",
                    class_name="OutlierDetector",
                    method="detect",
                    parameters={
                        "method": cleaning.outlier.method,
                        "threshold": cleaning.outlier.threshold,
                        "action": cleaning.outlier.action,
                    },
                    description=f"异常值检测 (方法: {cleaning.outlier.method}, "
                    f"动作: {cleaning.outlier.action})",
                )
            )

        pipeline = PipelineConfig(
            name=f"pipeline_{path.stem}",
            description=f"自动生成的 {path.name} 治理 Pipeline",
            steps=steps,
            input_file=str(path),
            output_file="cleaned_data.csv",
            generated_at=datetime.now().isoformat(),
        )

        # 生成代码
        code = self._generate_code(pipeline)

        output = Path(output_path)
        output.write_text(code, encoding="utf-8")
        logger.info("Pipeline 已生成: %s (%d 个步骤)", output, len(steps))

        return output

    def _generate_code(self, pipeline: PipelineConfig) -> str:
        """根据 Pipeline 配置生成可执行 Python 代码.

        Args:
            pipeline: Pipeline 配置.

        Returns:
            Python 源代码字符串.
        """
        # 生成各步骤的函数定义
        step_funcs = []
        step_calls = []

        for i, step in enumerate(pipeline.steps, start=2):
            func_name = step.step_name
            step_calls.append(f"    df = {func_name}(df)")
            step_funcs.append(self._generate_step_function(step, i))

        step_code = "\n\n".join(step_funcs)
        calls_code = "\n".join(step_calls)
        total_steps = len(pipeline.steps) + 2  # load + save + cleaning steps

        # Windows 路径 (C:\Users\...) 在普通 docstring 里触发 \U
        # unicodeescape 错误; 三连引号则终止 docstring —— 均安全化
        input_file = self._docstring_safe(pipeline.input_file)
        output_file = self._docstring_safe(pipeline.output_file)

        return PIPELINE_TEMPLATE.format(
            generated_at=pipeline.generated_at,
            input_file=input_file,
            output_file=output_file,
            pipeline_steps=step_code,
            pipeline_calls=calls_code,
            step_count=total_steps,
        )

    @staticmethod
    def _docstring_safe(text: str) -> str:
        """使文本可安全嵌入生成代码的三引号 docstring.

        CSV 列名等用户文本可能包含三连引号 (提前终止 docstring, 其后
        内容被当作代码执行 —— 已实测可构造任意命令执行) 或反斜杠
        (触发 unicodeescape SyntaxError). 两者在此归一化.
        """
        return str(text).replace("\\", "/").replace('"""', "'''")

    # Parameters each repair method actually accepts; anything else in
    # step.parameters is informational and must not be forwarded, or the
    # generated code would crash with an unexpected-keyword TypeError.
    _METHOD_PARAMS: dict[tuple[str, str], tuple[str, ...]] = {
        ("DuplicateCleaner", "clean"): ("keep",),
        ("MissingValueCleaner", "clean"): ("strategy", "constant_value"),
        ("DateStandardizer", "standardize"): ("target_format",),
        ("OutlierDetector", "detect"): ("method", "threshold"),
    }

    def _generate_step_function(self, step: PipelineStep, index: int) -> str:
        """生成单个步骤的函数代码.

        Args:
            step: Pipeline 步骤.
            index: 步骤索引.

        Returns:
            函数定义源代码.
        """
        accepted = self._METHOD_PARAMS.get((step.class_name, step.method), ())
        params_str = ", ".join(
            f"{k}={step.parameters[k]!r}" for k in accepted if k in step.parameters
        )
        call_args = f"df, {params_str}" if params_str else "df"

        # OutlierDetector.detect returns list[OutlierRecord], not a
        # (df, result) tuple — the generated code must handle it accordingly.
        if not str(step.step_name).isidentifier():
            raise ValueError(f"步骤名必须是合法 Python 标识符: {step.step_name!r}")
        safe_desc = self._docstring_safe(step.description)
        safe_step_name = self._docstring_safe(step.step_name)

        if step.class_name == "OutlierDetector" and step.method == "detect":
            action = step.parameters.get("action", "flag")
            if action == "remove":
                return f'''def {step.step_name}(df: pd.DataFrame) -> pd.DataFrame:
    """Step {index}: {safe_desc}

    使用 {step.class_name}.detect() + remove_outliers()
    """
    from {step.module} import {step.class_name}

    detector = {step.class_name}()
    outliers = detector.detect({call_args})
    df_clean = detector.remove_outliers(df, outliers)
    print(f"  [{safe_step_name}] 检出 {{len(outliers)}} 个异常值, "
          f"移除 {{len(df) - len(df_clean)}} 行")
    return df_clean'''

            return f'''def {step.step_name}(df: pd.DataFrame) -> pd.DataFrame:
    """Step {index}: {safe_desc}

    使用 {step.class_name}.detect()
    """
    from {step.module} import {step.class_name}

    detector = {step.class_name}()
    outliers = detector.detect({call_args})
    print(f"  [{safe_step_name}] 检出 {{len(outliers)}} 个异常值 (action=flag, 不修改数据)")
    return df'''

        return f'''def {step.step_name}(df: pd.DataFrame) -> pd.DataFrame:
    """Step {index}: {safe_desc}

    使用 {step.class_name}.{step.method}()
    """
    from {step.module} import {step.class_name}

    processor = {step.class_name}()
    df_clean, result = processor.{step.method}({call_args})
    print(f"  [{safe_step_name}] {{result.changes_made}} 处变更, "
          f"{{result.columns_affected}} 列受影响")
    return df_clean'''
