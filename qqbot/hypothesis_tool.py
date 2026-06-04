from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import shlex
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from qqbot.file_ingest import QQFileCandidate, materialize_first_pdf

ROOT = Path(__file__).resolve().parents[1]
ProgressCallback = Callable[[str], Awaitable[None]]
PROGRESS_WATCHDOG_INTERVAL_SECONDS = 10.0
PROGRESS_WATCHDOG_STALE_SECONDS = 55.0
PROGRESS_WATCHDOG_INITIAL_GRACE_SECONDS = 10.0


@dataclass(frozen=True)
class HypothesisCommand:
    action: str
    pdf_path: Path | None = None
    quest_root: Path | None = None
    attachment_error: str = ""
    task: str = "QQ live demo: generate a research hypothesis and verify citations"
    live_demo: bool = False
    inject_bad_citation: bool = False
    dry_run: bool = False


def parse_qq_command(text: str, file_paths: list[str] | None = None) -> HypothesisCommand | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        parts = shlex.split(stripped, posix=False)
    except ValueError:
        parts = stripped.split()
    if not parts:
        return None

    command = parts[0].lower()
    if command in {"/help", "help"}:
        return HypothesisCommand(action="help")
    if command in {"/preflight", "preflight"}:
        pdf, error = _path_from_parts(parts[1:], file_paths)
        return HypothesisCommand(action="preflight", pdf_path=pdf, attachment_error=error)
    if command in {"/auditquest", "/audit", "auditquest"}:
        quest = _quest_from_parts(parts[1:])
        dry_run = "--dry-run" in {part.lower() for part in parts[1:]}
        return HypothesisCommand(action="auditquest", quest_root=quest, dry_run=dry_run)
    if command in {"/official", "/dshypothesis", "/officialhypothesis", "/ds"}:
        pdf, error = _path_from_parts(parts[1:], file_paths)
        live_demo = any(part.lower() in {"--live", "--live-demo", "--fast"} for part in parts[1:])
        dry_run = "--dry-run" in {part.lower() for part in parts[1:]}
        return HypothesisCommand(action="official", pdf_path=pdf, attachment_error=error, live_demo=live_demo, dry_run=dry_run)
    local_command = command in {"/local", "local"}
    if command not in {"/hypothesis", "/hyp", "hypothesis", "/local", "local"}:
        return None

    pdf, error = _path_from_parts(parts[1:], file_paths)
    live_demo = local_command or any(part.lower() in {"--live", "--live-demo", "--fast"} for part in parts[1:])
    if local_command and any(part.lower() in {"--full", "--full-workflow"} for part in parts[1:]):
        live_demo = False
    inject_bad = any(part.lower() in {"--bad", "--inject-bad-citation"} for part in parts[1:])
    dry_run = "--dry-run" in {part.lower() for part in parts[1:]}
    task = _task_from_parts(parts[1:]) or "QQ live demo: generate a research hypothesis and verify citations"
    return HypothesisCommand(
        action="hypothesis",
        pdf_path=pdf,
        attachment_error=error,
        task=task,
        live_demo=live_demo,
        inject_bad_citation=inject_bad,
        dry_run=dry_run,
    )


def _quest_from_parts(parts: list[str]) -> Path | None:
    for part in parts:
        if part.startswith("--"):
            continue
        candidate = part.strip().strip('"')
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_absolute():
            return path
        direct = (Path.home() / "DeepScientist" / "quests" / candidate).resolve()
        if direct.exists() or re.fullmatch(r"[A-Za-z0-9._-]+", candidate):
            return direct
        return (ROOT / candidate).resolve()
    return None


def _path_from_parts(parts: list[str], file_paths: list[str] | None) -> tuple[Path | None, str]:
    for part in parts:
        if part.startswith("--"):
            continue
        if part.lower() in {"|", "task"}:
            continue
        candidate = part.strip().strip('"')
        if candidate.lower().endswith(".pdf"):
            return _resolve_pdf_path(candidate), ""
    if file_paths:
        path, error = materialize_first_pdf([QQFileCandidate(source=value, filename=Path(value).name) for value in file_paths])
        return path, error
    return None, ""


