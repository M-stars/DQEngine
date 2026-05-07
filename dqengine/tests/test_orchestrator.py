"""DAG Pipeline 编排引擎测试."""

import tempfile
from pathlib import Path

import pandas as pd
import pytest
import yaml

from dqengine.models.schemas import DAGNode, DAGNodeStatus, DAGNodeType, DAGPipeline
from dqengine.orchestrator.engine import DAGEngine


class TestDAGEngine:
    """DAG 引擎测试."""

    @pytest.fixture
    def engine(self):
        return DAGEngine()

    @pytest.fixture
    def sample_csv(self):
        df = pd.DataFrame({
            "name": ["Alice", "Bob", "Charlie", "Diana"],
            "age": [28, 35, 42, 31],
            "email": ["a@x.com", "b@y.com", "c@z.com", "d@w.com"],
            "salary": [50000, 65000, 80000, 72000],
        })
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            df.to_csv(f.name, index=False)
            return f.name

    def test_load_pipeline_simple_steps(self, engine):
        config = {
            "pipeline": {
                "name": "test",
                "steps": ["load", "profile", "score"],
            }
        }
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            yaml.dump(config, f)
            f_path = f.name

        try:
            pipeline = engine.load_pipeline(f_path)
            assert pipeline.name == "test"
            assert len(pipeline.nodes) == 3
            assert pipeline.nodes[0].node_type == DAGNodeType.LOAD
            assert pipeline.nodes[0].depends_on == []
            assert pipeline.nodes[1].depends_on == ["load"]
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_load_pipeline_with_config(self, engine):
        config = {
            "pipeline": {
                "name": "test_config",
                "steps": [
                    {
                        "type": "load",
                        "id": "load_data",
                        "config": {"input": "data.csv"},
                    },
                    {
                        "type": "clean",
                        "id": "clean_data",
                        "depends_on": ["load_data"],
                    },
                ],
            }
        }
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            yaml.dump(config, f)
            f_path = f.name

        try:
            pipeline = engine.load_pipeline(f_path)
            assert len(pipeline.nodes) == 2
            load_node = pipeline.nodes[0]
            assert load_node.config.get("input") == "data.csv"
            clean_node = pipeline.nodes[1]
            assert clean_node.depends_on == ["load_data"]
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_execute_simple_pipeline(self, engine, sample_csv):
        pipeline = DAGPipeline(
            name="test",
            nodes=[
                DAGNode(node_id="load", node_type=DAGNodeType.LOAD, config={"input": sample_csv}),
                DAGNode(node_id="profile", node_type=DAGNodeType.PROFILE, depends_on=["load"]),
                DAGNode(node_id="score", node_type=DAGNodeType.SCORE, depends_on=["profile"]),
            ],
        )

        result = engine.execute(pipeline)
        assert result.success
        assert result.nodes_executed == 3
        assert result.nodes_failed == 0

    def test_execute_clean_pipeline(self, engine, sample_csv):
        pipeline = DAGPipeline(
            name="clean_test",
            nodes=[
                DAGNode(node_id="load", node_type=DAGNodeType.LOAD, config={"input": sample_csv}),
                DAGNode(node_id="clean", node_type=DAGNodeType.CLEAN, depends_on=["load"]),
            ],
        )

        result = engine.execute(pipeline)
        assert result.success
        clean_result = result.node_results["clean"].result
        assert clean_result is not None

    def test_missing_input_file(self, engine):
        pipeline = DAGPipeline(
            name="fail_test",
            nodes=[
                DAGNode(node_id="load", node_type=DAGNodeType.LOAD, config={"input": "nonexistent.csv"}),
            ],
        )

        result = engine.execute(pipeline)
        assert not result.success
        assert result.nodes_failed == 1
        assert result.node_results["load"].status == DAGNodeStatus.FAILED

    def test_circular_dependency_detection(self, engine):
        pipeline = DAGPipeline(
            name="circular",
            nodes=[
                DAGNode(node_id="a", node_type=DAGNodeType.PROFILE, depends_on=["b"]),
                DAGNode(node_id="b", node_type=DAGNodeType.PROFILE, depends_on=["a"]),
            ],
        )

        with pytest.raises(ValueError, match="循环依赖"):
            engine.execute(pipeline)

    def test_custom_executor_registration(self, engine):
        def custom_exec(ctx, node):
            return {"custom": True}

        engine.register_executor(DAGNodeType.EXPORT, custom_exec)
        pipeline = DAGPipeline(
            name="custom",
            nodes=[DAGNode(node_id="e", node_type=DAGNodeType.EXPORT, config={"output": "test.csv"})],
        )
        # 自定义 executor 不需要 df, 应该成功
        result = engine.execute(pipeline)
        assert result.success
        assert result.node_results["e"].result == {"custom": True}

    def test_run_pipeline_from_file(self, engine, sample_csv):
        config = {
            "pipeline": {
                "name": "from_file",
                "steps": [
                    {"type": "load", "config": {"input": sample_csv}},
                    "profile",
                    "score",
                ],
            }
        }
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as f:
            yaml.dump(config, f)
            f_path = f.name

        try:
            result = engine.run_pipeline(f_path)
            assert result.success
            assert result.nodes_executed == 3
        finally:
            Path(f_path).unlink(missing_ok=True)


class TestTopologicalSort:
    """拓扑排序测试."""

    def test_linear_chain(self):
        engine = DAGEngine()
        nodes = [
            DAGNode(node_id="a", node_type=DAGNodeType.PROFILE),
            DAGNode(node_id="b", node_type=DAGNodeType.PROFILE, depends_on=["a"]),
            DAGNode(node_id="c", node_type=DAGNodeType.PROFILE, depends_on=["b"]),
        ]
        sorted_nodes = engine._topological_sort(nodes)
        ids = [n.node_id for n in sorted_nodes]
        assert ids == ["a", "b", "c"]

    def test_diamond_dependency(self):
        engine = DAGEngine()
        nodes = [
            DAGNode(node_id="a", node_type=DAGNodeType.PROFILE),
            DAGNode(node_id="b", node_type=DAGNodeType.PROFILE, depends_on=["a"]),
            DAGNode(node_id="c", node_type=DAGNodeType.PROFILE, depends_on=["a"]),
            DAGNode(node_id="d", node_type=DAGNodeType.PROFILE, depends_on=["b", "c"]),
        ]
        sorted_nodes = engine._topological_sort(nodes)
        ids = [n.node_id for n in sorted_nodes]
        assert ids[0] == "a"
        assert ids[3] == "d"
