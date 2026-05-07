<p align="center">
  <h1 align="center">DQEngine</h1>
  <p align="center">
    <strong>AI-Driven Data Quality Platform — 数据质量智能分析平台</strong>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/version-0.3.0-blue.svg" alt="Version 0.3.0">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT">
  <img src="https://img.shields.io/badge/status-active-brightgreen.svg" alt="Status: Active">
</p>

---

## 概述

**DQEngine** 是一个工程化的 AI 驱动数据质量平台，服务于数据工程师和分析师，提供从数据画像、规则验证、自动修复到漂移检测、实时监控和 API 服务的全链路数据治理能力。

它不仅是一个规则执行器，更是一个**数据质量智能分析系统**。

### 核心能力

| 能力 | 描述 |
|------|------|
| **数据画像** | 列级统计、空值率、唯一性、分布分析 |
| **质量评分** | 多维评分 (完整性/唯一性/有效性) 0-100 |
| **自动修复** | 缺失值填充、去重、日期标准化、异常值检测 |
| **规则验证** | YAML 驱动: range/regex/not_null/allowed_values |
| **AI 规则生成** | 基于统计推断自动生成数据质量规则 |
| **漂移检测** | Schema/分布(KS)/空值/分类(PSI) 四维漂移分析 |
| **持续监控** | 文件监听、增量分析、历史趋势、自动告警 |
| **REST API** | FastAPI 服务, OpenAPI 文档, 异步处理 |
| **Pipeline 编排** | DAG 节点编排, YAML 定义, 拓扑执行 |
| **流式验证** | 实时事件验证, Kafka/WebSocket 接口预留 |
| **数据血缘** | 元数据追踪, 处理步骤记录, 血缘可视化 |
| **任务调度** | Cron/Interval/文件监听, APScheduler |
| **可观测性** | Metrics/Tracing/Execution Logs, Prometheus 接口预留 |
| **插件系统** | 可扩展验证器/清洗器/评分器, 热插拔 |
| **企业架构** | Domain/Application/Infrastructure 分层, DI 容器 |

---

## 快速开始

### 安装

```bash
pip install -e .
```

### 30 秒体验

```bash
# 数据画像
dq profile examples/sample.csv

# 自动清洗
dq auto examples/sample.csv -o cleaned.csv -r report.html

# AI 规则生成
dq ai generate-rules examples/sample.csv

# 漂移检测
dq drift examples/sample.csv examples/sample.csv

# 启动 API 服务
dq serve

# 运行 Pipeline
dq run-pipeline configs/pipeline.yaml -i examples/sample.csv
```

