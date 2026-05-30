from __future__ import annotations

import asyncio
from pathlib import Path

from qqbot.hypothesis_tool import handle_qq_text, parse_qq_command
from qqbot.onebot_models import MessageType, build_send_msg, parse_message_event


def test_parse_hypothesis_live_command() -> None:
    command = parse_qq_command('/hypothesis inputs/papers/teacher_live.pdf --live | custom task')
    assert command is not None
    assert command.action == "hypothesis"
    assert command.pdf_path == Path("C:/Users/99303/git/llm_hypothesis_citation_agent/inputs/papers/teacher_live.pdf")
    assert command.live_demo is True
    assert command.task == "custom task"


def test_parse_preflight_from_file_segment() -> None:
    command = parse_qq_command("/preflight", file_paths=["C:/tmp/paper.pdf"])
    assert command is not None
    assert command.action == "preflight"
    assert command.pdf_path == Path("C:/tmp/paper.pdf")


def test_handle_help_returns_commands() -> None:
    response = asyncio.run(handle_qq_text("/help"))
    assert response is not None
    assert "/hypothesis" in response
    assert "/preflight" in response


def test_parse_onebot_text_event() -> None:
    event = {
        "post_type": "message",
        "message_type": "private",
        "user_id": 123,
        "message_id": 10,
        "message": [{"type": "text", "data": {"text": "/help"}}],
        "sender": {"nickname": "tester"},
    }
    parsed = parse_message_event(event)
    assert parsed is not None
    assert parsed.raw_message == "/help"
    assert parsed.message_type == MessageType.PRIVATE
    payload = build_send_msg(parsed.message_type, parsed.user_id, "ok", parsed.group_id)
    assert payload["action"] == "send_msg"
