#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


CORE_ARTIFACTS = [
    "tool_calls.jsonl",
    "retrieved_literature.jsonl",
    "citation_verification.csv",
    "final_report.md",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QQ demo command adapter for the hypothesis citation workflow")
    parser.add_argument("--message", required=True, help='QQ-style message, e.g. "/hypothesis inputs/papers/success_demo.pdf"')
    parser.add_argument("--dry-run", action="store_true", help="Parse and print the command without running workflow.py")
    return parser.parse_args()


def parse_message(message: str) -> tuple[Path, list[str]]:
    parts = message.strip().split()
    if not parts or parts[0] not in {"/hypothesis", "/hyp"}:
        raise ValueError('Expected message like: /hypothesis inputs/papers/success_demo.pdf')
    if len(parts) < 2:
        raise ValueError("Missing PDF path after /hypothesis")
    pdf_path = Path(parts[1])
    if not pdf_path.is_absolute():
        pdf_path = (ROOT / pdf_path).resolve()
    extra_flags: list[str] = []
    if "--bad" in parts or "--inject-bad-citation" in parts:
        extra_flags.append("--inject-bad-citation")
    if "--no-followup" in parts:
        extra_flags.append("--disable-followup")
    if "--live" in parts or "--live-demo" in parts or "--fast" in parts:
        extra_flags.append("--live-demo")
    return pdf_path, extra_flags


def summarize_csv(csv_path: Path) -> dict[str, int]:
    counts = {"Green": 0, "Yellow": 0, "Red": 0}
    if not csv_path.exists():
        return counts
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            label = row.get("color_label", "Red")
            counts[label] = counts.get(label, 0) + 1
    return counts


def latest_run_dir(output_root: Path) -> Path | None:
    runs = [path for path in output_root.iterdir() if path.is_dir()] if output_root.exists() else []
    return sorted(runs, key=lambda path: path.name)[-1] if runs else None


def main() -> int:
    args = parse_args()
    try:
        pdf_path, extra_flags = parse_message(args.message)
    except ValueError as exc:
        print(f"QQ command error: {exc}")
        return 2
    if not pdf_path.exists():
        print(f"QQ command error: PDF not found: {pdf_path}")
        return 2

    command = [
        sys.executable,
        str(ROOT / "agent" / "workflow.py"),
        "--pdf",
        str(pdf_path),
        "--task",
        "QQ live demo: generate a research hypothesis and verify citations",
        *extra_flags,
    ]
    print("QQ adapter parsed command:")
    print(" ".join(command))
    if args.dry_run:
        return 0

    completed = subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True)
    print(completed.stdout)
    if completed.returncode != 0:
        print(completed.stderr)
        return completed.returncode

    run_dir = latest_run_dir(ROOT / "outputs" / "runs")
    if run_dir is None:
        print("Workflow finished, but no run directory was found.")
        return 1
    counts = summarize_csv(run_dir / "citation_verification.csv")
    print("QQ demo summary:")
    print(f"Run directory: {run_dir}")
    print(f"Green={counts.get('Green', 0)} Yellow={counts.get('Yellow', 0)} Red={counts.get('Red', 0)}")
    print("Artifacts to show:")
    for name in CORE_ARTIFACTS:
        print(f"- {run_dir / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