---

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI / API Layer                           │
│        Typer Commands  ·  FastAPI Endpoints                 │
├─────────────────────────────────────────────────────────────┤
│               Application Layer (Use Cases)                  │
│  AutoClean · DriftDetection · QualityMonitor · RuleGeneration│
├─────────────────────────────────────────────────────────────┤
│                  Domain Layer (Entities)                     │
│   Dataset · QualityRule · GovernanceJob · RiskAssessment    │
├──────────┬──────────┬──────────┬────────────────────────────┤
│  Core    │  Repair  │  Rules   │  AI / Drift / Monitor      │
│  Loader  │  MV Fill │Validator │  RuleGenerator             │
│ Profiler │  Dedup   │          │  DriftDetector (KS/PSI)    │
│  Scorer  │  Date Std│          │  QualityMonitor            │
├──────────┼──────────┼──────────┼────────────────────────────┤
│ Semantic │  Batch   │ Pipeline │  Realtime / Metadata       │
│ Detector │Processor │ Generator│  StreamValidator           │
│          │          │  Export  │  LineageTracker            │
├──────────┼──────────┼──────────┼────────────────────────────┤
│ Plugin   │ Registry │  Report  │  Orchestrator / Scheduler  │
│  ABC     │  Plugin  │  HTML    │  DAGEngine                 │
│          │  Pattern │  JSON    │  TaskScheduler             │
├──────────┴──────────┴──────────┴────────────────────────────┤
│            Infrastructure + Container (DI)                   │
│  Storage (SQLite/DuckDB) · Cache (Memory/Redis)             │
│  ServiceContainer · TelemetryManager                       │
└─────────────────────────────────────────────────────────────┘
```

### 设计原则

- **模块化**: 每个模块独立可组合, 低耦合
- **插件化**: ABC 基类 + Registry 实现可扩展
- **配置驱动**: YAML + Pydantic 验证
- **Provider 架构**: AI/Cache/Storage 均支持多 Provider
- **向后兼容**: Phase 1/2 所有命令和 API 保持不变
- **Clean Architecture**: Domain/Application/Infrastructure 分层

---

## CLI 命令全集

### 数据分析
| 命令 | 描述 |
|------|------|
| `dq profile <file>` | 数据画像与统计 |
| `dq auto <file>` | 自动清洗流水线 |
| `dq validate <file> --rules <yaml>` | YAML 规则验证 |

### AI 与语义
| 命令 | 描述 |
|------|------|
| `dq semantic <file>` | 语义类型识别 |
| `dq ai generate-rules <file>` | AI 自动推断规则 |

### 漂移与监控
| 命令 | 描述 |
|------|------|
| `dq drift <baseline> <current>` | 数据漂移检测 |
| `dq monitor <directory>` | 持续质量监控 |

### 编排与调度
| 命令 | 描述 |
|------|------|
| `dq run-pipeline <yaml>` | DAG Pipeline 编排 |
| `dq schedule <config>` | 定时任务调度 |
| `dq stream-validate <json> --rules <yaml>` | 实时流验证 |

### 批量与服务
| 命令 | 描述 |
|------|------|
| `dq batch <dir>` | 批量处理 |
| `dq serve` | 启动 REST API |

### 工具
| 命令 | 描述 |
|------|------|
| `dq plugins` | 插件管理 |
| `dq doctor` | 环境诊断 |
| `dq version` | 版本信息 |

---

## 核心模块详解

### AI 规则生成 (`dq ai generate-rules`)

基于统计推断自动生成数据质量规则:

- **类型规则**: 自动检测列类型 (int/float/str/datetime)
- **范围规则**: IQR 方法推断数值范围
- **正则规则**: 自动识别 email/phone/URL/IP/UUID
- **唯一性规则**: 唯一率分析
- **空值规则**: 空值率评估

多 Provider 架构: `HeuristicRuleGenerator` → `LLMRuleGenerator` (预留 OpenAI/Ollama)

### 漂移检测 (`dq drift`)

四维漂移检测:

| 维度 | 方法 | 阈值 |
|------|------|------|
| Schema | 列增删/类型变化 | - |
| Distribution | KS Test | KS > 0.1 → medium |
| Null Rate | 空值率变化 | Δ > 5% → medium |
| Category | PSI | PSI > 0.1 → medium |

### 持续监控 (`dq monitor`)

- 自动扫描目录中新文件
- 执行画像 → 评分 → 漂移检测
- 历史质量趋势记录 (`quality_trends.json`)
- 自动告警: 低质量 (< 60) / 漂移检测
- 支持 watchdog 实时文件监听

### REST API (`dq serve`)

```bash
POST /profile      # 数据画像
POST /validate     # 规则验证
POST /clean        # 自动清洗
POST /semantic     # 语义分析
POST /drift        # 漂移检测
POST /report       # 报告生成
GET  /health       # 健康检查
GET  /docs         # OpenAPI 文档
```

### Pipeline 编排 (`dq run-pipeline`)

```yaml
pipeline:
  name: "数据质量流水线"
  steps:
    - load
    - profile
    - validate
    - clean
    - score
    - semantic
    - report
