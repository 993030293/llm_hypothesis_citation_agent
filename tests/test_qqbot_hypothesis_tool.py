from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from qqbot.bot import HypothesisQQBot, QQBotSettings, _inject_recent_pdf_if_needed, _should_forward_progress
from qqbot.file_ingest import candidates_from_notice, materialize_first_pdf
from qqbot import hypothesis_tool as hypothesis_tool_module
from qqbot.hypothesis_tool import _progress_message_from_line, _subprocess_env, handle_qq_text, parse_qq_command
from qqbot.onebot_models import MessageType, build_send_msg, file_segment_paths, parse_message_event


def test_parse_hypothesis_live_command() -> None:
    command = parse_qq_command('/hypothesis inputs/papers/teacher_live.pdf --live | custom task')
    assert command is not None
    assert command.action == "hypothesis"
    assert command.pdf_path == Path("C:/Users/99303/git/llm_hypothesis_citation_agent/inputs/papers/teacher_live.pdf")
    assert command.live_demo is True
    assert command.task == "custom task"


def test_parse_preflight_from_file_segment(tmp_path: Path) -> None:
    uploaded = tmp_path / "paper.pdf"
    uploaded.write_bytes(b"%PDF-1.4\n% test pdf\n")

    command = parse_qq_command("/preflight", file_paths=[str(uploaded)])
    assert command is not None
    assert command.action == "preflight"
    assert command.pdf_path is not None
    assert command.pdf_path.exists()
    assert command.pdf_path.parent.name == "qq_uploads"


def test_parse_hypothesis_from_attached_pdf(tmp_path: Path) -> None:
    uploaded = tmp_path / "attached.pdf"
    uploaded.write_bytes(b"%PDF-1.4\n% attached pdf\n")

    command = parse_qq_command("/hypothesis --live", file_paths=[str(uploaded)])

    assert command is not None
    assert command.action == "hypothesis"
    assert command.live_demo is True
    assert command.pdf_path is not None
    assert command.pdf_path.exists()


def test_parse_official_from_attached_pdf(tmp_path: Path) -> None:
    uploaded = tmp_path / "official.pdf"
    uploaded.write_bytes(b"%PDF-1.4\n% official pdf\n")

    command = parse_qq_command("/official", file_paths=[str(uploaded)])

    assert command is not None
    assert command.action == "official"
    assert command.pdf_path is not None
    assert command.pdf_path.exists()


def test_parse_official_quoted_windows_path_with_spaces() -> None:
    command = parse_qq_command('/official "C:\\Users\\99303\\Desktop\\ICML 2024 MEHA.pdf"')

    assert command is not None
    assert command.action == "official"
    assert command.pdf_path == Path("C:/Users/99303/Desktop/ICML 2024 MEHA.pdf")


def test_parse_local_quoted_windows_path_with_spaces() -> None:
    command = parse_qq_command('/local "C:\\Users\\99303\\Desktop\\ICML 2024 MEHA.pdf"')

    assert command is not None
    assert command.action == "hypothesis"
    assert command.live_demo is True
    assert command.pdf_path == Path("C:/Users/99303/Desktop/ICML 2024 MEHA.pdf")


def test_parse_auditquest_id() -> None:
    command = parse_qq_command("/auditquest 003")
    assert command is not None
    assert command.action == "auditquest"
    assert command.quest_root == Path.home() / "DeepScientist" / "quests" / "003"


def test_handle_help_returns_commands() -> None:
    response = asyncio.run(handle_qq_text("/help"))
    assert response is not None
    assert "/official" in response
    assert "/local" in response
    assert "/hypothesis" not in response
    assert "/preflight" not in response
    assert "/auditquest" not in response
    assert "--bad" not in response


def test_missing_pdf_response_is_demo_friendly() -> None:
    response = asyncio.run(handle_qq_text("/official"))

    assert response is not None
    assert "No PDF path was provided" in response
    assert "/official" in response
    assert "Missing PDF path" not in response


def test_unknown_slash_command_gets_reply() -> None:
    response = asyncio.run(handle_qq_text("/not_a_command"))

    assert response is not None
    assert "Unknown QQ command" in response
    assert "/official" in response


def test_progress_line_from_official_runner_is_forwarded() -> None:
    message = _progress_message_from_line("[progress] Skill installed in quest: citation-hypothesis-claims.")

    assert message == "Skill installed in quest: citation-hypothesis-claims."


def test_qq_subprocess_forces_utf8_output() -> None:
    env = _subprocess_env()

    assert env["PYTHONIOENCODING"] == "utf-8:replace"
    assert env["PYTHONUTF8"] == "1"


def test_local_workflow_progress_line_is_human_readable() -> None:
    message = _progress_message_from_line("[5/7] Citations verified: 3 (1.2s)")

    assert message == "Citation verification finished. Writing report and evidence chain."


def test_recent_pdf_can_be_reused_for_official(tmp_path: Path) -> None:
    uploaded = tmp_path / "remembered.pdf"
    uploaded.write_bytes(b"%PDF-1.4\n")

    assert _inject_recent_pdf_if_needed("/official", str(uploaded)) == [str(uploaded)]
    assert _inject_recent_pdf_if_needed("/local", str(uploaded)) == [str(uploaded)]
    assert _inject_recent_pdf_if_needed("/hypothesis --live", str(uploaded)) == [str(uploaded)]
    assert _inject_recent_pdf_if_needed('/official "C:\\Users\\99303\\Desktop\\paper.pdf"', str(uploaded)) == []


