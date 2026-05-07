"""语义模式注册中心 - 管理内置和用户自定义的语义识别模式."""

from __future__ import annotations

from typing import Dict, List, Optional

from dqengine.models.schemas import SemanticPattern, SemanticType


class PatternRegistry:
    """语义模式注册中心.

    管理模式:
        - 内置模式: 预定义的常见字段语义模式.
        - 自定义模式: 用户通过 API 或文件添加的自定义模式.

    使用方式:
        registry = get_pattern_registry()
        matches = registry.match_column_name("email_addr")
    """

    # 内置语义模式定义
    BUILTIN_PATTERNS: List[SemanticPattern] = [
        # 邮箱
        SemanticPattern(
            name="email",
            semantic_type=SemanticType.EMAIL,
            column_patterns=["email", "e-mail", "mail", "邮箱", "电子邮件", "e_mail"],
            value_regex=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
            priority=10,
            description="电子邮件地址",
        ),
        # 手机号
        SemanticPattern(
            name="phone_number",
            semantic_type=SemanticType.PHONE_NUMBER,
            column_patterns=[
                "phone", "mobile", "tel", "telephone", "cell", "mobilephone",
                "手机", "电话", "手机号", "联系电话", "phone_number", "contact",
            ],
            value_regex=r"^\+?[\d\s\-()]{7,20}$",
            priority=10,
            description="电话号码",
        ),
        # 日期时间
        SemanticPattern(
            name="datetime",
            semantic_type=SemanticType.DATETIME,
            column_patterns=[
                "date", "time", "datetime", "timestamp", "created", "updated",
                "birth", "生日", "日期", "时间", "created_at", "updated_at",
                "create_time", "update_time",
            ],
            value_regex=r"^\d{4}[-/]\d{2}[-/]\d{2}",
            priority=9,
            description="日期时间",
        ),
        # 货币
        SemanticPattern(
            name="currency",
            semantic_type=SemanticType.CURRENCY,
            column_patterns=[
                "price", "amount", "salary", "cost", "fee", "revenue",
                "价格", "金额", "工资", "费用", "收入", "currency", "money",
            ],
            value_regex=r"^[\$¥€£]?\s*[\d,]+\.?\d*$",
            priority=8,
            description="货币/金额",
        ),
        # UUID
        SemanticPattern(
            name="uuid",
            semantic_type=SemanticType.UUID,
            column_patterns=["uuid", "guid", "id", "identifier"],
            value_regex=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
            priority=9,
            description="通用唯一标识符",
        ),
        # IP地址
        SemanticPattern(
            name="ip_address",
            semantic_type=SemanticType.IP_ADDRESS,
            column_patterns=["ip", "ip_address", "ipaddr", "host", "client_ip", "server_ip"],
            value_regex=r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$",
            priority=8,
            description="IP地址",
        ),
        # URL
        SemanticPattern(
            name="url",
            semantic_type=SemanticType.URL,
            column_patterns=["url", "link", "website", "href", "链接", "网址", "web"],
            value_regex=r"^https?://[^\s]+$",
            priority=8,
            description="网页链接",
        ),
        # ID
        SemanticPattern(
            name="id",
            semantic_type=SemanticType.ID,
            column_patterns=["id", "code", "number", "编号", "序号", "user_id", "order_id"],
            value_regex=r"^[A-Z0-9_\-]+$",
            priority=5,
            description="标识符/编号",
        ),
        # 国家
        SemanticPattern(
            name="country",
            semantic_type=SemanticType.COUNTRY,
            column_patterns=["country", "nation", "国家", "国籍", "country_code"],
            value_regex="",
            priority=7,
            description="国家",
        ),
        # 城市
        SemanticPattern(
            name="city",
            semantic_type=SemanticType.CITY,
            column_patterns=["city", "town", "城市", "所在城市", "city_name"],
            value_regex="",
            priority=7,
            description="城市",
        ),
        # 年龄
        SemanticPattern(
            name="age",
            semantic_type=SemanticType.AGE,
            column_patterns=["age", "年龄", "years_old"],
            value_regex=r"^\d{1,3}$",
            priority=8,
            description="年龄",
        ),
        # 性别
        SemanticPattern(
            name="gender",
            semantic_type=SemanticType.GENDER,
            column_patterns=["gender", "sex", "性别", "sex_code"],
            value_regex="",
            priority=8,
            description="性别",
        ),
        # 姓名
        SemanticPattern(
            name="name",
            semantic_type=SemanticType.NAME,
            column_patterns=["name", "姓名", "名字", "fullname", "full_name", "username"],
            value_regex="",
            priority=6,
            description="姓名",
        ),
    ]

    def __init__(self) -> None:
        self._patterns: List[SemanticPattern] = list(self.BUILTIN_PATTERNS)
        self._custom_patterns: List[SemanticPattern] = []

    def register(self, pattern: SemanticPattern) -> None:
        """注册自定义语义模式.

        Args:
            pattern: SemanticPattern 实例.
        """
        existing = [p for p in self._custom_patterns if p.name == pattern.name]
        if existing:
            self._custom_patterns.remove(existing[0])
        self._custom_patterns.append(pattern)
        self._patterns.append(pattern)

    def unregister(self, name: str) -> bool:
        """移除自定义语义模式.

        Args:
            name: 模式名称.

        Returns:
            是否成功移除.
        """
        for p_list in [self._custom_patterns, self._patterns]:
            for i, p in enumerate(p_list):
                if p.name == name:
                    p_list.pop(i)
                    return True
        return False

    def get_all(self) -> List[SemanticPattern]:
        """获取所有已注册的语义模式 (内置 + 自定义), 按优先级排序."""
        return sorted(self._patterns, key=lambda p: p.priority, reverse=True)

    def get_builtin(self) -> List[SemanticPattern]:
        """仅获取内置模式."""
        return list(self.BUILTIN_PATTERNS)

    def get_custom(self) -> List[SemanticPattern]:
        """仅获取用户自定义模式."""
        return list(self._custom_patterns)

    def match_column(self, column_name: str) -> List[SemanticPattern]:
        """根据字段名匹配语义模式.

        Args:
            column_name: 字段名称 (大小写不敏感).

        Returns:
            匹配的 SemanticPattern 列表, 按优先级降序.
        """
        name_lower = column_name.lower()
        matches: List[SemanticPattern] = []
        for pattern in self._patterns:
            for col_pat in pattern.column_patterns:
                if col_pat.lower() == name_lower or col_pat.lower() in name_lower:
                    matches.append(pattern)
                    break
        return sorted(matches, key=lambda p: p.priority, reverse=True)

    def get_by_type(self, semantic_type: SemanticType) -> List[SemanticPattern]:
        """按语义类型获取模式.

        Args:
            semantic_type: 语义类型枚举.

        Returns:
            匹配的模式列表.
        """
        return [p for p in self._patterns if p.semantic_type == semantic_type]


# 全局单例
_registry: Optional[PatternRegistry] = None


def get_pattern_registry() -> PatternRegistry:
    """获取全局 PatternRegistry 单例."""
    global _registry
    if _registry is None:
        _registry = PatternRegistry()
    return _registry
