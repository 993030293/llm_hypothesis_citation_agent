from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

from qqbot.hypothesis_tool import handle_qq_text
from qqbot.onebot_models import (
    MessageType,
    build_send_msg,
    file_segment_paths,
    has_at_mention,
    parse_message_event,
    strip_at_prefix,
)
from qqbot.utils import split_long_message

logger = logging.getLogger("hypothesis_qqbot.bot")


@dataclass(frozen=True)
class QQBotSettings:
    host: str = "127.0.0.1"
    port: int = 3002
    bot_name: str = "CitationAgent"
    auto_respond_group: bool = False
    response_delay: float = 0.4


class HypothesisQQBot:
    def __init__(self, settings: QQBotSettings):
        self.settings = settings
        self._connections: dict[str, WebSocketServerProtocol] = {}

    async def run(self) -> None:
        logger.info(
            "Hypothesis QQ bot listening on ws://%s:%d",
            self.settings.host,
            self.settings.port,
        )

        async def handler(ws: WebSocketServerProtocol) -> None:
            remote = ws.remote_address
            conn_id = f"{remote[0]}:{remote[1]}" if remote else "unknown"
            self._connections[conn_id] = ws
            logger.info("NapCat connected from %s", conn_id)
            try:
                async for raw in ws:
                    await self._on_ws_message(raw, ws)
            except websockets.exceptions.ConnectionClosed:
                logger.info("NapCat disconnected: %s", conn_id)
            finally:
                self._connections.pop(conn_id, None)

        async with websockets.serve(handler, self.settings.host, self.settings.port, ping_interval=30, ping_timeout=10):
            await asyncio.Future()

    async def _on_ws_message(self, raw: str, ws: WebSocketServerProtocol) -> None:
        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            logger.debug("Ignoring non-json websocket message")
            return

        if "echo" in data:
            return
        if data.get("post_type") != "message":
            return
        await self._handle_message(data, ws)

    async def _handle_message(self, event: dict[str, Any], ws: WebSocketServerProtocol) -> None:
        parsed = parse_message_event(event)
        if parsed is None:
            return

        if parsed.message_type == MessageType.GROUP and not self.settings.auto_respond_group:
            if not has_at_mention(parsed.segments):
                return
            parsed.raw_message = strip_at_prefix(parsed.raw_message, self.settings.bot_name)

        user_text = parsed.raw_message.strip()
        file_paths = file_segment_paths(parsed.segments)
        if not user_text and file_paths:
            user_text = "/preflight " + file_paths[0]
        if not user_text:
            return

        logger.info("[%s] %s: %s", parsed.conversation_id, parsed.sender_nickname, user_text[:160])
        try:
            response = await handle_qq_text(user_text, file_paths=file_paths)
        except Exception:
            logger.exception("QQ command failed for %s", parsed.conversation_id)
            response = "Hypothesis Citation Agent 执行失败，请查看 qqbot_logs/hypothesis_bot.log。"

        if response is None:
            return
        await self._send_reply(ws, parsed.message_type, parsed.user_id, response, parsed.group_id)

    async def _send_reply(
        self,
        ws: WebSocketServerProtocol,
        message_type: MessageType,
        user_id: str,
        text: str,
        group_id: str | None,
    ) -> None:
        for part in split_long_message(text):
            await ws.send(json.dumps(build_send_msg(message_type, user_id, part, group_id), ensure_ascii=False))
            await asyncio.sleep(self.settings.response_delay)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QQ bot for the hypothesis citation agent")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3002)
    parser.add_argument("--bot-name", default="CitationAgent")
    parser.add_argument("--auto-respond-group", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()
