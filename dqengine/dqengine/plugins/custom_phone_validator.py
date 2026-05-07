"""示例插件: 自定义手机号验证器."""

from __future__ import annotations

import re
from typing import List

import pandas as pd

from dqengine.models.schemas import PluginInfo, PluginType, RuleViolation
from dqengine.plugins.base import BaseValidator


class CustomPhoneValidator(BaseValidator):
    """严格中国手机号验证器.

    验证规则:
        - 11位数字
        - 1开头
        - 第二位为3-9
    """

    PLUGIN_INFO = PluginInfo(
        name="custom_phone_validator",
        plugin_type=PluginType.VALIDATOR,
        version="0.1.0",
        description="严格的中国手机号格式验证器",
        author="DQEngine Team",
    )

    # 中国手机号正则: 1[3-9] 开头 + 9位数字
    CHINESE_PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")

    def validate(self, df: pd.DataFrame, column: str) -> List[RuleViolation]:
        """验证指定列中的手机号格式.

        Args:
            df: 输入 DataFrame.
            column: 目标字段名.

        Returns:
            RuleViolation 列表.
        """
        violations: List[RuleViolation] = []

        if column not in df.columns:
            return [
                RuleViolation(
                    column=column,
                    rule_type="custom_phone",
                    row_index=-1,
                    value=None,
                    message=f"列 '{column}' 不存在",
                )
            ]

        for idx, val in df[column].items():
            if pd.isna(val):
                continue
            if not self.CHINESE_PHONE_PATTERN.match(str(val).strip()):
                violations.append(
                    RuleViolation(
                        column=column,
                        rule_type="custom_phone",
                        row_index=int(idx),
                        value=str(val),
                        message=f"'{val}' 不是合法的中国手机号",
                    )
                )

        return violations
