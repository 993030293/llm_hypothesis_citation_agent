#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small official-DeepScientist path-2 smoke test.")
    parser.add_argument("--quest-id", default=None, help="Optional fixed quest id. Defaults to a timestamped smoke-test id.")
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--output-root", default=str(ROOT / "outputs" / "path2_smoke_tests"))
    parser.add_argument("--keep-existing-quest", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    quest_id = args.quest_id or f"path2-smoke-citation-audit-{stamp}"
    smoke_dir = Path(args.output_root) / stamp
    smoke_dir.mkdir(parents=True, exist_ok=True)
    quest_root = Path.home() / "DeepScientist" / "quests" / quest_id

    if not quest_root.exists() or not args.keep_existing_quest:
        goal = (
            "Path2 smoke test: create citation-backed claims for a citation hallucination audit. "
            "The audit module will verify Green/Yellow/Red labels after DeepScientist/Claude output."
        )
        created = run(["ds", "new", goal, "--quest-id", quest_id], timeout_seconds=120)
        (smoke_dir / "ds_new_stdout.txt").write_text(created["stdout"], encoding="utf-8")
        (smoke_dir / "ds_new_stderr.txt").write_text(created["stderr"], encoding="utf-8")
        if created["returncode"] != 0:
            return fail(smoke_dir, f"`ds new` failed: {created['stderr']}")

    claims_payload = generate_claims_with_claude(quest_root, smoke_dir, timeout_seconds=args.timeout_seconds)
    if not claims_payload.get("claims"):
        return fail(smoke_dir, "Claude did not produce a usable claims payload.")
    claims_path = quest_root / "citation_audit_claims.json"
    claims_path.write_text(json.dumps(claims_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    audit_dir = smoke_dir / "citation_audit"
    audit = run(
        [
            sys.executable,
            str(ROOT / "scripts" / "audit_deepscientist_output.py"),
            "--quest-root",
            str(quest_root),
            "--run-dir",
            str(audit_dir),
        ],
        timeout_seconds=300,
    )
    (smoke_dir / "audit_stdout.txt").write_text(audit["stdout"], encoding="utf-8")
    (smoke_dir / "audit_stderr.txt").write_text(audit["stderr"], encoding="utf-8")
    if audit["returncode"] != 0:
        return fail(smoke_dir, f"Audit failed: {audit['stderr']}")

    summary = {
        "ok": True,
        "quest_id": quest_id,
        "quest_root": str(quest_root),
        "claims_path": str(claims_path),
        "audit_dir": str(audit_dir),
        "audit_stdout": audit["stdout"],
    }
    (smoke_dir / "path2_smoke_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (smoke_dir / "path2_smoke_summary.md").write_text(
        "\n".join(
            [
                "# Path-2 Smoke Test",
                "",
                "Status: PASS",
                "",
                f"Quest root: `{quest_root}`",
                f"Claims file: `{claims_path}`",
                f"Audit directory: `{audit_dir}`",
                "",
                "Audit output:",
                "",
                "```text",
                audit["stdout"].strip(),
                "```",
            ]
        ),
        encoding="utf-8",
    )
    print("Path-2 smoke test passed")
    print(f"Quest root: {quest_root}")
    print(f"Claims file: {claims_path}")
    print(f"Audit directory: {audit_dir}")
    return 0


def generate_claims_with_claude(quest_root: Path, smoke_dir: Path, *, timeout_seconds: int) -> dict[str, Any]:
    target_payload = {
        "claims": [
            {
                "claim_id": "C_SMOKE_001",
                "hypothesis_id": "H_SMOKE_FINANCE_AGENT",
                "claim_text": (
                    "FinRL provides a deep reinforcement learning library and framework for automated "
                    "stock trading in quantitative finance."
                ),
                "claim_role": "citation_backed_claim",
                "cited_work": {
                    "title": "FinRL: A Deep Reinforcement Learning Library for Automated Stock Trading in Quantitative Finance",
                    "authors": ["Xiao-Yang Liu", "Hongyang Yang"],
                    "year": 2020,
                    "doi": "",
                    "url": "https://arxiv.org/abs/2011.09607",
                    "retrieval_source": "official_deepscientist_claude_smoke",
                    "abstract": (
                        "FinRL is presented as a deep reinforcement learning library for automated stock "
                        "trading in quantitative finance. It provides a framework that helps researchers "
                        "and practitioners develop and compare deep reinforcement learning algorithms for "
                        "stock trading tasks."
                    ),
                },
            },
            {
                "claim_id": "C_SMOKE_002",
                "hypothesis_id": "H_SMOKE_BOUNDARY",
                "claim_text": (
                    "A nonexistent boundary-demo paper proves that intentionally invalid citation metadata "
                    "should be rejected by the verifier."
                ),
                "claim_role": "deliberately_bad_citation_boundary_case",
                "cited_work": {
                    "title": "Clearly Nonexistent Citation Verification Paper for Boundary Demo",
                    "authors": ["No Such Author"],
                    "year": 2099,
                    "doi": "INTENTIONALLY_INVALID_DOI_FOR_DEMO",
                    "url": "",
                    "retrieval_source": "official_deepscientist_claude_smoke",
                },
            },
        ]
    }
    prompt = (
        "Do not use tools. Do not read or write files. Do not mention the filesystem. "
        "Your only task is to print valid JSON. The first character of your answer must be '{' "
        "and the last character must be '}'. Return exactly the following JSON object with no "
        "markdown, no explanation, and no extra keys:\n"
        f"{json.dumps(target_payload, ensure_ascii=False)}"
    )
    result = run(
        [
            "claude",
            "-p",
            "--input-format",
            "text",
            "--output-format",
            "json",
            "--tools=",
        ],
        cwd=quest_root,
        input_text=prompt,
        timeout_seconds=timeout_seconds,
    )
    (smoke_dir / "claude_claims_stdout.txt").write_text(result["stdout"], encoding="utf-8")
    (smoke_dir / "claude_claims_stderr.txt").write_text(result["stderr"], encoding="utf-8")
    if result["returncode"] != 0:
        return {}
    try:
        stdout_payload = json.loads(result["stdout"])
        text = str(stdout_payload.get("result") if isinstance(stdout_payload, dict) else result["stdout"]).strip()
        return parse_json_payload(text)
    except json.JSONDecodeError:
        try:
            return parse_json_payload(result["stdout"])
        except json.JSONDecodeError:
            return {}


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    resolved_cmd = resolve_windows_command(cmd)
    try:
        completed = subprocess.run(
            resolved_cmd,
            cwd=str(cwd or ROOT),
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        return {"returncode": completed.returncode, "stdout": completed.stdout or "", "stderr": completed.stderr or ""}
    except subprocess.TimeoutExpired as exc:
        return {"returncode": -1, "stdout": str(exc.stdout or ""), "stderr": f"Timed out after {timeout_seconds}s"}
    except OSError as exc:
        return {"returncode": 127, "stdout": "", "stderr": str(exc)}


def parse_json_payload(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def resolve_windows_command(cmd: list[str]) -> list[str]:
    if os.name != "nt" or not cmd:
        return cmd
    executable = cmd[0]
    if Path(executable).suffix:
        return cmd
    for candidate in (f"{executable}.cmd", f"{executable}.exe", executable):
        resolved = shutil.which(candidate)
        if resolved:
            return [resolved, *cmd[1:]]
    return cmd


def fail(smoke_dir: Path, message: str) -> int:
    (smoke_dir / "path2_smoke_summary.md").write_text(f"# Path-2 Smoke Test\n\nStatus: FAIL\n\n{message}\n", encoding="utf-8")
    print(message, file=sys.stderr)
    print(f"Report: {smoke_dir / 'path2_smoke_summary.md'}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
