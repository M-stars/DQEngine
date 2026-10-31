# DQEngine

<p align="center">
  <strong>轻量级、自动化、开发者友好的数据质量治理框架</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.1.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/python-≥3.9-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://github.com/M-stars/DQEngine/actions/workflows/ci.yml/badge.svg" alt="CI">
</p>

---

## 简介

**DQEngine** 是一个轻量级的数据质量治理框架，提供从数据分析、清洗、验证到报告生成的全链路能力。

- **CLI 即用**：一条命令完成数据质量治理，无需复杂配置
- **可扩展**：热插拔插件架构 + 语义引擎 + 自定义规则
- **多数据源**：CSV / Excel / JSON / Parquet / SQLite 自动识别；数据库连接串由连接器插件接入（PostgreSQL / MySQL / SQLite 等）
- **可选分布式**：执行后端插件（Dask）将批处理与规则验证扇出到本地进程集群或外部集群，核心保持单机轻量
- **多格式报告**：HTML（含 Plotly 图表）/ JSON / Markdown
- **可编程**：完整的 Python API，可嵌入 Jupyter Notebook、Airflow DAG 或任何 Python 项目

## 快速开始

### 安装

```bash
# 进入项目目录后执行

# 基础安装（轻量, 不含数据库/分布式）
pip install -e .

# 可选能力按需安装
pip install -e ".[db]"          # SQL 连接器 (sqlalchemy, SQLite 零驱动可用)
pip install -e ".[postgres]"    # PostgreSQL 驱动
pip install -e ".[mysql]"       # MySQL / MariaDB 驱动
pip install -e ".[clickhouse]"  # ClickHouse 方言
pip install -e ".[hive]"        # Hive / Spark(Thrift Server) / Presto / Trino 方言
pip install -e ".[mongo]"       # MongoDB 连接器
pip install -e ".[kafka]"       # Kafka 连接器
pip install -e ".[dask]"        # Dask 分布式执行后端

# 带开发依赖
pip install -e ".[dev]"

# 完整安装（含全部数据源、分布式、API、监控、调度）
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
| `dq profile <file>` | 数据画像 — 字段统计、空值率、分布分析；支持 `--table` / `--query` 连接串取数 |
| `dq auto <file>` | 自动清洗 — 缺失值/重复值/日期/异常值一键修复；支持 `--table` / `--query` 连接串取数 |
| `dq validate <file>` | 规则验证 — YAML 驱动的数据质量规则检查；`--distributed` 分区分片并行验证 |
| `dq semantic <file>` | 语义识别 — 自动识别字段类型（邮箱/电话/日期...） |
| `dq batch <dir>` | 批量处理 — 并发治理目录中所有数据文件；`--backend dask` 分布式扇出 |
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

## 数据库源与分布式执行（可选插件）

数据库连接器和分布式执行后端都是**热插拔插件**：依赖按需安装、懒加载，未安装时核心功能完全不受影响。用 `dq plugins` 查看已加载的插件，`dq doctor` 检查可选依赖状态。

### 数据库连接器

| 数据源 | scheme | extra | 取数语义 |
|--------|--------|-------|----------|
| PostgreSQL | `postgresql://` | `postgres` | 表 / SQL 查询 |
| MySQL / MariaDB | `mysql://` | `mysql` | 表 / SQL 查询 |
| ClickHouse | `clickhouse://` / `clickhousedb://` | `clickhouse` | 表 / SQL 查询 |
| Hive / Spark(Thrift) | `hive://` / `spark://` | `hive` | 表 / SQL 查询 |
| Presto / Trino | `presto://` / `trino://` | —（自装 PyHive / trino） | 表 / SQL 查询 |
| SQLite | `sqlite:///` | 无需驱动 | 表 / SQL 查询 |
| MongoDB | `mongodb://` | `mongo` | collection + JSON 过滤 |
| Kafka | `kafka://broker/topic` | `kafka` | 消费 topic 消息 |

