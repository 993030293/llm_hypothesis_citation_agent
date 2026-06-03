from __future__ import annotations

import json
import logging
import os
from typing import Any

from openai import OpenAI

logger = logging.getLogger("hypothesis_qqbot.llm")

# This wrapper supports OpenAI format, specifically set up to connect to DeepSeek API.
# You can override the base URL and API key via environment variables.

def get_llm_client() -> OpenAI:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    # Disable proxy detection to avoid socks4:// issues on Windows
    import httpx
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=httpx.Client(proxy=None, trust_env=False, follow_redirects=True)
    )

def call_llm(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str = "deepseek-chat",
    temperature: float = 0.5,
) -> dict[str, Any]:
    """
    Calls the LLM and handles function calling if tools are provided.
    Returns the response message (which can be a text response or tool calls).
    """
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