def _task_from_parts(parts: list[str]) -> str | None:
    if "|" not in parts:
        return None
    idx = parts.index("|")
    tail = [part for part in parts[idx + 1 :] if not part.startswith("--")]
    return " ".join(tail).strip() or None


def _resolve_pdf_path(path_text: str) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


async def run_preflight(pdf_path: Path | None) -> str:
    if pdf_path is None:
        return _help_text(_missing_pdf_prefix())
    if not pdf_path.exists():
        return f"PDF not found: {pdf_path}\nCheck the path, or use /official \"FULL_PDF_PATH\"."

    from agent.pdf_preflight import preflight_pdf

    result = preflight_pdf(pdf_path, max_pages=2)
    return (
        "PDF preflight completed\n"
        f"PDF: {result['pdf']}\n"
        f"Readiness: {result['readiness']}\n"
        f"Pages checked: {result['pages_checked']} / {result['page_count']}\n"
        f"Extracted characters: {result['total_extracted_characters']}\n"
        f"Title: {result['title_preview']}\n"
        f"Keywords: {', '.join(result['keywords_preview'][:8])}\n"
        f"Risk flags: {', '.join(result['risk_flags']) or 'none'}\n\n"
        "Next command:\n"
        f"/official \"{pdf_path}\"\n"
        "Fast fallback:\n"
        f"/local \"{pdf_path}\""
    )


async def run_hypothesis(
    command: HypothesisCommand,
    timeout_seconds: int = 240,
    progress_callback: ProgressCallback | None = None,
) -> str:
    if command.pdf_path is None:
        if command.attachment_error:
            return _help_text(command.attachment_error)
        return _help_text(_missing_pdf_prefix())
    if not command.pdf_path.exists():
        return f"PDF not found: {command.pdf_path}\nCheck the path, or use /local \"FULL_PDF_PATH\"."

    cmd = [
        sys.executable,
        str(ROOT / "agent" / "workflow.py"),
        "--pdf",
        str(command.pdf_path),
        "--task",
        command.task,
    ]
    if command.live_demo:
        cmd.append("--live-demo")
    if command.inject_bad_citation:
        cmd.append("--inject-bad-citation")

    if command.dry_run:
        return "Local command to run:\n" + " ".join(cmd)

    await _emit_progress(progress_callback, "Command accepted. Starting local hypothesis workflow.")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_subprocess_env(),
    )
    try:
        stdout, stderr = await _wait_process_with_progress(proc, timeout_seconds, progress_callback)
    except asyncio.TimeoutError:
        return _final_failed(
            "Local hypothesis workflow timed out\n"
            f"PDF: {command.pdf_path}\n"
            "Use prepared logs or rerun with /official."
        )

    if proc.returncode != 0:
        return _final_failed(
            "Local hypothesis workflow failed\n"
            f"PDF: {command.pdf_path}\n"
            f"Return code: {proc.returncode}\n"
            f"Error summary:\n{_tail(stderr)}"
        )

    run_dir = _parse_run_dir(stdout)
    if run_dir is None:
        return _final_failed("Workflow finished, but no output directory was parsed.\n" + _tail(stdout))
    return _format_run_response(run_dir, command.live_demo, stdout)


