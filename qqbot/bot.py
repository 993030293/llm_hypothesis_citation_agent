from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

from qqbot.file_ingest import materialize_first_pdf
from qqbot.hypothesis_tool import handle_qq_text
from qqbot.onebot_models import (
    MessageType,
    build_send_msg,
    candidates_from_notice,
    file_segment_paths,
    has_at_mention,
    parse_message_event,
    strip_at_prefix,
)
from qqbot.utils import split_long_message

logger = logging.getLogger("hypothesis_qqbot.bot")
PROGRESS_MIN_INTERVAL_SECONDS = 5.0
PROGRESS_SEND_TIMEOUT_SECONDS = 10.0


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
        self._latest_ws: WebSocketServerProtocol | None = None
        self._recent_pdfs: dict[str, str] = {}

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
            self._latest_ws = ws
            logger.info("NapCat connected from %s", conn_id)
            try:
                async for raw in ws:
                    await self._on_ws_message(raw, ws)
            except websockets.exceptions.ConnectionClosed:
                logger.info("NapCat disconnected: %s", conn_id)
            finally:
                self._connections.pop(conn_id, None)
                if self._latest_ws is ws:
                    self._latest_ws = next(reversed(self._connections.values()), None) if self._connections else None

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
        if data.get("post_type") == "notice":
            await self._handle_notice(data, ws)
            return
        if data.get("post_type") != "message":
            return
        await self._handle_message(data, ws)

    async def _handle_message(self, event: dict[str, Any], ws: WebSocketServerProtocol) -> None:
        self._latest_ws = ws
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
            user_text = "/preflight"
        if not user_text:
            return

        file_paths = self._prepare_file_paths(parsed.conversation_id, file_paths)
        if not file_paths:
            recent_pdf = self._recent_pdfs.get(parsed.conversation_id)
            file_paths = _inject_recent_pdf_if_needed(user_text, recent_pdf)

        logger.info("[%s] %s: %s", parsed.conversation_id, parsed.sender_nickname, user_text[:160])
        progress_state: dict[str, float | str] = {}

        async def send_progress(message: str) -> None:
            if not _should_forward_progress(message, progress_state):
                return
            try:
                await asyncio.wait_for(
                    self._send_reply_active(
                        ws,
                        parsed.message_type,
                        parsed.user_id,
                        f"Progress: {message}",
                        parsed.group_id,
                    ),
                    timeout=PROGRESS_SEND_TIMEOUT_SECONDS,
                )
            except Exception as exc:  # noqa: BLE001 - progress delivery must not kill the backend reader.
                logger.warning("Progress reply failed for %s: %s", parsed.conversation_id, exc)

        try:
            response = await handle_qq_text(user_text, file_paths=file_paths, progress_callback=send_progress)
        except Exception:
            logger.exception("QQ command failed for %s", parsed.conversation_id)
            response = (
                "FAILED: This run has ended with an error or incomplete result.\n\n"
                "Hypothesis Citation Agent failed.\n"
                "Check the backend log: qqbot_logs/hypothesis_bot.log\n"
                "If this was /official, also check whether DeepScientist is running."
                "\n\nEND OF RUN"
            )

        if response is None:
            return
        try:
            await self._send_reply_active(ws, parsed.message_type, parsed.user_id, response, parsed.group_id)
        except Exception as exc:  # noqa: BLE001 - nothing else can be done if every QQ connection failed.
            logger.warning("Final reply failed for %s: %s", parsed.conversation_id, exc)

    async def _handle_notice(self, event: dict[str, Any], ws: WebSocketServerProtocol) -> None:
        self._latest_ws = ws
        notice_type = str(event.get("notice_type", ""))
        if notice_type not in {"group_upload", "offline_file"}:
            return
        candidates = candidates_from_notice(event)
        raw_file_paths = [candidate.source for candidate in candidates]
        if not raw_file_paths or not any(path.lower().split("?", 1)[0].endswith(".pdf") for path in raw_file_paths):
            return

        group_id = str(event.get("group_id")) if event.get("group_id") else None
        user_id = str(event.get("user_id", "0"))
        message_type = MessageType.GROUP if group_id else MessageType.PRIVATE
        conversation_id = _conversation_id(message_type, user_id, group_id)
        file_paths = self._prepare_file_paths(conversation_id, raw_file_paths)
        logger.info("[%s] PDF upload notice from %s", group_id or user_id, user_id)
        try:
            response = await handle_qq_text("/preflight", file_paths=file_paths)
        except Exception:
            logger.exception("QQ PDF upload handling failed for %s", group_id or user_id)
            response = (
                "Hypothesis Citation Agent failed to process the uploaded PDF.\n"
                "Check the backend log: qqbot_logs/hypothesis_bot.log"
            )
        if response:
            await self._send_reply_active(ws, message_type, user_id, response, group_id)

    async def _send_reply_active(
        self,
        preferred_ws: WebSocketServerProtocol,
        message_type: MessageType,
        user_id: str,
        text: str,
        group_id: str | None,
    ) -> None:
        last_error: Exception | None = None
        for candidate in self._candidate_connections(preferred_ws):
            try:
                await self._send_reply(candidate, message_type, user_id, text, group_id)
                return
            except Exception as exc:  # noqa: BLE001 - try the next live websocket if NapCat reconnected.
                last_error = exc
                logger.warning("QQ reply failed on one websocket, trying another if available: %s", exc)
        if last_error is not None:
            raise last_error

    def _candidate_connections(self, preferred_ws: WebSocketServerProtocol) -> list[WebSocketServerProtocol]:
        candidates: list[WebSocketServerProtocol] = []
        if self._latest_ws is not None:
            candidates.append(self._latest_ws)
        candidates.append(preferred_ws)
        candidates.extend(reversed(list(self._connections.values())))

        seen: set[int] = set()
        live: list[WebSocketServerProtocol] = []
        for candidate in candidates:
            marker = id(candidate)
            if marker in seen:
                continue
            seen.add(marker)
            if bool(getattr(candidate, "closed", False)):
                continue
            live.append(candidate)
        return live

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

    def _prepare_file_paths(self, conversation_id: str, file_paths: list[str]) -> list[str]:
        if not file_paths:
            return []
        saved, error = materialize_first_pdf(file_paths)
        if saved is not None:
            self._recent_pdfs[conversation_id] = str(saved)
            return [str(saved)]
        logger.warning("Could not materialize QQ PDF for %s: %s", conversation_id, error)
        return file_paths


