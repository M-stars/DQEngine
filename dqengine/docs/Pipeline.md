# DQEngine Pipeline 编排指南

## 概述

DAG Pipeline Engine 允许将数据治理流程编排为有向无环图 (DAG)，支持依赖管理和并行执行。

## Pipeline YAML 格式

### 简单模式

```yaml
pipeline:
  name: "基础治理流水线"
  steps:
    - load
    - profile
    - validate
    - clean
    - score
    - report
```

### 高级模式 (带依赖和配置)

```yaml
pipeline:
  name: "高级治理流水线"
  description: "加载 → 画像 → 清洗 → 评分 → 语义 → 报告"
  steps:
    - type: load
      id: load_data
      config:
        input: data.csv

    - type: profile
      id: profile_data
      depends_on:
        - load_data

    - type: clean
      id: clean_data
      depends_on:
        - profile_data

    - type: score
      id: score_data
      depends_on:
        - clean_data

    - type: semantic
      id: analyze_data
      depends_on:
        - clean_data

    - type: report
      id: generate_report
      depends_on:
        - score_data
        - analyze_data
      config:
        output: "pipeline_report.html"
        format: html
```

## 可用节点类型

| 类型 | 描述 | 必需参数 |
|------|------|---------|
| `load` | 加载数据 | `config.input` |
| `profile` | 数据画像 | - |
| `validate` | 规则验证 | `config.rules` (可选) |
| `clean` | 自动清洗 | - |
| `score` | 质量评分 | - |
| `semantic` | 语义分析 | - |
| `report` | 报告生成 | `config.output` (可选) |
| `drift` | 漂移检测 | `config.baseline`, `config.current` |
| `export` | 导出数据 | `config.output`, `config.format` |

## CLI 使用

```bash
# 运行 Pipeline
dq run-pipeline pipeline.yaml

# 指定输入文件
dq run-pipeline pipeline.yaml -i data.csv

# 保存执行结果
dq run-pipeline pipeline.yaml -o result.json
```

## Python API

```python
from dqengine.orchestrator.engine import DAGEngine

engine = DAGEngine()
result = engine.run_pipeline("pipeline.yaml", input_file="data.csv")
print(f"Success: {result.success}")
print(f"Duration: {result.total_duration_ms}ms")
```

## 自定义节点执行器

```python
from dqengine.models.schemas import DAGNodeType
from dqengine.orchestrator.engine import DAGEngine

def my_custom_exec(ctx, node):
    df = ctx["dataframe"]
    # 自定义逻辑
    return {"rows": len(df)}

engine = DAGEngine()
engine.register_executor(DAGNodeType.EXPORT, my_custom_exec)
```
