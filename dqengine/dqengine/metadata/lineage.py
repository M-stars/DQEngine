"""元数据与数据血缘追踪系统."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from dqengine.models.schemas import DataLineage, ExecutionRecord, LineageStep


class LineageTracker:
    """数据血缘追踪器.

    记录:
    - 数据来源 (source tracking)
    - 清洗步骤 (transformation steps)
    - 规则执行历史 (rule execution history)
    - Pipeline 执行历史 (pipeline execution history)

    Usage:
        tracker = LineageTracker()
        tracker.start_session("data.csv")
        tracker.record_step("load", input="data.csv", output="memory")
        ...
        tracker.save("lineage.json")
    """

    def __init__(self) -> None:
        self._lineages: Dict[str, DataLineage] = {}
        self._executions: List[ExecutionRecord] = []

    def start_session(self, source_path: str) -> str:
        """开始新的血缘追踪会话."""
        dataset_id = str(uuid.uuid4())[:8]
        self._lineages[dataset_id] = DataLineage(
            dataset_id=dataset_id,
            source_path=source_path,
            created_at=datetime.now().isoformat(),
        )
        return dataset_id

    def record_step(
        self,
        dataset_id: str,
        step_name: str,
        input_data: str = "",
        output_data: str = "",
        operation: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        duration_ms: float = 0.0,
    ) -> None:
        """记录一个处理步骤."""
        if dataset_id not in self._lineages:
            raise ValueError(f"未知数据集: {dataset_id}")

        step = LineageStep(
            step_id=str(uuid.uuid4())[:8],
            step_name=step_name,
            input_data=input_data,
            output_data=output_data,
            operation=operation,
            parameters=parameters or {},
            duration_ms=duration_ms,
        )
        self._lineages[dataset_id].steps.append(step)

    def record_schema(self, dataset_id: str, df: pd.DataFrame) -> None:
        """记录当前 Schema."""
        if dataset_id in self._lineages:
            self._lineages[dataset_id].current_schema = {
                col: str(dtype) for col, dtype in df.dtypes.items()
            }

    def record_execution(
        self,
        rule_name: str,
        file_path: str,
        passed: bool,
        violations_count: int,
        execution_time_ms: float,
    ) -> None:
        """记录规则执行历史."""
        record = ExecutionRecord(
            execution_id=str(uuid.uuid4())[:8],
            rule_name=rule_name,
            file_path=file_path,
            passed=passed,
            violations_count=violations_count,
            execution_time_ms=execution_time_ms,
        )
        self._executions.append(record)

    def get_lineage(self, dataset_id: str) -> Optional[DataLineage]:
        """获取数据集血缘."""
        return self._lineages.get(dataset_id)

    def get_execution_history(
        self, rule_name: Optional[str] = None, limit: int = 100
    ) -> List[ExecutionRecord]:
        """获取规则执行历史."""
        records = self._executions
        if rule_name:
            records = [r for r in records if r.rule_name == rule_name]
        return records[-limit:]

    def save(self, output_path: str = "lineage.json") -> str:
        """保存血缘数据到 JSON 文件."""
        data = {
            "lineages": {
                k: v.model_dump() for k, v in self._lineages.items()
            },
            "executions": [e.model_dump() for e in self._executions],
            "exported_at": datetime.now().isoformat(),
        }
        path = Path(output_path)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def load(self, input_path: str) -> None:
        """从 JSON 文件加载血缘数据."""
        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(f"血缘文件未找到: {input_path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        for k, v in data.get("lineages", {}).items():
            self._lineages[k] = DataLineage(**v)
        for e in data.get("executions", []):
            self._executions.append(ExecutionRecord(**e))

    def generate_lineage_graph(self, dataset_id: str, output_path: str = "lineage_graph.html") -> str:
        """生成血缘关系可视化 HTML."""
        lineage = self._lineages.get(dataset_id)
        if not lineage:
            raise ValueError(f"未知数据集: {dataset_id}")

        nodes_json = json.dumps([
            {"id": step.step_id, "label": step.step_name, "title": step.operation}
            for step in lineage.steps
        ])
        edges_json = json.dumps([
            {"from": lineage.steps[i].step_id, "to": lineage.steps[i + 1].step_id}
            for i in range(len(lineage.steps) - 1)
        ])

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>DQEngine 数据血缘</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/vis-network.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; }}
        .header {{ text-align: center; padding: 2rem; background: #1e293b; }}
        .header h1 {{ color: #38bdf8; }}
        .header p {{ color: #94a3b8; }}
        #lineage-graph {{ height: 500px; border: 1px solid #334155; margin: 2rem; border-radius: 12px; }}
        .steps {{ margin: 2rem; }}
        .step-card {{ background: #1e293b; border-radius: 8px; padding: 1rem; margin-bottom: 0.5rem; border-left: 4px solid #38bdf8; }}
        .step-card .name {{ font-weight: bold; color: #38bdf8; }}
        .step-card .meta {{ color: #94a3b8; font-size: 0.85rem; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>DQEngine 数据血缘追踪</h1>
        <p>数据集: {lineage.dataset_id} | 来源: {lineage.source_path}</p>
    </div>
    <div id="lineage-graph"></div>
    <div class="steps">
        <h2 style="color:#38bdf8; margin-bottom:1rem;">处理步骤 ({len(lineage.steps)})</h2>
"""
        for step in lineage.steps:
            html += f"""
        <div class="step-card">
            <div class="name">{step.step_name}</div>
            <div class="meta">{step.operation} | {step.input_data} → {step.output_data} | {step.duration_ms:.1f}ms</div>
        </div>"""

        html += f"""
    </div>
    <script>
        var nodes = new vis.DataSet({nodes_json});
        var edges = new vis.DataSet({edges_json});
        var container = document.getElementById('lineage-graph');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            layout: {{ hierarchical: {{ direction: 'LR', sortMethod: 'directed' }} }},
            nodes: {{ shape: 'box', color: {{ background: '#1e293b', border: '#38bdf8' }},
                font: {{ color: '#e2e8f0' }} }},
            edges: {{ color: '#38bdf8', arrows: 'to' }}
        }};
        new vis.Network(container, data, options);
    </script>
</body>
</html>"""
        path = Path(output_path)
        path.write_text(html, encoding="utf-8")
        return str(path)
