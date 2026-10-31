# Changelog

本项目所有重要变更记录在此文件中。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.1.0] - 2026-11-01

### 新增：LLM 集成（自然语言驱动的数据质量治理）
- LLM Provider 层（`dqengine/ai/llm.py`，纯标准库 urllib 零新依赖）：
  `OpenAIProvider` 支持任意 OpenAI 兼容端点（DeepSeek/Kimi/通义/vLLM，经
  `--base-url` 切换），`OllamaProvider` 对接本地/远程 Ollama；API Key 解析顺序
  显式参数 > `DQENGINE_LLM_API_KEY` > `OPENAI_API_KEY`；网络/鉴权/限流错误
  统一转 `LLMAPIError` 并附排查建议
- `LLMRuleGenerator` 真实现（替换原 Stub）：列统计画像（dtype/null率/唯一率/
  min-max/少量样本，不发送整表数据）→ 单次 LLM 调用 → JSON 解析（容忍代码
  围栏与前后闲聊文本）→ 规则类型白名单校验 + 置信度 clamp + 未知列丢弃并警告；
  `dq ai generate-rules -p openai|ollama` 新增 `--model/--api-key/--base-url/--timeout`
- 新增自然语言规则生成 `dq ai parse-rules`：中文/英文数据质量要求直接转成
  `RuleValidator` 可消费的 YAML（仅 min/max、regex、not_null、allowed_values 四类
  白名单键，杜绝"生成了规则但验证器静默忽略"的假通过）；可选 `--file` 对齐
  实际列名
- 新增智能修复建议 `dq ai suggest-fixes`：Profiler 统计为确定性输入，LLM 仅从
  动作白名单选建议，清洗配置片段由本地映射合成（防 LLM 结构漂移）；输出与
  `CleaningConfig` 对齐的可执行配置 + 建议报告 YAML
- 新增模型 `RepairIssue` / `RepairSuggestion`
- 新增 tests/test_llm.py（52 例，全 mock 不联网）：Provider 请求构造与错误映射、
  JSON 提取容错、规则白名单/clamp、NL 规则经 RuleValidator 回环验证（含假通过
  回归）、CLI 全命令

### 测试：v1.0.0 P0 修复的回归兜底（新增 74 例，全量 340 例）
- tests/test_api.py（17 例）：/profile /validate /clean /semantic /drift /report
  六个业务端点、坏文件 400、规则 YAML 语法 400、rules_path 目录穿越拦截、
  编排器尊重 outlier.enabled=false
- tests/test_cli.py（18 例）：profile/auto/validate/semantic/drift/batch/plugins/
  doctor/pipeline 十命令 CliRunner 路径；生成 Pipeline 脚本必须可编译
- tests/test_repair.py（21 例）：日期标准化不毁数值列/不清空合法值、nullable
  Int64 填充、重复索引异常值不误删、threshold<=0 拒绝
- tests/test_report.py（8 例）：HTML/JSON/Markdown 三格式、用户列名 XSS 转义
- tests/test_scheduler_monitor.py（10 例）：CRON/INTERVAL/WATCH 调度语义、
  croniter 缺失退化、监控回调/坏文件不崩/趋势往返
- tests/test_config.py、tests/test_integration.py 补漏断言

### 修复
- 异常值检测零 IQR 漏检：常量列（如全 0 计数列）混入偏离值时 0 检出，
  现在以常量值为界正确检出
- 空文件报错友好化：CSV 空文件由 pandas EmptyDataError 堆栈转为明确中文
  提示；auto/drift 命令加载失败统一 print_error 包装，不再冒 traceback

### 工程化
- 全仓 ruff 清零（22 处历史遗留：unused imports/变量、f-string 无占位符）
- pyproject classifier 升为 Production/Stable；black/ruff/mypy 工具链 target
  从 py311 对齐到 requires-python >=3.9
- Makefile 镜像标签、telemetry 过时 docstring 修正
- 顶层 README 过时项修正（血缘/Docker/Spark/LLM 已实现勾选、失效的 docs
  引用、configs 清单）

## [1.0.0] - 2026-10-31

首个正式发布版本。

### 新增：数据库连接器与分布式执行（热插拔插件）
- 插件体系新增两类基类：`BaseConnector`（数据源连接器，按 URI scheme 路由）与
  `BaseBackend`（分布式执行后端）；`PluginType` 新增 `backend` 类型
- 内置 SQL 连接器插件（`sql_connector`，需 `dqengine[db]`）：PostgreSQL / MySQL /
  SQLite / SQL Server / Oracle / ClickHouse / Hive / Spark(Thrift Server) /
  Presto / Trino，支持表模式（`--table`，可选 `--limit`，方言无关）与查询模式
  （`--query`）；连接串密码全程脱敏，表名经元数据反射参数化；缺方言/驱动时
  报错附安装提示
- 内置 MongoDB 连接器插件（`mongo_connector`，需 `dqengine[mongo]`）：
  `--table` = collection，`--query` = JSON 过滤条件，嵌套文档 json_normalize
  展平，ObjectId 统一字符串化
- 内置 Kafka 连接器插件（`kafka_connector`，需 `dqengine[kafka]`）：
  `kafka://broker[,broker2]/topic` 消费至多 `--limit` 条消息（缺省 1000，
  可配 timeout/offset），JSON 消息展平、非 JSON 消息入 `value` 原文列
- `DataLoader` 按 URI scheme 自动路由连接器插件：`profile` / `auto` / `validate`
  直接支持数据库连接串取数；`CleanOrchestrator` 透传 `table_name` / `query`
- 内置 Dask 执行后端插件（`dask_backend`，需 `dqengine[dask]`）：未配置调度器时
  使用本地进程集群，`DQENGINE_DASK_SCHEDULER` 可直连外部集群
