from __future__ import annotations

import json
import logging
import os
from typing import Any

from openai import OpenAI

logger = logging.getLogger("hypothesis_qqbot.llm")

# ───────── LLM Client 工厂 ─────────

def _make_client(api_key: str, base_url: str) -> OpenAI:
    import httpx
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=httpx.Client(proxy=None, trust_env=False, follow_redirects=True)
    )

def _required_api_key(env_name: str) -> str:
    api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        raise RuntimeError(f"{env_name} is required for this LLM client and must be provided via environment variable.")
    return api_key


def get_llm_client() -> OpenAI:
    api_key = _required_api_key("DEEPSEEK_API_KEY")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    return _make_client(api_key, base_url)

def get_minimax_client() -> OpenAI:
    api_key = _required_api_key("MINIMAX_API_KEY")
    base_url = os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
    return _make_client(api_key, base_url)


def get_glm_client() -> OpenAI:
    api_key = _required_api_key("GLM_API_KEY")
    base_url = os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    return _make_client(api_key, base_url)

# ───────── 通用调用接口 ─────────

def call_llm(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str = "deepseek-chat",
    temperature: float = 0.5,
    client: OpenAI | None = None,
) -> dict[str, Any]:
    """
    Calls the LLM and handles function calling if tools are provided.
    Returns the response message (which can be a text response or tool calls).
    """
    if client is None:
        client = get_llm_client()
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    # DeepSeek 暂时有些时候对 tools 的强制支持容易掉链子或返回非标准 JSON。
    if tools:
        kwargs["tools"] = tools

    response = client.chat.completions.create(**kwargs)
    message = response.choices[0].message
    
    # Check if there are tool calls
    if message.tool_calls:
        return {
            "role": "assistant",
            "content": message.content or "", # DeepSeek可能连带文字一并传
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in message.tool_calls
            ],
        }
    
    return {
        "role": "assistant",
        "content": message.content or ""
    }