def test_progress_forwarding_dedupes_heartbeats_only() -> None:
    state: dict[str, float | str] = {}

    assert _should_forward_progress("Still running multi_reviewer. Elapsed: 60s.", state, now=10.0)
    assert not _should_forward_progress("Still running multi_reviewer. Elapsed: 60s.", state, now=11.0)
    assert not _should_forward_progress("Still running multi_reviewer. Elapsed: 120s.", state, now=12.0)
    assert _should_forward_progress("Finished multi_reviewer: success.", state, now=13.0)
    assert _should_forward_progress("Still running multi_reviewer. Elapsed: 180s.", state, now=18.1)


def test_process_watchdog_emits_when_backend_progress_stalls(monkeypatch) -> None:
    async def run_case() -> list[str]:
        monkeypatch.setattr(hypothesis_tool_module, "PROGRESS_WATCHDOG_INTERVAL_SECONDS", 0.02)
        monkeypatch.setattr(hypothesis_tool_module, "PROGRESS_WATCHDOG_STALE_SECONDS", 0.04)
        messages: list[str] = []

        async def progress(message: str) -> None:
            messages.append(message)

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(0.12)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await hypothesis_tool_module._wait_process_with_progress(proc, 2, progress)
        return messages

    messages = asyncio.run(run_case())

    assert any(message.startswith("Still running backend process.") for message in messages)


def test_progress_callback_exception_does_not_stop_stdout_reader() -> None:
    async def run_case() -> tuple[list[str], str]:
        calls: list[str] = []

        async def progress(message: str) -> None:
            calls.append(message)
            if len(calls) == 1:
                raise RuntimeError("temporary qq send failure")

        script = (
            "import sys\n"
            "print('[progress] Starting citation_audit.', flush=True)\n"
            "print('[progress] Still running citation_audit. Elapsed: 60s.', flush=True)\n"
        )
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await hypothesis_tool_module._wait_process_with_progress(proc, 2, progress)
        return calls, stdout

    calls, stdout = asyncio.run(run_case())

    assert calls == ["Starting citation_audit.", "Still running citation_audit. Elapsed: 60s."]
    assert "Still running citation_audit" in stdout


def test_replies_use_latest_websocket_after_reconnect() -> None:
    class FakeWebSocket:
        def __init__(self) -> None:
            self.closed = False
            self.sent: list[str] = []

        async def send(self, payload: str) -> None:
            self.sent.append(payload)

    async def run_case() -> tuple[list[str], list[str]]:
        old_ws = FakeWebSocket()
        new_ws = FakeWebSocket()
        bot = HypothesisQQBot(QQBotSettings(response_delay=0))
        bot._latest_ws = new_ws  # noqa: SLF001 - verifies reconnect routing.
        await bot._send_reply_active(old_ws, MessageType.PRIVATE, "123", "DONE", None)  # noqa: SLF001
        return old_ws.sent, new_ws.sent

    old_sent, new_sent = asyncio.run(run_case())

    assert old_sent == []
    assert len(new_sent) == 1
    assert "DONE" in new_sent[0]


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


def test_parse_onebot_file_segment_path(tmp_path: Path) -> None:
    uploaded = tmp_path / "qq_file.pdf"
    uploaded.write_bytes(b"%PDF-1.4\n")
    event = {
        "post_type": "message",
        "message_type": "private",
        "user_id": 123,
        "message_id": 11,
        "message": [
            {"type": "file", "data": {"name": "qq_file.pdf", "path": str(uploaded)}},
        ],
        "sender": {"nickname": "tester"},
    }
    parsed = parse_message_event(event)
    assert parsed is not None
    paths = file_segment_paths(parsed.segments)
    assert paths == [str(uploaded)]


def test_group_upload_notice_candidate_can_be_saved(tmp_path: Path) -> None:
    uploaded = tmp_path / "group_upload.pdf"
    uploaded.write_bytes(b"%PDF-1.4\n")
    event = {
        "post_type": "notice",
        "notice_type": "group_upload",
        "group_id": 456,
        "user_id": 123,
        "file": {"name": "group_upload.pdf", "path": str(uploaded), "size": uploaded.stat().st_size},
    }

    candidates = candidates_from_notice(event)
    saved, error = materialize_first_pdf(candidates)

    assert not error
    assert saved is not None
    assert saved.exists()
    assert saved.parent.name == "qq_uploads"


def test_materialized_pdf_is_not_copied_again(tmp_path: Path) -> None:
    saved = tmp_path / "already_saved.pdf"
    saved.write_bytes(b"%PDF-1.4\n")

    first, error = materialize_first_pdf([str(saved)], upload_dir=tmp_path)
    second, second_error = materialize_first_pdf([str(first)], upload_dir=tmp_path)

    assert not error
    assert not second_error
    assert first == saved
    assert second == saved
    assert sorted(path.name for path in tmp_path.glob("*.pdf")) == ["already_saved.pdf"]
