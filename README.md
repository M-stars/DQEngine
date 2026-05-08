# DQEngine

<p align="center">
  <strong>轻量级、自动化、开发者友好的数据质量治理框架</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.3.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/python-≥3.9-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://github.com/M-stars/DQEngine/actions/workflows/ci.yml/badge.svg" alt="CI">
</p>

---

## 简介

**DQEngine** 是一个轻量级的数据质量治理框架，提供从数据分析、清洗、验证到报告生成的全链路能力。

- **CLI 即用**：一条命令完成数据质量治理，无需复杂配置
- **可扩展**：热插拔插件架构 + 语义引擎 + 自定义规则
- **多数据源**：CSV / Excel / JSON / Parquet / SQLite 自动识别
- **多格式报告**：HTML（含 Plotly 图表）/ JSON / Markdown
- **可编程**：完整的 Python API，可嵌入 Jupyter Notebook、Airflow DAG 或任何 Python 项目

## 快速开始

### 安装

```bash
# 进入项目目录后执行

# 基础安装
pip install -e .

# 带开发依赖
pip install -e ".[dev]"

# 完整安装（含数据库、API、监控、调度）
pip install -e ".[all]"
```

### 30 秒体验

```bash
# 分析数据质量
dq profile examples/sample.csv

# 一键自动清洗
dq auto examples/sample.csv -o cleaned.csv -r report.html

# 语义识别字段类型
dq semantic examples/sample.csv

# 规则验证
dq validate examples/sample.csv --rules configs/rules.yaml

# 环境诊断
dq doctor
```

## CLI 命令参考

| 命令 | 说明 |
|------|------|
| `dq profile <file>` | 数据画像 — 字段统计、空值率、分布分析 |
| `dq auto <file>` | 自动清洗 — 缺失值/重复值/日期/异常值一键修复 |
| `dq validate <file>` | 规则验证 — YAML 驱动的数据质量规则检查 |
| `dq semantic <file>` | 语义识别 — 自动识别字段类型（邮箱/电话/日期...） |
| `dq batch <dir>` | 批量处理 — 并发治理目录中所有数据文件 |
| `dq pipeline <file>` | 导出 Pipeline — 生成可重复执行的 Python 清洗脚本 |
| `dq drift <baseline> <current>` | 漂移检测 — Schema/分布/空值率/分类四种漂移 |
| `dq monitor <dir>` | 质量监控 — 持续监控目录数据质量变化 |
| `dq stream-validate <file>` | 实时流验证 — 逐事件验证数据流 |
| `dq schedule <config>` | 任务调度 — Cron/Interval 定时执行治理任务 |
| `dq ai generate-rules <file>` | AI 规则生成 — 自动推断数据质量规则 |
| `dq run-pipeline <file>` | DAG 编排 — 执行多步骤 Pipeline 工作流 |
| `dq serve` | API 服务 — 启动 REST API 服务器 (FastAPI) |
| `dq plugins` | 插件管理 — 查看已加载的插件列表 |
| `dq doctor` | 环境诊断 — 检查依赖和配置状态 |
| `dq version` | 版本信息 |

### 常用选项

```bash
--config, -c     # 指定配置文件 (YAML)
--output, -o     # 输出路径
--workers, -w    # 并发数 (batch 命令)
--verbose, -v    # 详细输出
--help           # 查看命令帮助
```

## Python API

所有 CLI 功能均可在代码中直接调用：

```python
from dqengine.core.loader import DataLoader
from dqengine.core.profiler import Profiler
from dqengine.core.scorer import QualityScorer
from dqengine.repair.missing_value import MissingValueCleaner
from dqengine.repair.duplicate import DuplicateCleaner
from dqengine.repair.outlier import OutlierDetector
from dqengine.rules.validator import RuleValidator
from dqengine.semantic.detector import SemanticDetector
from dqengine.report.generator import ReportGenerator
from dqengine.services.orchestrator import CleaningOrchestrator
from dqengine.models.schemas import AppConfig

# 加载数据
loader = DataLoader()
df = loader.load("data.csv")

# 数据画像
profiler = Profiler()
profile = profiler.profile(df, file_path="data.csv")

# 质量评分
scorer = QualityScorer()
score = scorer.score(df, profile)
print(f"评分: {score.overall_score:.1f}/100 ({score.grade})")

# 缺失值填充
mv_cleaner = MissingValueCleaner()
df, result = mv_cleaner.clean(df)

# 去重
dup_cleaner = DuplicateCleaner()
df, result = dup_cleaner.clean(df, keep="first")

# 异常值检测
outlier_detector = OutlierDetector()
outliers = outlier_detector.detect(df)

# 语义识别
detector = SemanticDetector()
semantic_result = detector.detect(df)

# 规则验证
validator = RuleValidator()
val_result = validator.validate(df, "configs/rules.yaml")

# 报告生成
report_gen = ReportGenerator()
report_gen.generate(profile, score, repairs, outliers, output_path="report.html")

# 一键编排
orchestrator = CleaningOrchestrator()
result = orchestrator.run("dirty_data.csv", output_path="clean.csv")
```

> 详细 API 文档和完整示例参见 [docs/DQEngine使用教程.md](docs/DQEngine使用教程.md)

## 配置指南

### 创建配置文件

```bash
cp configs/default.yaml my_config.yaml
```

### 配置结构