```bash
# SQL 库: 表模式 / 查询模式 (优先于 --table; 大结果集请自行加 LIMIT)
dq profile "postgresql://user:pass@host:5432/mydb" --table users
dq validate "mysql://user:pass@host/mydb" \
    --query "SELECT * FROM orders WHERE dt = '2026-10-31'" \
    --rules configs/rules.yaml --json
dq profile "postgresql://..." --table events --limit 100000

# ClickHouse / Hive 同一套用法
dq profile "clickhouse://user:pass@host:8123/ods" --table events
dq profile "hive://nn:10000/ods" --table dwd_orders

# MongoDB: --table = collection, --query = JSON 过滤条件 (嵌套文档自动展平)
dq profile "mongodb://user:pass@host:27017/appdb" --table users --query '{"age": {"$gt": 18}}'

# Kafka: 消费 topic 至多 --limit 条消息 (缺省 1000, JSON 展平/原文入 value 列)
dq profile "kafka://broker1:9092,broker2:9092/orders" --limit 5000

# 自动清洗同样支持
dq auto "sqlite:///warehouse.db" --table users -o cleaned.csv
```

- 连接串密码在日志中始终脱敏；SQL 表名经 SQLAlchemy 元数据反射参数化，无拼接注入面
- Kafka 取数是数据质量检查视角（近期消息画像/验证），不是全量回放工具
- 自定义数据源（HDFS、S3...）：编写 `BaseConnector` 插件（声明 `SCHEMES`）放入 `plugins/` 目录即可，`DataLoader` 会按 URI scheme 自动路由

### 分布式执行

```bash
# 批处理文件扇出到本地进程集群 (绕开 GIL)
dq batch ./datasets --backend dask

# 连接外部 Dask 集群
DQENGINE_DASK_SCHEDULER="tcp://cluster:8786" dq batch ./datasets --backend dask

# 大文件分区分片验证 (与单机验证结果完全一致, 行号全局对齐)
dq validate big_table.csv --rules rules.yaml --distributed --npartitions 8
```

- 4 种规则（range / regex / not_null / allowed_values）均为行级语义，分区分片结果与单机对拍一致；列级违规按规则去重
- `--distributed` 只在申请违规隔离区时才回读全量数据
- 清洗（`auto`）不做分布式：去重与异常值阈值依赖全局统计，强做分片会静默出错
- 外部集群 worker 需能 `import dqengine`，并可通过共享路径访问输入/输出文件

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

> 详细文档参见 [dqengine/docs/](dqengine/docs/)（API、架构、漂移检测、监控、Pipeline、插件开发）

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

### 连接器（自定义数据源）

声明 `SCHEMES` 后，`dq <命令> "myscheme://..."` 会自动路由到该插件。
可选依赖一律在方法内懒加载，不要放在模块顶层。

```python
from typing import Optional
import pandas as pd
from dqengine.plugins.base import BaseConnector
from dqengine.models.schemas import PluginInfo, PluginType

class MyConnector(BaseConnector):
    PLUGIN_INFO = PluginInfo(
        name="my_connector",
        plugin_type=PluginType.LOADER,
        description="自定义数据源连接器",
    )
    SCHEMES = ("myscheme",)

    def load(self, uri, table=None, query=None, **kwargs):
        return pd.DataFrame({"col": [1, 2]})  # 实际从数据源读取
```

### 执行后端（自定义分布式）

实现 `map`（任务扇出，保序返回）与 `map_partitions`
（分区分片，签名 `fn(partition, row_offset)`）两个方法即可接入
`dq batch --backend` 与 `dq validate --distributed`。

```python
from typing import Any, Callable, List, Sequence
from dqengine.plugins.base import BaseBackend
from dqengine.models.schemas import PluginInfo, PluginType

class MyBackend(BaseBackend):
    PLUGIN_INFO = PluginInfo(
        name="my_backend",
        plugin_type=PluginType.BACKEND,
        description="自定义执行后端",
    )
    NAME = "my_backend"

    def map(self, fn: Callable, items: Sequence[Any]) -> List[Any]:
        return [fn(x) for x in items]  # 替换为并行/分布式实现

    def map_partitions(self, source, npartitions, fn, merge, **kwargs):
        parts = ...  # 切分数据源
        return merge([fn(p, i * len_p) for i, p in enumerate(parts)])
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
| `GET` | `/metrics` | Prometheus 指标 |

## 生产部署

### API 服务（带鉴权与监控）

```bash
# 启用 API Key 鉴权（未设置时实例保持开放，启动日志会明确告警）
export DQENGINE_API_KEY="your-secret-key"