```

支持执行器自定义注册和拓扑排序引擎。

---

## 项目结构

```
dqengine/
├── dqengine/                    # 主包
│   ├── __init__.py              # v0.3.0
│   ├── cli/commands.py          # CLI 命令 (17+ 命令)
│   ├── core/                    # 核心引擎 (loader/profiler/scorer)
│   ├── repair/                  # 数据修复 (missing/dup/date/outlier)
│   ├── rules/validator.py       # YAML 规则验证
│   ├── report/                  # HTML/JSON/MD 报告生成
│   ├── semantic/                # 语义分析引擎
│   ├── batch/                   # 批量处理
│   ├── pipeline/                # Pipeline 导出
│   ├── plugins/                 # 插件系统 (ABC + PhoneValidator)
│   ├── registry/                # 插件/模式注册中心
│   ├── services/                # 编排/配置服务
│   ├── utils/                   # Rich 控制台工具
│   ├── models/schemas.py        # Pydantic 数据模型 (50+ 类)
│   ├── ai/generator.py          # AI 规则生成 (Phase 3)
│   ├── drift/detector.py        # 漂移检测 (Phase 3)
│   ├── monitoring/monitor.py    # 持续监控 (Phase 3)
│   ├── api/server.py            # REST API (Phase 3)
│   ├── orchestrator/engine.py   # DAG 编排 (Phase 3)
│   ├── realtime/validator.py    # 流式验证 (Phase 3)
│   ├── metadata/lineage.py      # 血缘追踪 (Phase 3)
│   ├── scheduler/scheduler.py   # 任务调度 (Phase 3)
│   ├── observability/telemetry.py # 可观测性 (Phase 3)
│   ├── domain/entities.py       # 领域实体 (Phase 3)
│   ├── application/use_cases.py # 用例层 (Phase 3)
│   ├── infrastructure/          # 基础设施 (Phase 3)
│   └── container/container.py   # DI 容器 (Phase 3)
├── configs/                     # 配置文件 (YAML)
├── examples/                    # 示例数据
├── tests/                       # 测试套件
├── benchmark/                   # 性能测试
├── docs/                        # 文档
├── Dockerfile                   # Docker 构建
├── docker-compose.yml           # Docker 编排
├── Makefile                     # 开发工具
├── pyproject.toml               # 项目配置
└── README.md
```

---

## 测试

```bash
# 全部测试
pytest tests/ -v

# 覆盖率
pytest tests/ -v --cov=dqengine --cov-report=term-missing

# 性能测试
pytest benchmark/ -v

# 使用 Makefile
make test
make test-cov
```

## Docker

```bash
# 构建
docker build -t dqengine:0.3.0 .

# 运行 API
docker run -p 8000:8000 dqengine:0.3.0

# Docker Compose
docker-compose up -d
```

---

## 技术栈

| 组件 | 技术 |
|------|------|
| CLI | Typer + Rich |
| API | FastAPI + Uvicorn |
| 数据 | Pandas + NumPy + SciPy |
| 模型 | Pydantic v2 |
| 配置 | PyYAML |
| 报告 | Jinja2 + Plotly |
| 存储 | SQLite / DuckDB (PostgreSQL 预留) |
| 缓存 | Memory / Redis (预留) |
| 调度 | APScheduler |
| 容器 | Docker + Docker Compose |
| CI/CD | GitHub Actions |

---

## 路线图

### v0.3.0 (当前) — AI-Driven Platform
- [x] AI 规则生成 (统计推断 + LLM Stub)
- [x] 数据漂移检测 (KS/PSI)
- [x] 持续质量监控 (watchdog + 趋势)
- [x] REST API Server (FastAPI)
- [x] DAG Pipeline 编排引擎
- [x] 实时流式验证
- [x] 元数据与数据血缘
- [x] 任务调度器
- [x] 可观测性系统
- [x] 企业级架构 (Domain/Application/Infrastructure)

### v0.4.0 — LLM Integration
- [ ] OpenAI/Ollama Provider 完整实现
- [ ] 智能修复建议
- [ ] 自然语言规则生成
- [ ] PostgreSQL 存储实现
- [ ] Redis 缓存实现

### v1.0.0 — Enterprise Ready
- [ ] Web Dashboard
- [ ] 多租户支持
- [ ] Kafka 流接入
- [ ] 分布式架构
- [ ] 企业级安全

---

## 贡献

欢迎提交 Issue 和 PR。

## 许可

MIT © DQEngine Team
