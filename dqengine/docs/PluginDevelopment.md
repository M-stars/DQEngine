# DQEngine 插件开发指南

## 插件类型

| 类型 | 基类 | 方法 |
|------|------|------|
| Validator | `BaseValidator` | `validate(df, column) -> List[RuleViolation]` |
| Cleaner | `BaseCleaner` | `clean(df, column) -> tuple[DataFrame, RepairResult]` |
| Scorer | `BaseScorer` | `score(df, profile) -> Dict` |
| Loader | `BasePlugin` | 自定义 |
| Reporter | `BasePlugin` | 自定义 |

## 快速开始

### 1. 创建插件文件

在 `plugins/` 目录创建 `.py` 文件：

```python
# plugins/my_validator.py

from dqengine.plugins.base import BaseValidator
from dqengine.models.schemas import PluginInfo, PluginType, RuleViolation

PLUGIN_INFO = PluginInfo(
    name="my_validator",
    plugin_type=PluginType.VALIDATOR,
    version="1.0.0",
    description="自定义数据验证器",
)

class MyCustomValidator(BaseValidator):
    PLUGIN_INFO = PLUGIN_INFO

    def validate(self, df, column):
        violations = []
        for idx, value in df[column].items():
            if self._is_invalid(value):
                violations.append(RuleViolation(
                    column=column,
                    rule_type="custom",
                    row_index=idx,
                    value=value,
                    message=f"验证失败: {value}",
                ))
        return violations

    def _is_invalid(self, value):
        # 自定义验证逻辑
        return False
```

### 2. 自动发现

插件在 `plugins/` 目录中自动发现：

```bash
dq plugins                    # 列出所有插件
dq plugins --type validator   # 按类型过滤
```

### 3. 使用插件

插件在注册后自动参与验证、清洗或评分流程。

## AI 规则生成扩展

```python
from dqengine.ai.generator import RuleGeneratorBase

class MyLLMGenerator(RuleGeneratorBase):
    provider_type = "my_provider"

    def generate(self, df, columns=None):
        # 调用自定义 LLM
        ...
        return AIRuleSet(...)
```

## 漂移检测扩展

自定义漂移检测可以通过继承 `DriftDetector` 或添加新的统计方法：

```python
from dqengine.drift.detector import DriftDetector

class MyDriftDetector(DriftDetector):
    def _detect_custom_drift(self, baseline, current):
        # 自定义漂移检测
        return []
```

## Pipeline 节点扩展

```python
from dqengine.orchestrator.engine import DAGEngine
from dqengine.models.schemas import DAGNodeType

engine = DAGEngine()
engine.register_executor("my_type", my_custom_executor)
```