def _conversation_id(message_type: MessageType, user_id: str, group_id: str | None) -> str:
    if message_type == MessageType.GROUP and group_id:
        return f"group_{group_id}_user_{user_id}"
    return f"user_{user_id}"


def _is_long_running_command(user_text: str) -> bool:
    lowered = user_text.strip().lower()
    if "--dry-run" in lowered:
        return False
    return lowered.startswith((
        "/official",
        "/ds",
        "/dshypothesis",
        "/officialhypothesis",
        "/local",
        "/hypothesis",
        "/hyp ",
    ))


def _command_can_use_recent_pdf(user_text: str) -> bool:
    lowered = user_text.strip().lower()
    if not lowered:
        return False
    if ".pdf" in lowered:
        return False
    return lowered.startswith((
        "/official",
        "/ds",
        "/dshypothesis",
        "/officialhypothesis",
        "/local",
        "/hypothesis",
        "/hyp ",
    ))


def _inject_recent_pdf_if_needed(user_text: str, recent_pdf: str | None) -> list[str]:
    if not recent_pdf or not _command_can_use_recent_pdf(user_text):
        return []
    path = Path(recent_pdf)
    if not path.exists():
        return []
    return [str(path)]


def _should_forward_progress(message: str, state: dict[str, float | str], now: float | None = None) -> bool:
    text = " ".join(str(message).split())
    if not text:
        return False
    if text == state.get("last_message"):
        return False
    current = time.monotonic() if now is None else now
    is_heartbeat = text.startswith("Still running ") or text.startswith("Still waiting ")
    last_heartbeat_at = float(state.get("last_heartbeat_at", -10_000.0))
    if is_heartbeat and current - last_heartbeat_at < PROGRESS_MIN_INTERVAL_SECONDS:
        return False
    state["last_message"] = text
    state["last_sent_at"] = current
    if is_heartbeat:
        state["last_heartbeat_at"] = current
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QQ bot for the hypothesis citation agent")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3002)
    parser.add_argument("--bot-name", default="CitationAgent")
    parser.add_argument("--auto-respond-group", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()