async def run_official_hypothesis(
    command: HypothesisCommand,
    timeout_seconds: int = 1800,
    progress_callback: ProgressCallback | None = None,
) -> str:
    if command.pdf_path is None:
        if command.attachment_error:
            return _help_text(command.attachment_error)
        return _help_text(_missing_pdf_prefix())
    if not command.pdf_path.exists():
        return f"PDF not found: {command.pdf_path}\nCheck the path, or use /official \"FULL_PDF_PATH\"."

    run_id = "qq_official_" + time.strftime("%Y%m%d_%H%M%S")
    case_id = "qq_pdf_" + command.pdf_path.stem[:40]
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_official_ds_case.py"),
        "--case-id",
        case_id,
        "--pdf-path-or-url",
        str(command.pdf_path),
        "--run-id",
        run_id,
        "--timeout-seconds",
        str(timeout_seconds),
        "--ds-attempts",
        "2",
    ]
    if command.dry_run:
        return "Official DeepScientist command to run:\n" + " ".join(cmd)

    case_dir = ROOT / "outputs" / "deepscientist_15x_campaigns" / run_id / "cases" / case_id
    await _emit_progress(progress_callback, "Command accepted. Starting official DeepScientist + citation audit workflow.")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_subprocess_env(),
    )
    try:
        stdout, stderr = await _wait_process_with_progress(proc, timeout_seconds + 120, progress_callback)
    except asyncio.TimeoutError:
        return _final_failed(
            f"Official DeepScientist workflow timed out: {command.pdf_path}\n"
            f"Case directory: {case_dir}\n"
            f"Latest logs: {case_dir / 'logs'}\n"
            "Show the generated case directory and logs. Explain that the official agent did not write claims in time."
        )

    status = _load_json(case_dir / "case_status.json")
    if proc.returncode != 0 and not status:
        return _final_failed(
            "Official DeepScientist workflow failed\n"
            f"PDF: {command.pdf_path}\n"
            f"Case directory: {case_dir}\n"
            f"Latest logs: {case_dir / 'logs'}\n"
            f"Return code: {proc.returncode}\n"
            f"Error summary:\n{_tail(stderr)}"
        )
    audit_dir = case_dir / "citation_audit"
    counts = _read_label_counts(audit_dir / "citation_verification.csv")
    final_status = str(status.get("final_status", "unknown")) if status else "unknown"
    await _emit_progress(
        progress_callback,
        (
            "Official workflow completed. "
            f"Final status: {final_status}. "
            f"Green={counts.get('Green', 0)} Yellow={counts.get('Yellow', 0)} Red={counts.get('Red', 0)}. "
            "Preparing final report."
        ),
    )
    return _format_official_response(case_dir, status, stdout, stderr)


async def run_auditquest(
    command: HypothesisCommand,
    timeout_seconds: int = 360,
    progress_callback: ProgressCallback | None = None,
) -> str:
    if command.quest_root is None:
        return _help_text("Missing DeepScientist quest id or quest root.")
    if not command.quest_root.exists():
        return (
            f"DeepScientist quest not found: {command.quest_root}\n"
            "Check the quest id or use the full quest path."
        )
    claims_path = _find_claims_file(command.quest_root)
    if claims_path is None:
        return (
            f"citation_audit_claims.json not found under: {command.quest_root}\n"
            "Generate the claims file first, then run citation audit."
        )

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "audit_deepscientist_output.py"),
        "--quest-root",
        str(command.quest_root),
    ]
    if command.dry_run:
        return "Existing quest audit command to run:\n" + " ".join(cmd)

    await _emit_progress(progress_callback, "Command accepted. Auditing claims from an existing DeepScientist quest.")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_subprocess_env(),
    )
    try:
        stdout, stderr = await _wait_process_with_progress(proc, timeout_seconds, progress_callback)
    except asyncio.TimeoutError:
        return _final_failed(f"Existing quest citation audit timed out: {command.quest_root}")

    if proc.returncode != 0:
        return _final_failed(
            "Existing quest citation audit failed\n"
            f"Quest root: {command.quest_root}\n"
            f"Claims file: {claims_path}\n"
            f"Return code: {proc.returncode}\n"
            f"Error summary:\n{_tail(stderr)}"
        )

    run_dir = _parse_audit_run_dir(stdout)
    if run_dir is None:
        return _final_failed("Audit finished, but no audit output directory was parsed.\n" + _tail(stdout))
    return _format_auditquest_response(command.quest_root, claims_path, run_dir, stdout)


def _parse_run_dir(stdout: str) -> Path | None:
    matches = re.findall(r"Run dir:\s+(.+)", stdout)
    if not matches:
        return None
    return Path(matches[-1].strip())


def _parse_audit_run_dir(stdout: str) -> Path | None:
    matches = re.findall(r"Run directory:\s+(.+)", stdout)
    if not matches:
        return None
    return Path(matches[-1].strip())


