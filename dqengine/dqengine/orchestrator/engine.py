"""DAG Pipeline 编排引擎 — 可编排、可依赖、可复用的治理流程."""

from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
import yaml

from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.drift.detector import DriftDetector
from dqengine.models.schemas import (
    DAGExecutionResult,
    DAGNode,
    DAGNodeStatus,
    DAGNodeType,
    DAGPipeline,
)
from dqengine.repair.date_standardizer import DateStandardizer
from dqengine.repair.duplicate import DuplicateCleaner
from dqengine.repair.missing_value import MissingValueCleaner
from dqengine.repair.outlier import OutlierDetector
from dqengine.report.advanced_generator import AdvancedReportGenerator
from dqengine.rules.validator import RuleValidator
from dqengine.semantic.detector import SemanticDetector


class DAGEngine:
    """DAG Pipeline 编排引擎.

    支持:
    - YAML Pipeline 定义
    - 节点依赖管理
    - 拓扑排序执行
    - 错误隔离

    Usage:
        engine = DAGEngine()
        result = engine.run_pipeline("pipeline.yaml")
    """

    # 节点执行器注册
    EXECUTORS: Dict[DAGNodeType, Callable] = {}

    def __init__(self) -> None:
        self.loader = DataLoader()
        self.profiler = Profiler()
        self.scorer = QualityScorer()
        self.validator = RuleValidator()
        self.detector = SemanticDetector()
        self.drift_detector = DriftDetector()
        self._register_executors()

    def _register_executors(self) -> None:
        """注册内置节点执行器."""
        self.EXECUTORS = {
            DAGNodeType.LOAD: self._exec_load,
            DAGNodeType.PROFILE: self._exec_profile,
            DAGNodeType.VALIDATE: self._exec_validate,
            DAGNodeType.CLEAN: self._exec_clean,
            DAGNodeType.SCORE: self._exec_score,
            DAGNodeType.REPORT: self._exec_report,
            DAGNodeType.SEMANTIC: self._exec_semantic,
            DAGNodeType.DRIFT: self._exec_drift,
            DAGNodeType.EXPORT: self._exec_export,
        }

    def register_executor(self, node_type: DAGNodeType, executor: Callable) -> None:
        """注册自定义节点执行器."""
        self.EXECUTORS[node_type] = executor

    def load_pipeline(self, pipeline_path: str) -> DAGPipeline:
        """从 YAML 文件加载 Pipeline 定义."""
        path = Path(pipeline_path)
        if not path.exists():
            raise FileNotFoundError(f"Pipeline 文件未找到: {pipeline_path}")

        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        pipeline_config = config.get("pipeline", config)
        nodes: List[DAGNode] = []

        for step in pipeline_config.get("steps", []):
            if isinstance(step, str):
                # 简单模式: 步骤名即节点类型
                node_type = DAGNodeType(step.strip())
                nodes.append(DAGNode(node_id=step.strip(), node_type=node_type))
            elif isinstance(step, dict):
                node_type = DAGNodeType(step["type"])
                node_id = step.get("id", step["type"])
                depends_on = step.get("depends_on", [])
                config_dict = step.get("config", {})
                nodes.append(
                    DAGNode(
                        node_id=node_id,
                        node_type=node_type,
                        depends_on=depends_on if isinstance(depends_on, list) else [depends_on],
                        config=config_dict,
                    )
                )

        # 自动推断依赖: 如果只有一个节点且无显式依赖,按顺序排列
        if len(nodes) > 1 and all(not n.depends_on for n in nodes):
            for i in range(1, len(nodes)):
                nodes[i].depends_on = [nodes[i - 1].node_id]

        return DAGPipeline(
            name=pipeline_config.get("name", "pipeline"),
            description=pipeline_config.get("description", ""),
            nodes=nodes,
        )

    def execute(self, pipeline: DAGPipeline, input_file: Optional[str] = None) -> DAGExecutionResult:
        """执行 DAG Pipeline."""
        start_time = time.time()
        context: Dict[str, Any] = {"input_file": input_file, "dataframe": None, "results": {}}

        # 拓扑排序
        sorted_nodes = self._topological_sort(pipeline.nodes)

        for node in sorted_nodes:
            node.status = DAGNodeStatus.RUNNING
            node.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")

            try:
                executor = self.EXECUTORS.get(node.node_type)
                if executor is None:
                    raise ValueError(f"未知节点类型: {node.node_type}")

                result = executor(context, node)
                node.result = result
                node.status = DAGNodeStatus.COMPLETED
                context["results"][node.node_id] = result
            except Exception as e:
                node.status = DAGNodeStatus.FAILED
                node.error = str(e)

            node.completed_at = time.strftime("%Y-%m-%dT%H:%M:%S")

        elapsed = (time.time() - start_time) * 1000
        nodes_failed = sum(1 for n in pipeline.nodes if n.status == DAGNodeStatus.FAILED)

        return DAGExecutionResult(
            pipeline_name=pipeline.name,
            success=nodes_failed == 0,
            nodes_executed=len(pipeline.nodes),
            nodes_failed=nodes_failed,
            total_duration_ms=round(elapsed, 2),
            node_results={n.node_id: n for n in pipeline.nodes},
        )

    def run_pipeline(self, pipeline_path: str, input_file: Optional[str] = None) -> DAGExecutionResult:
        """加载并执行 Pipeline 文件."""
        pipeline = self.load_pipeline(pipeline_path)
        if input_file and not pipeline.nodes[0].config.get("input"):
            pipeline.nodes[0].config["input"] = input_file
        return self.execute(pipeline, input_file)

    def _topological_sort(self, nodes: List[DAGNode]) -> List[DAGNode]:
        """拓扑排序 (Kahn's algorithm)."""
        node_map = {n.node_id: n for n in nodes}
        in_degree = {n.node_id: len(n.depends_on) for n in nodes}
        adj: Dict[str, List[str]] = {n.node_id: [] for n in nodes}

        for n in nodes:
            for dep in n.depends_on:
                if dep in adj:
                    adj[dep].append(n.node_id)

        queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
        sorted_nodes: List[DAGNode] = []

        while queue:
            nid = queue.popleft()
            sorted_nodes.append(node_map[nid])
            for neighbor in adj[nid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_nodes) != len(nodes):
            raise ValueError("Pipeline 中存在循环依赖!")
        return sorted_nodes

    # ---- 内置执行器 ----

    def _exec_load(self, ctx: dict, node: DAGNode) -> dict:
        input_path = node.config.get("input", ctx.get("input_file", ""))
        if not input_path:
            raise ValueError("缺少输入文件路径")
        df = self.loader.load(Path(input_path))
        ctx["dataframe"] = df
        return {"rows": len(df), "columns": len(df.columns)}

    def _exec_profile(self, ctx: dict, node: DAGNode) -> dict:
        df = self._get_df(ctx)
        profile = self.profiler.profile(df)
        ctx["profile"] = profile
        return profile.model_dump()

    def _exec_validate(self, ctx: dict, node: DAGNode) -> dict:
        df = self._get_df(ctx)
        rules_path = node.config.get("rules", "configs/rules.yaml")
        result = self.validator.validate(df, rules_path)
        ctx["validation"] = result
        return result.model_dump()

    def _exec_clean(self, ctx: dict, node: DAGNode) -> dict:
        df = self._get_df(ctx)
        rows_before = len(df)

        df, r1 = MissingValueCleaner().clean(df)
        df, r2 = DuplicateCleaner().clean(df)
        df, r3 = DateStandardizer().standardize(df)

        ctx["dataframe"] = df
        return {"rows_before": rows_before, "rows_after": len(df)}

    def _exec_score(self, ctx: dict, node: DAGNode) -> dict:
        df = self._get_df(ctx)
        profile = ctx.get("profile") or self.profiler.profile(df)
        score = self.scorer.score(df, profile)
        return score.model_dump()

    def _exec_report(self, ctx: dict, node: DAGNode) -> dict:
        df = self._get_df(ctx)
        output = node.config.get("output", "report.html")
        profile = ctx.get("profile") or self.profiler.profile(df)
        score = self.scorer.score(df, profile)
        gen = AdvancedReportGenerator()
        from dqengine.models.schemas import ReportFormat

        fmt = node.config.get("format", "html")
        fmt_map = {"html": ReportFormat.HTML, "json": ReportFormat.JSON, "markdown": ReportFormat.MARKDOWN}
        gen.generate(profile, score, [], [], df=df, formats=[fmt_map.get(fmt, ReportFormat.HTML)])
        return {"output": output}

    def _exec_semantic(self, ctx: dict, node: DAGNode) -> dict:
        df = self._get_df(ctx)
        result = self.detector.detect(df)
        return result.model_dump()

    def _exec_drift(self, ctx: dict, node: DAGNode) -> dict:
        baseline = node.config.get("baseline")
        current = node.config.get("current")
        if not baseline or not current:
            raise ValueError("漂移检测需要 baseline 和 current 参数")
        report = self.drift_detector.detect(baseline, current)
        return report.model_dump()

    def _exec_export(self, ctx: dict, node: DAGNode) -> dict:
        df = self._get_df(ctx)
        output = node.config.get("output", "exported_data.csv")
        fmt = node.config.get("format", "csv")
        if fmt == "csv":
            df.to_csv(output, index=False)
        elif fmt == "json":
            df.to_json(output, orient="records", force_ascii=False)
        elif fmt == "parquet":
            df.to_parquet(output, index=False)
        return {"output": output, "rows": len(df)}

    @staticmethod
    def _get_df(ctx: dict) -> pd.DataFrame:
        df = ctx.get("dataframe")
        if df is None:
            raise ValueError("上下文缺少 DataFrame，请确保 LOAD 节点已执行")
        return df
