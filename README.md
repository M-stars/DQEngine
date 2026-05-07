# DQEngine

<p align="center">
  <strong>轻量级、自动化、开发者友好的数据质量治理框架</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.2.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/python-≥3.9-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://github.com/M-stars/DQEngine/actions/workflows/ci.yml/badge.svg" alt="CI">
  <img src="https://codecov.io/gh/M-stars/DQEngine/branch/main/graph/badge.svg" alt="Coverage">
</p>

---

## 简介

**DQEngine** 是一个轻量级的数据质量治理框架，提供从数据分析、清洗、验证到报告生成的全链路能力。它被设计为：

- **开发者友好**：CLI 即用，无复杂配置
- **可扩展**：插件架构 + 语义引擎
- **自动化**：一键批量治理 + Pipeline 导出
- **专业化**：符合 dbt / Great Expectations 风格的工程实践


## 快速开始

### 安装

```bash
pip install -e .

# 带开发依赖
pip install -e ".[dev]"

# 带数据库支持
pip install -e ".[db]"
```

### 5 分钟体验

```bash
# 1. 分析数据
dq profile examples/sample.csv

# 2. 自动清洗
dq auto examples/sample.csv -o cleaned.csv -r report.html

# 3. 语义识别
dq semantic examples/sample.csv

# 4. 批量治理
dq batch ./examples

# 5. 导出Pipeline
dq pipeline examples/sample.csv

# 6. 查看插件
dq plugins

# 7. 环境诊断
dq doctor

# 8. 规则验证
dq validate examples/sample.csv --rules configs/rules.yaml
```


## 功能模块

### 第一阶段 (MVP) ✓

| 模块 | 说明 |
|------|------|
| CLI | Typer + Rich 命令行界面 |
| 数据分析 (Profile) | 字段统计、质量画像 |
| 质量评分 (Score) | 完整性/唯一性/有效性三维评分 |
| 缺失值治理 | 均值/众数自动填充 |
| 重复值治理 | 自动去重 |
| 日期标准化 | 日期格式统一 YYYY-MM-DD |
| 异常值检测 | IQR 方法检测 |
| 规则验证 | YAML 驱动规则引擎 |
| HTML 报告 | Jinja2 渲染报告 |

### 第二阶段 (当前) ✓

| 模块 | 命令 | 说明 |
|------|------|------|
| **Semantic Engine** | `dq semantic` | 字段语义自动识别 (email/phone/datetime/UUID...) |
| **Batch Processing** | `dq batch` | 批量数据质量治理 (并发 + 进度条) |
| **Pipeline Export** | `dq pipeline` | 自动生成可重复执行的 Python Pipeline |
| **Plugin System** | `dq plugins` | 热插拔插件架构 (Validator/Cleaner/Scorer) |
| **Multi-Datasource** | 自动检测 | CSV / Excel / JSON / Parquet / SQLite |
| **Advanced Reports** | — | JSON / Markdown / HTML + Plotly 图表 |
| **Config-Driven** | `--config` | Pydantic + YAML 配置驱动治理 |
| **Doctor** | `dq doctor` | 环境/依赖/配置/插件诊断 |
| **CI/CD** | — | GitHub Actions + pre-commit hooks |


## 架构

```
DQEngine/
├── dqengine/
│   ├── cli/                    # CLI 命令层
│   │   ├── __init__.py
│   │   └── commands.py         # 所有 CLI 命令
│   │
│   ├── core/                   # 核心引擎层
│   │   ├── __init__.py
│   │   ├── loader.py           # 多数据源加载器
│   │   ├── profiler.py         # 数据画像引擎
│   │   └── scorer.py           # 质量评分引擎
│   │
│   ├── models/                 # 数据模型层 (Pydantic)
│   │   ├── __init__.py
│   │   └── schemas.py          # 所有数据模型定义
│   │
│   ├── repair/                 # 数据修复层
│   │   ├── __init__.py
│   │   ├── missing_value.py    # 缺失值填充
│   │   ├── duplicate.py        # 重复值移除
│   │   ├── date_standardizer.py # 日期标准化
│   │   └── outlier.py          # 异常值检测
│   │
│   ├── semantic/               # 🆕 语义引擎层
│   │   ├── __init__.py
│   │   └── detector.py         # 字段语义检测器
│   │
│   ├── batch/                  # 🆕 批处理层
│   │   ├── __init__.py
│   │   └── processor.py        # 批量治理处理器
│   │
│   ├── pipeline/               # 🆕 Pipeline层
│   │   ├── __init__.py
│   │   └── generator.py        # Pipeline代码生成器
│   │
│   ├── plugins/                # 🆕 插件系统层
│   │   ├── __init__.py
│   │   ├── base.py             # 插件基类
│   │   └── custom_phone_validator.py  # 示例插件
│   │
│   ├── registry/               # 🆕 注册中心层
│   │   ├── __init__.py
│   │   ├── pattern_registry.py # 语义模式注册
│   │   └── plugin_registry.py  # 插件注册
│   │
│   ├── services/               # 🆕 服务编排层
│   │   ├── __init__.py
│   │   ├── orchestrator.py     # 清洗编排器
│   │   └── config_manager.py   # 配置管理器
│   │
│   ├── rules/                  # 规则引擎层
│   │   ├── __init__.py
│   │   └── validator.py        # YAML规则验证器
│   │
│   ├── report/                 # 报告生成层
│   │   ├── __init__.py
│   │   ├── generator.py        # HTML报告生成
│   │   ├── advanced_generator.py # 🆕 高级报告
│   │   └── templates/
│   │       └── report.html     # HTML报告模板
│   │
│   └── utils/                  # 工具层
│       ├── __init__.py
│       ├── console.py          # Rich控制台工具
│       └── logger.py           # 🆕 日志系统
│
├── configs/
│   ├── rules.yaml              # 验证规则配置
│   └── default.yaml            # 🆕 默认配置
│
├── tests/                      # 测试
│   ├── test_loader.py
│   ├── test_profiler.py
│   ├── test_validator.py
│   ├── test_semantic.py        # 🆕
│   ├── test_plugins.py         # 🆕
│   ├── test_config.py          # 🆕
│   ├── test_registry.py        # 🆕
│   ├── test_loader_extended.py # 🆕
│   └── test_integration.py     # 🆕
│
├── .github/workflows/ci.yml    # 🆕 CI配置
├── .pre-commit-config.yaml     # 🆕 Pre-commit配置
├── pyproject.toml              # 项目配置
└── README.md
```