def _format_run_response(run_dir: Path, live_demo: bool, stdout: str) -> str:
    counts = _read_label_counts(run_dir / "citation_verification.csv")
    citation_summary = _citation_summary(run_dir / "citation_verification.csv")
    report_excerpt = _report_excerpt(run_dir / "final_report.md")
    mode = "fast local mode" if live_demo else "full local workflow"
    return _final_done(
        "Local workflow finished\n"
        f"Mode: {mode}\n"
        f"Run directory: {run_dir}\n"
        f"Green={counts.get('Green', 0)} Yellow={counts.get('Yellow', 0)} Red={counts.get('Red', 0)}\n\n"
        "Files to show in class:\n"
        f"- {run_dir / 'tool_calls.jsonl'}\n"
        f"- {run_dir / 'retrieved_literature.jsonl'}\n"
        f"- {run_dir / 'citation_verification.csv'}\n"
        f"- {run_dir / 'evidence_chain.csv'}\n"
        f"- {run_dir / 'final_report.md'}\n\n"
        "Citation audit summary:\n"
        f"{citation_summary}\n\n"
        "Report excerpt:\n"
        f"{report_excerpt}\n\n"
        "Workflow status:\n"
        f"{_workflow_status(stdout)}"
    )


def _format_auditquest_response(quest_root: Path, claims_path: Path, run_dir: Path, stdout: str) -> str:
    counts = _read_label_counts(run_dir / "citation_verification.csv")
    citation_summary = _citation_summary(run_dir / "citation_verification.csv", limit=6)
    summary_excerpt = _report_excerpt(run_dir / "deepscientist_audit_summary.md")
    return _final_done(
        "Existing DeepScientist quest citation audit finished\n"
        f"Quest root: {quest_root}\n"
        f"Claims file: {claims_path}\n"
        f"Audit directory: {run_dir}\n"
        f"Green={counts.get('Green', 0)} Yellow={counts.get('Yellow', 0)} Red={counts.get('Red', 0)}\n\n"
        "Files to show in class:\n"
        f"- {run_dir / 'tool_calls.jsonl'}\n"
        f"- {run_dir / 'evidence_items.jsonl'}\n"
        f"- {run_dir / 'citation_verification.csv'}\n"
        f"- {run_dir / 'evidence_chain.csv'}\n"
        f"- {run_dir / 'deepscientist_audit_summary.md'}\n\n"
        "Citation audit summary:\n"
        f"{citation_summary}\n\n"
        "Audit report excerpt:\n"
        f"{summary_excerpt}\n\n"
        "Console summary:\n"
        f"{_tail(stdout, 700)}"
    )


def _format_official_response(case_dir: Path, status: dict[str, object], stdout: str, stderr: str) -> str:
    audit_dir = case_dir / "citation_audit"
    review_dir = case_dir / "multi_review"
    counts = _read_label_counts(audit_dir / "citation_verification.csv")
    citation_summary = _citation_summary(audit_dir / "citation_verification.csv", limit=6)
    claims_source = str(status.get("claims_source", "unknown")) if status else "unknown"
    quest_root = str(status.get("quest_root", "")) if status else ""
    final_status = str(status.get("final_status", "unknown")) if status else "unknown"
    failure_type = str(status.get("failure_type", "")) if status else ""
    failure_reason = str(status.get("failure_reason", "")) if status else ""
    meta = _load_json(review_dir / "meta_decision.json")
    reviewer_source = str(meta.get("review_source", "unknown")) if meta else "unknown"
    reviewer_score = str(meta.get("final_score_1_to_6", "")) if meta else ""
    formatter = _final_done if final_status == "success" else _final_failed
    return formatter(
        "Official DeepScientist + Citation Audit finished\n"
        f"Final status: {final_status}\n"
        f"Claims source: {claims_source}\n"
        f"Quest root: {quest_root}\n"
        f"Case directory: {case_dir}\n"
        f"Green={counts.get('Green', 0)} Yellow={counts.get('Yellow', 0)} Red={counts.get('Red', 0)}\n"
        f"Multi-reviewer: {reviewer_source}, score={reviewer_score}\n"
        f"Failure type: {failure_type or 'none'}\n"
        f"Failure reason: {_clip(failure_reason, 260) or 'none'}\n\n"
        f"Latest logs: {case_dir / 'logs'}\n\n"
        "Files to show in class:\n"
        f"- {case_dir / 'deepscientist' / 'citation_audit_claims.json'}\n"
        f"- {audit_dir / 'tool_calls.jsonl'}\n"
        f"- {audit_dir / 'provider_verification.jsonl'}\n"
        f"- {audit_dir / 'citation_verification.csv'}\n"
        f"- {audit_dir / 'evidence_chain.csv'}\n"
        f"- {review_dir / 'multi_review_report.md'}\n"
        f"- {case_dir / 'final_case_report.md'}\n\n"
        "Citation audit summary:\n"
        f"{citation_summary}\n\n"
        "Console summary:\n"
        f"{_tail(stdout or stderr, 700)}"
    )