- `dq batch --backend dask`：文件任务扇出到执行后端（分布式 worker 端自建输出目录
  与处理器）
- `dq validate --distributed --npartitions N`：大文件分区分片验证；4 种行级规则
  分区结果与单机对拍完全一致（行号全局对齐），列级违规按规则去重；仅在申请
  违规隔离区时回读全量数据
- 新 extras：`postgres` / `mysql` / `clickhouse` / `hive` / `mongo` / `kafka` /
  `dask`（均入 `all`）；`dq doctor` 增加可选依赖检测；`dq plugins` 支持展示
  连接器/后端类型
- 插件发现助手 `plugins/discovery.py`：内置插件目录 + 用户 `plugins/` 目录统一
  扫描（线程安全、进程内一次），连接器缓存实例化
- 注册中心修复遗留幽灵注册：抽象基类（含 @abstractmethod 的 Base* 类）不再被
  注册为插件（此前 `dq plugins` 会显示 base_validator / base_cleaner 等幽灵条目）
- 新增 tests/test_db.py、tests/test_distributed.py、tests/test_connectors.py
  （48 例，含分布式与单机对拍、多 scheme 路由、消息解码）

### 生产化
- API 服务支持可选 Key 鉴权（环境变量 `DQENGINE_API_KEY`），豁免健康检查/文档/指标端点
- 新增 Prometheus `/metrics` 端点（内置存活时长/trace 数/进程内存指标）
- 监控告警支持 Webhook 投递（`DQENGINE_WEBHOOK_URL`，兼容钉钉/企微/Slack 网关），失败不中断监控
- monitor/scheduler 全部输出迁移到结构化 logger，可被日志聚合系统采集
- 调度器任务状态持久化（`state_file`）：重启后恢复 `next_run`，CRON 任务不再因重启立即重跑
- `validate --quarantine`：违规行隔离输出（附加违规摘要列），坏数据进隔离区而非丢失
- `validate --json`：纯 JSON 输出供 CI 解析；有违规退出码 1
- `auto --fail-below-score`：清洗后评分门禁，未达标退出码 2
- CI 改为阻断式 ruff 检查；修复 test/build job 缺少 working-directory 的问题；build job 增加 twine 检查与 wheel 冒烟

### 修复（P0 级）
- 日期标准化不再把数值列（时间戳/序号）毁成 "1970-01-01"，不再静默清空无法解析的合法值
- 编排器尊重清洗配置：`outlier.enabled=false` 不再删行；strategy/method/threshold 全部生效
- HTML 报告存储型 XSS（用户列名/文件路径全部 HTML 转义）
- `profile/semantic/run-pipeline -o` 保存崩溃（pydantic 非法参数）
- nullable Int64 列缺失值填充崩溃
- JSON 数组输入时 Scorer KeyError
- API `/report`、`/validate` 端点必 500 的调用错误
- 生成的 Pipeline 代码必然崩溃且丢弃全部治理参数
- 调度器轮询模式 WATCH 无限重跑 / CRON 停摆
- 漂移检测永报全列漂移（severity 永不返回 NONE）
- 流式验证器忽略 `rules_path`（非法数据全判通过）
- 模式注销失效、Excel 数值手机号全误判、monitor 报告静默丢失
- StorageManager SQL 标识符注入面

### 修复（P1/P2 级）
- 异常值检测/移除对重复索引崩溃或误删行；`threshold<=0` 可清空数据集
- range 规则对非数值垃圾静默通过；带引号阈值崩溃；空/畸形 YAML 崩溃
- KS 漂移判定加入 p 值门控（小样本同分布误报 100%→~3%）
- AI 规则导出与验证器回环断裂（假通过）；生成 Pipeline 的 Windows 路径 SyntaxError
- DAG 上游失败不再继续执行下游；空 steps/未知依赖明确报错
- 插件系统幽灵注册与共享基类污染；API CORS 通配+凭据组合；`rules_path` 任意路径读取
- 批处理输出同名覆盖/自吞输出目录；流式验证数字事件 id 炸流等 20 余项

### 性能
- 规则验证/异常值检测向量化（1M 行 75×/135×/12×）
- 报告直方图预分箱（45MB→58KB）
- 流式验证与 WATCH 快照（24×/57×）；API 上传免落盘往返
- 清洗链 `copy=False` 协议、Profiler 重复哈希复用、CSV 编码预探测
- CLI 冷启动 0.5s→0.15s；telemetry 落库 160×（WAL + 持久连接）
- 端到端清洗管线（1M×7 列）11.2s→8.4s

### 测试
- 新增 test_production.py 覆盖鉴权/指标/Webhook/门禁/隔离/调度持久化/监控扫描
- 修复 CI lint 债务（62 处 unused imports / undefined names）

### 第四轮巡查修复
- **安全**: Pipeline 生成器列名注入 → 生成代码任意命令执行（RCE，已端到端复现并阻断）；
  血缘图 HTML/JS 注入转义
- **正确性**: 遥测持久连接跨线程静默丢数据（check_same_thread + 锁）；
  嵌套 JSON 单元格使画像/去重/多个 API 端点崩溃；
  scipy 导入失败被静默吞掉输出零漂移假报告；
  API 上传坏文件 500→400；规则 YAML 语法错误 500→400；
  调度状态与 load_config 并用时 CRON 重启仍重跑；
  tqdm 降级实现从未可用；批处理失败文件遗留陈旧输出；
  流式验证标量流崩溃；console 消息含标签形态崩溃；
  /clean 的 config_path 被静默忽略；
  validate --json 与 --quarantine 同用时隔离被跳过

## [0.3.0] 及更早

见 git 历史（ab296ea 及之前）。
