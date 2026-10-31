"""LLM Provider 层 — OpenAI 兼容端点与 Ollama 的统一调用接口.

仅依赖标准库 urllib, 不引入 SDK:

- ``OpenAIProvider``: 任何 OpenAI 兼容 REST 端点 (OpenAI / DeepSeek / Kimi /
  通义 / vLLM / Ollama 的 /v1 兼容层 ...), 通过 ``base_url`` 自由切换
- ``OllamaProvider``: 本地/远程 Ollama 的原生 ``/api/chat``

API Key 解析顺序: 显式参数 > DQENGINE_LLM_API_KEY > OPENAI_API_KEY.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

__all__ = [
    "LLMProviderBase",
    "OpenAIProvider",
    "OllamaProvider",
    "LLMAPIError",
    "make_provider",
]

DEFAULT_TIMEOUT = 60.0
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"


class LLMAPIError(RuntimeError):
    """LLM 调用失败 (网络/鉴权/模型错误), message 面向终端用户可直接展示."""


def resolve_api_key(explicit: Optional[str] = None) -> Optional[str]:
    """API Key 解析: 显式参数 > DQENGINE_LLM_API_KEY > OPENAI_API_KEY."""
    return (
        explicit
        or os.environ.get("DQENGINE_LLM_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )


class LLMProviderBase(ABC):
    """LLM Provider 基类 — 子类实现单轮对话补全."""

    name: str = "base"

    @abstractmethod
    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        """发送单轮对话, 返回助手回复文本.

        Args:
            system: 系统提示词.
            user: 用户消息.
            json_mode: True 时请求模型输出严格 JSON (Provider 支持则传参,
                不支持则仅依赖提示词约束).
        """
        ...


def _post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: float) -> Dict[str, Any]:
    """POST JSON 并解析响应体, 统一网络错误为 LLMAPIError."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # pragma: no cover - 响应体读取失败时忽略
            pass
        if e.code in (401, 403):
            raise LLMAPIError(f"LLM 鉴权失败 (HTTP {e.code}): 请检查 API Key。{detail}") from e
        if e.code == 404:
            raise LLMAPIError(f"LLM 端点不存在 (HTTP 404): 请检查 base_url 与模型名。{detail}") from e
        if e.code == 429:
            raise LLMAPIError(f"LLM 请求被限流 (HTTP 429): 请稍后重试。{detail}") from e
        raise LLMAPIError(f"LLM 请求失败 (HTTP {e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise LLMAPIError(f"无法连接 LLM 服务 ({url}): {e.reason}") from e
    except TimeoutError as e:
        raise LLMAPIError(f"LLM 请求超时 ({timeout}s): 可用 --timeout 调大") from e
    except json.JSONDecodeError as e:
        raise LLMAPIError("LLM 返回了非 JSON 响应") from e


class OpenAIProvider(LLMProviderBase):
    """OpenAI 兼容 Chat Completions Provider.

    Args:
        model: 模型名, 如 gpt-4o-mini / deepseek-chat / qwen-plus.
        api_key: 缺省时从环境变量解析 (见 resolve_api_key).
        base_url: OpenAI 兼容端点, 缺省官方; DeepSeek 等中转端点直接换此处.
        timeout: 请求超时秒数.
    """

    name = "openai"

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.model = model
        self.api_key = resolve_api_key(api_key)
        if not self.api_key:
            raise LLMAPIError(
                "缺少 API Key: 请通过 --api-key 或环境变量 DQENGINE_LLM_API_KEY / OPENAI_API_KEY 提供"
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = _post_json(
            f"{self.base_url}/chat/completions",
            payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMAPIError(f"LLM 响应格式异常: {json.dumps(data, ensure_ascii=False)[:300]}") from e
        if not isinstance(content, str):
            raise LLMAPIError("LLM 响应缺少文本内容")
        return content


class OllamaProvider(LLMProviderBase):
    """Ollama 原生 /api/chat Provider, 无需 API Key.

    Args:
        model: 模型名, 如 qwen2.5 / llama3.1 (需已 ollama pull).
        base_url: Ollama 服务地址; 环境变量 OLLAMA_HOST 可覆盖缺省值.
        timeout: 请求超时秒数 (本地大模型首响应较慢, 可调大).
    """

    name = "ollama"

    def __init__(
        self,
        model: str = "qwen2.5",
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = (base_url or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        self.timeout = timeout

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0.1},
        }
        if json_mode:
            payload["format"] = "json"
        data = _post_json(
            f"{self.base_url}/api/chat",
            payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as e:
            raise LLMAPIError(f"Ollama 响应格式异常: {json.dumps(data, ensure_ascii=False)[:300]}") from e
        if not isinstance(content, str):
            raise LLMAPIError("Ollama 响应缺少文本内容")
        return content


def make_provider(
    provider: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> LLMProviderBase:
    """按名称构造 Provider (工厂), 供 CLI/服务层复用.

    Args:
        provider: "openai" 或 "ollama".
        model: 缺省 openai -> gpt-4o-mini, ollama -> qwen2.5.
        api_key/base_url/timeout: 透传给具体 Provider.
    """
    name = (provider or "").strip().lower()
    if name == "openai":
        return OpenAIProvider(
            model=model or "gpt-4o-mini",
            api_key=api_key,
            base_url=base_url or DEFAULT_OPENAI_BASE_URL,
            timeout=timeout,
        )
    if name == "ollama":
        kwargs: Dict[str, Any] = {"model": model or "qwen2.5", "timeout": timeout}
        if base_url:
            kwargs["base_url"] = base_url
        return OllamaProvider(**kwargs)
    raise LLMAPIError(f"未知 LLM Provider: '{provider}' (支持: openai, ollama)")


def extract_json(text: str) -> Dict[str, Any]:
    """从 LLM 回复中提取第一个 JSON 对象.

    容忍 markdown 代码围栏、前后闲聊文本; 解析失败抛 ValueError.
    """
    if not text or not text.strip():
        raise ValueError("LLM 回复为空")
    cleaned = text.strip()
    # 剥离 ```json ... ``` 围栏
    if "```" in cleaned:
        parts = cleaned.split("```")
        for part in parts:
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{"):
                cleaned = candidate
                break
    start = cleaned.find("{")
    if start < 0:
        raise ValueError(f"LLM 回复中未找到 JSON 对象: {cleaned[:200]}")
    # 从末尾向前找匹配的右括号
    depth = 0
    end = -1
    in_string = False
    escape = False
    for i, ch in enumerate(cleaned[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        raise ValueError(f"LLM 回复中 JSON 不完整: {cleaned[:200]}")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM 回复 JSON 解析失败: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError("LLM 回复 JSON 顶层必须是对象")
    return parsed


def normalize_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """预留: 多轮对话消息归一化 (当前仅单轮, 保持接口稳定)."""
    return messages