```yaml
cleaning:
  missing:
    strategy: median        # mean / median / mode / drop / constant
  duplicate:
    enabled: true
    keep: first
  outlier:
    method: iqr             # iqr / zscore
    threshold: 1.5
    action: remove          # flag / remove
  date:
    target_format: "%Y-%m-%d"

report:
  formats:
    - html
    - json
    - markdown
  output_dir: reports
  include_charts: true

semantic_enabled: true
plugins_dir: plugins
log_level: INFO
```

### 使用配置

```bash
dq auto data.csv --config my_config.yaml
dq batch ./datasets --config my_config.yaml
```

## 插件开发

将自定义插件放入 `plugins/` 目录即可自动加载。

### 验证器

```python
from dqengine.plugins.base import BaseValidator
from dqengine.models.schemas import PluginInfo, PluginType, RuleViolation

class MyValidator(BaseValidator):
    PLUGIN_INFO = PluginInfo(
        name="my_validator",
        plugin_type=PluginType.VALIDATOR,
        version="0.1.0",
        description="自定义验证器",
    )

    def validate(self, df, column):
        violations = []
        for idx, val in df[column].items():
            if not self._is_valid(val):
                violations.append(RuleViolation(
                    column=column, rule_type="custom",
                    row_index=int(idx), value=str(val),
                    message=f"验证失败: {val}",
                ))
        return violations
```

### 清洗器

```python
from dqengine.plugins.base import BaseCleaner
from dqengine.models.schemas import PluginInfo, PluginType, RepairResult

class MyCleaner(BaseCleaner):
    PLUGIN_INFO = PluginInfo(
        name="my_cleaner",
        plugin_type=PluginType.CLEANER,
        description="自定义清洗器",
    )

    def clean(self, df, column=None):
        df_clean = df.copy()
        # 自定义清洗逻辑
        return df_clean, RepairResult(
            operation="my_cleaner",
            rows_before=len(df), rows_after=len(df_clean),
            columns_affected=1, changes_made=10,
        )
```

```bash
# 查看已加载插件
dq plugins
dq plugins --type validator
```

## API 服务

```bash
# 安装依赖
pip install fastapi uvicorn python-multipart

# 启动服务
dq serve

# 访问文档
# Swagger UI: http://localhost:8000/docs
# Redoc:     http://localhost:8000/redoc
```

API 端点：

| 方法 | 路径 | 功能 |
|------|------|------|
| `POST` | `/profile` | 数据画像 |
| `POST` | `/validate` | 规则验证 |
| `POST` | `/clean` | 自动清洗 |
| `POST` | `/semantic` | 语义分析 |
| `POST` | `/drift` | 漂移检测 |
| `POST` | `/report` | 报告生成 |
| `GET` | `/health` | 健康检查 |

## 项目结构

```
DQEngine/
├── dqengine/
│   ├── cli/              # CLI 命令层 (Typer + Rich)
│   ├── core/             # 核心引擎 — 加载器 / 画像 / 评分
│   ├── models/           # 数据模型 (Pydantic)
│   ├── repair/           # 数据修复 — 缺失值 / 重复值 / 日期 / 异常值
│   ├── semantic/         # 语义引擎 — 字段类型自动识别
│   ├── batch/            # 批处理 — 并发治理
│   ├── pipeline/         # Pipeline — 代码自动生成
│   ├── plugins/          # 插件系统 — 基类 / 注册中心
│   ├── registry/         # 注册中心 — 语义模式 / 插件
│   ├── services/         # 服务层 — 编排器 / 配置管理
│   ├── rules/            # 规则引擎 — YAML 驱动验证
│   ├── report/           # 报告生成 — HTML / JSON / Markdown
│   ├── ai/               # AI 辅助 — 规则自动生成
│   ├── api/              # REST API — FastAPI 服务
│   ├── drift/            # 漂移检测 — KS Test / PSI
│   ├── monitoring/       # 质量监控 — 目录监控
│   ├── realtime/         # 实时验证 — 流式数据
│   ├── scheduler/        # 任务调度 — Cron / Interval
│   ├── orchestrator/     # DAG 编排 — 多步骤工作流
│   ├── metadata/         # 元数据 — 数据血缘
│   ├── observability/    # 可观测性 — 指标 / 追踪
│   ├── application/      # 应用层 — 用例
│   ├── domain/           # 领域层 — 实体
│   ├── infrastructure/   # 基础设施 — 缓存 / 存储
│   ├── container/        # 依赖注入容器
│   └── utils/            # 工具 — 控制台 / 日志
│
├── configs/
│   ├── rules.yaml        # 验证规则示例
│   └── default.yaml      # 默认配置
│
├── docs/
│   └── DQEngine使用教程.md
│
├── tests/                # 测试
├── pyproject.toml        # 项目配置
└── README.md
```

## 测试

```bash
# 运行所有测试
pytest tests/ -v

# 带覆盖率
pytest tests/ --cov=dqengine --cov-report=term-missing

# 特定模块
pytest tests/test_semantic.py -v
pytest tests/test_plugins.py -v
pytest tests/test_integration.py -v
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 代码格式化
black dqengine/ tests/ --line-length=100
isort dqengine/ tests/ --profile=black
ruff check dqengine/ tests/

# 类型检查
mypy dqengine/

# Pre-commit
pre-commit install
```



---

<p align="center">
  <strong>DQEngine</strong> — 让数据治理像写代码一样优雅
</p>
