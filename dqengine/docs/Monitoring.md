# DQEngine 质量监控指南

## 概述

持续数据质量监控系统自动监听数据目录，对新文件执行画像、评分和漂移检测，记录历史趋势。

## CLI 使用

```bash
# 基本监控
dq monitor ./incoming_data

# 指定扫描间隔
dq monitor ./incoming_data -i 60

# 启用漂移检测
dq monitor ./incoming_data -b baseline.csv

# 生成监控报告
dq monitor ./incoming_data -r monitoring_report.html
```

## 监控模式

### 1. 轮询模式 (默认)

定期扫描目录，处理新文件。支持 `watchdog` 库自动切换为实时监听模式。

### 2. Watchdog 模式

```bash
pip install watchdog
dq monitor ./data  # 自动使用 watchdog 实时监听
```

## 质量趋势

监控自动记录历史质量趋势 (JSON)：
- 文件级评分变化
- 空值率趋势
- 重复率趋势
- 行数变化

趋势数据保存在 `quality_trends.json`。

## 告警规则

监控自动触发告警：
- **低质量**: 评分 < 60
- **漂移告警**: 基线对比检测到漂移 (severity >= medium)

## Python API

```python
from dqengine.monitoring.monitor import QualityMonitor

# 创建监控器
monitor = QualityMonitor(
    watch_directory="./data",
    baseline_file="baseline.csv",
)

# 注册事件回调
def on_new_file(event):
    print(f"处理: {event.file_path}, 评分: {event.score.overall_score}")

monitor.on_event(on_new_file)

# 开始监控
monitor.start_polling(interval_seconds=30)

# 获取趋势
trends = monitor.get_trends(hours=24)
for t in trends:
    print(f"{t.file_name}: {t.overall_score:.1f}")

# 生成报告
monitor.generate_trends_html("monitoring_report.html")
```

## 监控报告

HTML 报告包含：
- 质量评分趋势图 (Plotly)
- 空值率双轴图
- 近期告警列表
- 处理文件统计