# Prometheus 抓取 /metrics；健康检查走 /health（均免鉴权）
dq serve --host 0.0.0.0 --port 8000

# 带 CORS 的开发模式
dq serve --reload
```

客户端在请求头携带 `X-API-Key: your-secret-key`。

```bash
# Nginx 反向代理示例
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
}
```

### 监控与告警投递

```bash
# 告警实时 POST 到 Webhook（兼容钉钉/企业微信/Slack 网关或自建接收端）
export DQENGINE_WEBHOOK_URL="https://oapi.dingtalk.com/robot/send?access_token=xxx"
dq monitor ./incoming_data -i 30 -b baseline.csv --report trend.html
```

告警载荷为 JSON，`text` 字段可直接被常见 IM 网关消费：

```json
{"text": "低质量告警 [data.csv]: 评分 36.5", "session_id": "a1b2c3d4"}
```

### 定时调度（重启安全）

```python
from dqengine.scheduler.scheduler import TaskScheduler
from dqengine.models.schemas import ScheduledTask, ScheduleType

scheduler = TaskScheduler(state_file="schedule_state.json")  # 状态持久化
scheduler.add_task(ScheduledTask(
    task_id="nightly", name="每夜画像",
    schedule_type=ScheduleType.CRON, schedule_value="0 3 * * *",
    action="profile", target_path="/data/daily/",
))
scheduler.start(blocking=True)  # 重启后自动恢复 next_run，CRON 不会立即重跑
```

长驻进程建议用 systemd/supervisor 托管，日志输出已全部走结构化
logger（`logs/dqengine.log`，自动轮转）。

### CI 数据质量门禁

```yaml
# GitHub Actions: 数据变更时执行质量门禁
- name: Data quality gate
  run: |
    dq validate data/ --rules configs/rules.yaml --json > dq_result.json
    # 退出码: 0=通过, 1=有违规; 违规行同时落入隔离区供人工复核
    dq validate data/ --rules configs/rules.yaml --quarantine quarantine/
```

清洗管线同样支持门禁：`dq auto data.csv --fail-below-score 80`
（清洗后评分低于 80 时退出码 2）。

### 违规隔离区

`validate --quarantine` 将违规行（去重）导出为 CSV 并附加
`dqengine_violations` 摘要列——坏数据进入隔离区供人工复核，
而不是混在结果里或被静默丢弃。

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
│   ├── default.yaml          # 默认配置
│   ├── rules.yaml            # 验证规则示例
│   ├── pipeline.yaml         # Pipeline 编排配置
│   └── schedule_config.yaml  # 调度配置
│
├── docs/                 # 模块文档 (API/架构/漂移/监控/Pipeline/插件)
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

## Roadmap

- [x] 数据血缘可视化 (血缘图 HTML 生成)
- [x] Docker 容器化部署 (Dockerfile + docker-compose)
- [x] Spark 数据源连接器 (Thrift Server)
- [x] LLM 集成 (自然语言规则生成 / 智能修复建议)
- [ ] Web Dashboard — 数据质量监控面板
- [ ] PostgreSQL 深度集成 (存储层)
- [ ] Redis 缓存层

完整路线图见 [dqengine/README.md](dqengine/README.md)。

## 贡献

欢迎提交 Issue 和 Pull Request。确保代码通过：

```bash
pytest tests/ -v
black dqengine/ tests/ --line-length=100 --check
ruff check dqengine/ tests/
```

## License

MIT License

---

<p align="center">
  <strong>DQEngine</strong> — 让数据治理像写代码一样优雅
</p>
