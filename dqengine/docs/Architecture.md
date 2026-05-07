# DQEngine 系统架构

## 架构演进

```
Phase 1 (v0.1.0)          Phase 2 (v0.2.0)          Phase 3 (v0.3.0)
┌─────────────┐      ┌───────────────────┐      ┌──────────────────────────┐
│  CLI        │      │  CLI + 6 modules  │      │  CLI + 14 modules        │
│  Core       │  →   │  Semantic         │  →   │  AI / Drift / Monitor    │
│  Repair     │      │  Batch / Pipeline  │      │  API / Orchestrator      │
│  Rules      │      │  Plugin / Registry │      │  Realtime / Metadata     │
│  Report     │      │  Service / Config  │      │  Scheduler / Observability│
│             │      │                    │      │  Domain / Application    │
│             │      │                    │      │  Infrastructure / Container│
└─────────────┘      └───────────────────┘      └──────────────────────────┘
```

## 分层架构

```
┌─────────────────────────────────────────────────────┐
│                    CLI / API Layer                   │
│        (Typer Commands / FastAPI Endpoints)         │
├─────────────────────────────────────────────────────┤
│                Application Layer                     │
│        (Use Cases: AutoClean, Drift, Monitor)       │
├─────────────────────────────────────────────────────┤
│                   Domain Layer                       │
│     (Entities: Dataset, QualityRule, Governance)    │
├──────────┬──────────┬──────────┬───────────────────┤
│   Core   │  Repair  │  Rules   │   AI / Drift      │
│  Loader  │  Missing │Validator │  RuleGenerator    │
│ Profiler │  Dup     │          │  DriftDetector    │
│  Scorer  │  Date    │          │                   │
├──────────┼──────────┼──────────┼───────────────────┤
│ Semantic │  Batch   │Pipeline  │   Monitoring      │
│Detector  │Processor │Generator │  QualityMonitor   │
├──────────┼──────────┼──────────┼───────────────────┤
│  Plugin  │ Registry │  Report  │   Orchestrator    │
│  Base    │ Plugin   │Generator │   DAGEngine       │
│          │ Pattern  │Advanced  │                   │
├──────────┴──────────┴──────────┴───────────────────┤
│              Infrastructure Layer                    │
│   (Storage: SQLite/DuckDB, Cache: Memory/Redis)     │
├─────────────────────────────────────────────────────┤
│              Container (DI) / Models                 │
│   ServiceContainer / Pydantic Schemas               │
└─────────────────────────────────────────────────────┘
```

## 模块依赖图

```
  cli ──────────────┐
   │                │
   ├── ai ──────────┤
   ├── drift ───────┤
   ├── monitoring ──┤
   ├── api ─────────┤
   ├── orchestrator─┤
   ├── realtime ────┤
   ├── metadata ────┤
   ├── scheduler ───┤
   ├── observability┤
   │                │
   ├── core ────────┤
   ├── repair ──────┤
   ├── rules ───────┤
   ├── report ──────┤
   ├── semantic ────┤
   │                │
   ├── domain ──────┤
   ├── application ─┤
   ├── infrastructure┤
   └── container ───┘
```

## 核心设计原则

1. **插件化**: 通过 ABC 基类 + Plugin Registry 实现可扩展的验证器/清洗器/评分器
2. **配置驱动**: YAML 配置文件 + Pydantic 模型验证
3. **分离关注点**: Domain / Application / Infrastructure 三层分离
4. **Provider 模式**: AI / Cache / Storage 均支持多 Provider 可替换
5. **向后兼容**: 所有 Phase 1/2 的 CLI 命令和 API 保持不变