## 配置指南

### 创建配置文件

```bash
# 复制默认配置
cp configs/default.yaml my_config.yaml
```

### 自定义治理策略

```yaml
# my_config.yaml
cleaning:
  missing:
    strategy: median        # mean / median / mode / drop
  duplicate:
    enabled: true
    keep: first
  outlier:
    method: zscore          # iqr / zscore
    threshold: 3.0
    action: remove          # flag / remove

report:
  formats:
    - html
    - json
    - markdown
  output_dir: my_reports
```

### 使用配置

```bash
dq auto data.csv --config my_config.yaml
dq batch ./datasets --config my_config.yaml
```


## 插件开发指南

### 创建自定义验证器

```python
# plugins/my_plugin.py
from dqengine.plugins.base import BaseValidator
from dqengine.models.schemas import PluginInfo, PluginType, RuleViolation

class MyValidator(BaseValidator):
    PLUGIN_INFO = PluginInfo(
        name="my_validator",
        plugin_type=PluginType.VALIDATOR,
        version="0.1.0",
        description="我的自定义验证器",
        author="Your Name",
    )

    def validate(self, df, column):
        violations = []
        for idx, val in df[column].items():
            # 自定义验证逻辑
            if not is_valid(val):
                violations.append(RuleViolation(
                    column=column,
                    rule_type="custom",
                    row_index=int(idx),
                    value=str(val),
                    message=f"'{val}' 验证失败",
                ))
        return violations
```

### 创建自定义清洗器

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
        # 自定义清洗逻辑
        df_clean = df.copy()
        # ...
        return df_clean, RepairResult(
            operation="my_cleaner",
            rows_before=len(df),
            rows_after=len(df_clean),
            columns_affected=1,
            changes_made=10,
        )
```

### 加载插件

将插件放在 `plugins/` 目录下即可自动发现：

```bash
dq plugins          # 查看已加载插件
dq plugins --type validator  # 按类型过滤
```


## CLI 完整参考

| 命令 | 说明 | 示例 |
|------|------|------|
| `dq profile <file>` | 数据分析画像 | `dq profile data.csv` |
| `dq auto <file>` | 自动清洗 | `dq auto data.csv -c config.yaml` |
| `dq validate <file>` | 规则验证 | `dq validate data.csv -r rules.yaml` |
| `dq semantic <file>` | 语义识别 | `dq semantic data.csv` |
| `dq batch <dir>` | 批量治理 | `dq batch ./datasets -w 8` |
| `dq pipeline <file>` | 导出Pipeline | `dq pipeline data.csv` |
| `dq plugins` | 插件列表 | `dq plugins --type validator` |
| `dq doctor` | 环境诊断 | `dq doctor` |
| `dq version` | 版本信息 | `dq version` |


## 测试

```bash
# 运行所有测试
pytest tests/ -v

# 带覆盖率报告
pytest tests/ --cov=dqengine --cov-report=term-missing

# 运行特定模块
pytest tests/test_semantic.py -v
pytest tests/test_plugins.py -v
pytest tests/test_integration.py -v
```


## 开发环境

```bash
# 安装依赖
pip install -e ".[dev]"

# 配置 pre-commit
pre-commit install

# 代码格式化
black dqengine/ tests/ --line-length=100
isort dqengine/ tests/ --profile=black
ruff check dqengine/ tests/

# 类型检查
mypy dqengine/
```


## Roadmap

### 第二阶段 (进行中)

- [x] Semantic Engine — 字段语义自动识别
- [x] Batch Processing — 批量数据治理
- [x] Pipeline Export — 自动生成治理Pipeline
- [x] Plugin System — 插件架构
- [x] Multi-Datasource — CSV/Excel/JSON/Parquet/SQLite
- [x] Advanced Reports — JSON/Markdown/HTML+Plotly
- [x] Configuration System — Pydantic+YAML
- [x] CLI Enhancement — Rich Panel/Table/Progress
- [x] Testing — 完整测试体系
- [x] CI/CD — GitHub Actions + pre-commit

### 第三阶段 (规划中)

- [ ] Web Dashboard — 数据质量监控面板
- [ ] Data Lineage — 数据血缘追踪
- [ ] Scheduling — 定时治理任务
- [ ] PostgreSQL Support — 完整数据库集成
- [ ] API Server — REST API 服务
- [ ] Docker Support — 容器化部署


## 贡献

欢迎提交 Issue 和 Pull Request。

确保代码通过：
- `pytest tests/ -v`
- `black dqengine/ tests/ --line-length=100 --check`
- `ruff check dqengine/ tests/`


## License

MIT License — 详见 [LICENSE](LICENSE)

---

<p align="center">
  <strong>DQEngine</strong> — 让数据治理像写代码一样优雅
</p>