def _find_claims_file(quest_root: Path) -> Path | None:
    names = ("citation_audit_claims.json", "generated_claims.json", "deepscientist_claims.json", "claims.json")
    for name in names:
        path = quest_root / name
        if path.exists():
            return path
    for name in names:
        matches = sorted(quest_root.rglob(name), key=lambda item: len(item.parts))
        if matches:
            return matches[0]
    return None


def _read_label_counts(csv_path: Path) -> dict[str, int]:
    counts = {"Green": 0, "Yellow": 0, "Red": 0}
    if not csv_path.exists():
        return counts
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            label = row.get("color_label", "Red")
            counts[label] = counts.get(label, 0) + 1
    return counts


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _citation_summary(csv_path: Path, limit: int = 4) -> str:
    if not csv_path.exists():
        return "citation_verification.csv not found"
    rows: list[str] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            title = _clip(row.get("cited_title", ""), 80)
            reason = _clip(row.get("reason", ""), 150)
            rows.append(
                f"- {row.get('claim_id')}: {row.get('color_label')} | "
                f"{row.get('exists_status')}/{row.get('metadata_match_status')}/{row.get('support_status')} | "
                f"{title} | {reason}"
            )
            if len(rows) >= limit:
                break
    return "\n".join(rows) if rows else "No citation audit rows found"


def _report_excerpt(path: Path) -> str:
    if not path.exists():
        return "Report file not found"
    text = path.read_text(encoding="utf-8", errors="replace")
    marker = "## Citation Verification Summary"
    if marker in text:
        text = marker + text.split(marker, 1)[1]
        stop = text.find("\n## Retrieved Literature Preview")
        if stop != -1:
            text = text[:stop]
    return _head(text, 900)


def _workflow_status(stdout: str) -> str:
    lines = [line.strip() for line in stdout.splitlines() if re.match(r"^\[\d/7\]", line.strip())]
    return "\n".join(lines[-7:]) if lines else _tail(stdout, 500)


async def _wait_process_with_progress(
    proc: asyncio.subprocess.Process,
    timeout_seconds: int,
    progress_callback: ProgressCallback | None,
) -> tuple[str, str]:
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    start = time.monotonic()
    initial_grace = min(PROGRESS_WATCHDOG_INITIAL_GRACE_SECONDS, PROGRESS_WATCHDOG_STALE_SECONDS / 2)
    progress_state = {"start": start, "last_progress_at": start + initial_grace}

    async def tracked_progress(message: str) -> None:
        progress_state["last_progress_at"] = time.monotonic()
        try:
            await _emit_progress(progress_callback, message)
        except Exception:
            return

    reader_tasks = [
        asyncio.create_task(_read_stream(proc.stdout, stdout_lines, tracked_progress)),
        asyncio.create_task(_read_stream(proc.stderr, stderr_lines, None)),
    ]
    watchdog_task = (
        asyncio.create_task(_progress_watchdog(proc, tracked_progress, progress_state))
        if progress_callback is not None
        else None
    )
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    finally:
        if watchdog_task is not None:
            watchdog_task.cancel()
        await asyncio.gather(*reader_tasks, return_exceptions=True)
        if watchdog_task is not None:
            await asyncio.gather(watchdog_task, return_exceptions=True)
    return "".join(stdout_lines), "".join(stderr_lines)


async def _progress_watchdog(
    proc: asyncio.subprocess.Process,
    progress_callback: ProgressCallback,
    progress_state: dict[str, float],
) -> None:
    while True:
        await asyncio.sleep(PROGRESS_WATCHDOG_INTERVAL_SECONDS)
        if proc.returncode is not None:
            return
        now = time.monotonic()
        last_progress_at = float(progress_state.get("last_progress_at", progress_state["start"]))
        if now - last_progress_at < PROGRESS_WATCHDOG_STALE_SECONDS:
            continue
        elapsed = int(now - progress_state["start"])
        await progress_callback(f"Still running backend process. Elapsed: {elapsed}s.")


