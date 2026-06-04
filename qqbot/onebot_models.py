from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from qqbot.file_ingest import QQFileCandidate, candidates_from_notice, candidates_from_segments, file_segment_paths


class MessageType(str, Enum):
    PRIVATE = "private"
    GROUP = "group"


@dataclass
class OneBotEvent:
    post_type: str
    message_type: MessageType
    user_id: str
    group_id: str | None
    message_id: int
    raw_message: str
    sender_nickname: str
    segments: list[dict[str, Any]] = field(default_factory=list)

    @property
    def conversation_id(self) -> str:
        if self.message_type == MessageType.GROUP and self.group_id:
            return f"group_{self.group_id}_user_{self.user_id}"
        return f"user_{self.user_id}"


def extract_text(segments: list[dict[str, Any]]) -> str:
    texts: list[str] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        if seg.get("type") == "text":
            texts.append(str(seg.get("data", {}).get("text", "")))
    return "".join(texts)


def file_segment_candidates(segments: list[dict[str, Any]]) -> list[QQFileCandidate]:
    """Best-effort file extraction for NapCat file/image message segments."""

    return candidates_from_segments(segments)


def has_at_mention(segments: list[dict[str, Any]], bot_qq: str | None = None) -> bool:
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        if seg.get("type") == "at":
            qq = str(seg.get("data", {}).get("qq", ""))
            if bot_qq is None or qq == bot_qq:
                return True
    return False


def strip_at_prefix(text: str, bot_name: str) -> str:
    import re

    text = re.sub(r"\[CQ:at,qq=\d+\]", "", text).strip()
    text = re.sub(rf"@{re.escape(bot_name)}\s*", "", text).strip()
    return text


def parse_message_event(event: dict[str, Any]) -> OneBotEvent | None:
    if event.get("post_type") != "message":
        return None

    try:
        msg_type = MessageType(event.get("message_type", "private"))
    except ValueError:
        return None

    segments = event.get("message", [])
    if isinstance(segments, str):
        segments = [{"type": "text", "data": {"text": segments}}]
    if not isinstance(segments, list):
        segments = []

    text = extract_text(segments)
    sender = event.get("sender", {}) or {}
    return OneBotEvent(
        post_type="message",
        message_type=msg_type,
        user_id=str(event.get("user_id", "0")),
        group_id=str(event.get("group_id")) if msg_type == MessageType.GROUP else None,
        message_id=int(event.get("message_id", 0) or 0),
        raw_message=text,
        sender_nickname=str(sender.get("nickname", "unknown")),
        segments=segments,
    )


def build_send_msg(
    message_type: MessageType,
    user_id: str,
    text: str,
    group_id: str | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "message_type": message_type.value,
        "user_id": user_id,
        "message": text,
    }
    if group_id:
        params["group_id"] = group_id
    return {"action": "send_msg", "params": params, "echo": str(uuid.uuid4())}
