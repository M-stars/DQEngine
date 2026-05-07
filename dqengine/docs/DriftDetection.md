# DQEngine 数据漂移检测指南

## 概述

数据漂移检测系统自动比较两个数据集版本，识别四种类型的漂移：

1. **Schema Drift** - 列增删、数据类型变化
2. **Distribution Drift** - 数值分布变化 (KS Test)
3. **Null Drift** - 空值率变化
4. **Category Drift** - 分类值分布变化 (PSI)

## CLI 使用

```bash
# 基本使用
dq drift baseline.csv current.csv

# 指定输出文件
dq drift baseline.csv current.csv --html drift_report.html --output drift_summary.json
```

## 漂移严重度

| 级别 | 说明 |
|------|------|
| `none` | 无漂移 |
| `low` | 轻微变化 |
| `medium` | 中等变化, 需关注 |
| `high` | 显著变化, 需要处理 |
| `critical` | 严重变化, 立即处理 |

## 检测阈值

### KS Test (分布漂移)

| 统计值 | 严重度 |
|--------|--------|
| < 0.10 | low |
| 0.10 - 0.20 | medium |
| 0.20 - 0.30 | high |
| >= 0.30 | critical |

### PSI (分类漂移)

| 值 | 严重度 |
|----|--------|
| < 0.10 | low |
| 0.10 - 0.20 | medium |
| 0.20 - 0.30 | high |
| >= 0.30 | critical |

### 空值率变化

| 变化量 | 严重度 |
|--------|--------|
| < 5% | low |
| 5% - 15% | medium |
| 15% - 30% | high |
| >= 30% | critical |

## Python API

```python
from dqengine.drift.detector import DriftDetector

detector = DriftDetector()

# 执行检测
report = detector.detect("baseline.csv", "current.csv")

# 分析结果
print(f"漂移列数: {report.drifted_columns}")
print(f"整体严重度: {report.overall_severity}")

# 查看 Schema 漂移
for d in report.schema_drift:
    print(f"  {d.column_name}: {d.description}")

# 生成报告
detector.generate_html_report(report, "drift_report.html")
detector.save_summary_json(report, "drift_summary.json")
```

## 监控集成

漂移检测可与监控系统集成：

```python
from dqengine.monitoring.monitor import QualityMonitor

monitor = QualityMonitor(
    watch_directory="./incoming",
    baseline_file="baseline.csv",  # 启用漂移检测
)
monitor.start_polling(interval_seconds=300)
```