async def _read_stream(
    stream: asyncio.StreamReader | None,
    collector: list[str],
    progress_callback: ProgressCallback | None,
) -> None:
    if stream is None:
        return
    while True:
        raw = await stream.readline()
        if not raw:
            break
        line = raw.decode("utf-8", errors="replace")
        collector.append(line)
        message = _progress_message_from_line(line)
        if message:
            try:
                await _emit_progress(progress_callback, message)
            except Exception:
                continue


async def _emit_progress(progress_callback: ProgressCallback | None, message: str) -> None:
    if progress_callback is not None:
        await progress_callback(message)


def _progress_message_from_line(line: str) -> str:
    text = line.strip()
    if not text:
        return ""
    if text.startswith("[progress]"):
        return text.removeprefix("[progress]").strip()
    if re.match(r"^\[\d+[a-z]?/7\]", text):
        return _local_workflow_progress(text)
    return ""


def _local_workflow_progress(line: str) -> str:
    if line.startswith("[1/7]"):
        return "PDF parsed. Extracting full-text evidence."
    if line.startswith("[1b/7]"):
        return "Full-text evidence extracted. Planning retrieval."
    if line.startswith("[2/7]"):
        return "Agent is planning queries and retrieving related literature."
    if line.startswith("[3/7]"):
        return "Literature retrieval finished. Organizing research ideas."
    if line.startswith("[4/7]"):
        return "Research ideas generated. Verifying citations."
    if line.startswith("[5/7]"):
        return "Citation verification finished. Writing report and evidence chain."
    if line.startswith("[6/7]"):
        return "Report and evidence chain written."
    if line.startswith("[7/7]"):
        return "Local workflow finished. Summarizing results."
    return line


def _subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8:replace"
    env["PYTHONUTF8"] = "1"
    return env


def _tail(text: str, limit: int = 1200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _head(text: str, limit: int = 1200) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n..."


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _final_done(body: str) -> str:
    return "DONE: This run has finished successfully.\n\n" + body.rstrip() + "\n\nEND OF RUN"


def _final_failed(body: str) -> str:
    return "FAILED: This run has ended with an error or incomplete result.\n\n" + body.rstrip() + "\n\nEND OF RUN"


def _missing_pdf_prefix() -> str:
    return (
        "No PDF path was provided.\n"
        "Use /official \"FULL_PDF_PATH\" or /local \"FULL_PDF_PATH\". If the path contains spaces, keep the quotes."
    )


def _help_text(prefix: str | None = None) -> str:
    lines = []
    if prefix:
        lines.append(prefix)
        lines.append("")
    lines.extend(
        [
            "Hypothesis Citation Agent",
            "",
            "Use one of these two commands:",
            "",
            "1. /official \"C:\\Users\\99303\\Desktop\\paper.pdf\"",
            "   Run official DeepScientist to generate idea/claims, then audit citations.",
            "",
            "2. /local \"C:\\Users\\99303\\Desktop\\paper.pdf\"",
            "   Run the faster local workflow. Use this if the official path is too slow.",
            "",
            "The reply includes the output directory, Green/Yellow/Red counts, and key artifact paths.",
            "If the path contains spaces, keep the quotes.",
        ]
    )
    return "\n".join(lines)


async def handle_qq_text(
    text: str,
    file_paths: list[str] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> str | None:
    command = parse_qq_command(text, file_paths=file_paths)
    if command is None:
        if text.strip().startswith("/"):
            return _help_text("Unknown QQ command.")
        return None
    if command.action == "help":
        return _help_text()
    if command.action == "preflight":
        return await run_preflight(command.pdf_path)
    if command.action == "auditquest":
        return await run_auditquest(command, progress_callback=progress_callback)
    if command.action == "hypothesis":
        return await run_hypothesis(command, progress_callback=progress_callback)
    if command.action == "official":
        return await run_official_hypothesis(command, progress_callback=progress_callback)
    return _help_text("Unknown QQ command.")
