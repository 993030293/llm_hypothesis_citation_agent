from __future__ import annotations

import asyncio
import csv
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class HypothesisCommand:
    action: str
    pdf_path: Path | None = None
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
        pdf = _path_from_parts(parts[1:], file_paths)
        return HypothesisCommand(action="preflight", pdf_path=pdf)
    if command not in {"/hypothesis", "/hyp", "hypothesis"}:
        return None

    pdf = _path_from_parts(parts[1:], file_paths)
    live_demo = any(part.lower() in {"--live", "--live-demo", "--fast"} for part in parts[1:])
    inject_bad = any(part.lower() in {"--bad", "--inject-bad-citation"} for part in parts[1:])
    dry_run = "--dry-run" in {part.lower() for part in parts[1:]}
    task = _task_from_parts(parts[1:]) or "QQ live demo: generate a research hypothesis and verify citations"
    return HypothesisCommand(
        action="hypothesis",
        pdf_path=pdf,
        task=task,
        live_demo=live_demo,
        inject_bad_citation=inject_bad,
        dry_run=dry_run,
    )


def _path_from_parts(parts: list[str], file_paths: list[str] | None) -> Path | None:
    for part in parts:
        if part.startswith("--"):
            continue
        if part.lower() in {"|", "task"}:
            continue
        candidate = part.strip().strip('"')
        if candidate.lower().endswith(".pdf"):
            return _resolve_pdf_path(candidate)
    for file_path in file_paths or []:
        if file_path.lower().endswith(".pdf"):
            return _resolve_pdf_path(file_path)
    return None


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
        return _help_text("Missing PDF path.")
    if not pdf_path.exists():
        return f"PDF not found: {pdf_path}\nSave the PDF under inputs/papers/ or send an absolute path."

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
        "Recommended QQ command:\n"
        f"/hypothesis {pdf_path} --live"
    )


async def run_hypothesis(command: HypothesisCommand, timeout_seconds: int = 240) -> str:
    if command.pdf_path is None:
        return _help_text("Missing PDF path.")
    if not command.pdf_path.exists():
        return f"PDF not found: {command.pdf_path}\nSave it under the project directory or use an absolute path."

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
        return "Command to run:\n" + " ".join(cmd)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return f"Hypothesis workflow timed out: {command.pdf_path}\nShow prepared logs under submission/evidence/."

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        return (
            "Hypothesis workflow failed\n"
            f"PDF: {command.pdf_path}\n"
            f"returncode: {proc.returncode}\n"
            f"stderr:\n{_tail(stderr)}"
        )

    run_dir = _parse_run_dir(stdout)
    if run_dir is None:
        return "Workflow finished, but no run directory was parsed.\n" + _tail(stdout)
    return _format_run_response(run_dir, command.live_demo, stdout)


def _parse_run_dir(stdout: str) -> Path | None:
    matches = re.findall(r"Run dir:\s+(.+)", stdout)
    if not matches:
        return None
    return Path(matches[-1].strip())


def _format_run_response(run_dir: Path, live_demo: bool, stdout: str) -> str:
    counts = _read_label_counts(run_dir / "citation_verification.csv")
    citation_summary = _citation_summary(run_dir / "citation_verification.csv")
    report_excerpt = _report_excerpt(run_dir / "final_report.md")
    mode = "live-demo" if live_demo else "full workflow"
    return (
        "Hypothesis Citation Agent completed\n"
        f"Mode: {mode}\n"
        f"Run directory: {run_dir}\n"
        f"Green={counts.get('Green', 0)} Yellow={counts.get('Yellow', 0)} Red={counts.get('Red', 0)}\n\n"
        "Files to show in class:\n"
        f"- {run_dir / 'tool_calls.jsonl'}\n"
        f"- {run_dir / 'retrieved_literature.jsonl'}\n"
        f"- {run_dir / 'citation_verification.csv'}\n"
        f"- {run_dir / 'evidence_chain.csv'}\n"
        f"- {run_dir / 'final_report.md'}\n\n"
        "Citation verification rows:\n"
        f"{citation_summary}\n\n"
        "Report excerpt:\n"
        f"{report_excerpt}\n\n"
        "Workflow status:\n"
        f"{_workflow_status(stdout)}"
    )


def _read_label_counts(csv_path: Path) -> dict[str, int]:
    counts = {"Green": 0, "Yellow": 0, "Red": 0}
    if not csv_path.exists():
        return counts
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            label = row.get("color_label", "Red")
            counts[label] = counts.get(label, 0) + 1
    return counts


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
    return "\n".join(rows) if rows else "No citation rows found"


def _report_excerpt(path: Path) -> str:
    if not path.exists():
        return "final_report.md not found"
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


def _help_text(prefix: str | None = None) -> str:
    lines = []
    if prefix:
        lines.append(prefix)
        lines.append("")
    lines.extend(
        [
            "Hypothesis Citation Agent QQ commands:",
            "/preflight inputs/papers/teacher_live.pdf",
            "/hypothesis inputs/papers/success_demo.pdf",
            "/hypothesis inputs/papers/boundary_demo.pdf --bad",
            "/hypothesis inputs/papers/teacher_live.pdf --live",
            "",
            "Notes:",
            "- --live is for teacher-supplied PDFs and uses faster settings.",
            "- --bad injects one intentionally invalid citation to demonstrate Red.",
            "- The reply returns a run directory and Green/Yellow/Red counts.",
        ]
    )
    return "\n".join(lines)


async def handle_qq_text(text: str, file_paths: list[str] | None = None) -> str | None:
    command = parse_qq_command(text, file_paths=file_paths)
    if command is None:
        return None
    if command.action == "help":
        return _help_text()
    if command.action == "preflight":
        return await run_preflight(command.pdf_path)
    if command.action == "hypothesis":
        return await run_hypothesis(command)
    return _help_text("Unknown command.")
