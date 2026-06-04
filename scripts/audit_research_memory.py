#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.research_memory import DEFAULT_MEMORY_DIR, MEMORY_FILES, ResearchMemory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit persistent research memory quality.")
    parser.add_argument("--memory-dir", default=str(DEFAULT_MEMORY_DIR))
    parser.add_argument("--out-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    memory_dir = Path(args.memory_dir).resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else memory_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    result = audit_memory(memory_dir=memory_dir, out_dir=out_dir)
    print(f"Memory audit written: {result['report_path']}")
    return 0


def audit_memory(*, memory_dir: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    memory = ResearchMemory(memory_dir)
    quality = memory.audit_quality()
    citation_rows = memory.read("citation")
    provider_rows = memory.read("provider")
    reviewer_rows = memory.read("reviewer")

    label_counts = count_values(citation_rows, "latest_color_label", fallback_key="color_label")
    error_counts = count_values(citation_rows, "error_type")
    provider_failures = summarize_provider_failures(provider_rows)
    duplicate_citations = sum(1 for row in citation_rows if int(row.get("seen_count") or 1) > 1)
    reviewer_scores = collect_reviewer_scores(reviewer_rows)

    csv_path = out_dir / "memory_quality.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["memory_type", "entries", "missing_case_id", "missing_run_id", "missing_doi"],
        )
        writer.writeheader()
        for memory_type, row in quality.items():
            writer.writerow({"memory_type": memory_type, **row})

    report_path = out_dir / "memory_audit_report.md"
    report_path.write_text(
        render_report(
            memory_dir=memory_dir,
            quality=quality,
            label_counts=label_counts,
            error_counts=error_counts,
            provider_failures=provider_failures,
            duplicate_citations=duplicate_citations,
            reviewer_scores=reviewer_scores,
        ),
        encoding="utf-8",
    )
    json_path = out_dir / "memory_audit_summary.json"
    json_path.write_text(
        json.dumps(
            {
                "memory_dir": str(memory_dir),
                "quality": quality,
                "label_counts": label_counts,
                "error_counts": error_counts,
                "provider_failures": provider_failures,
                "duplicate_citations": duplicate_citations,
                "reviewer_scores": reviewer_scores,
                "memory_files": {key: filename for key, (filename, _prefix) in MEMORY_FILES.items()},
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {"report_path": str(report_path), "csv_path": str(csv_path), "json_path": str(json_path)}


def count_values(rows: list[dict[str, Any]], key: str, *, fallback_key: str = "") -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or (row.get(fallback_key) if fallback_key else "") or "missing")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def summarize_provider_failures(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        provider = str(row.get("provider") or "unknown")
        tool_errors = int(row.get("tool_error_count") or 0)
        provider_counts = row.get("counts") if isinstance(row.get("counts"), dict) else {}
        explicit_errors = sum(
            int(count)
            for status, count in provider_counts.items()
            if str(status).lower() in {"error", "failed", "timeout", "api_error"}
        )
        total = tool_errors + explicit_errors
        if total:
            counts[provider] = counts.get(provider, 0) + total
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def collect_reviewer_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scores: list[float] = []
    decisions: dict[str, int] = {}
    for row in rows:
        try:
            scores.append(float(row.get("final_score_1_to_6")))
        except Exception:
            pass
        decision = str(row.get("meta_decision") or "missing")
        decisions[decision] = decisions.get(decision, 0) + 1
    avg = round(sum(scores) / len(scores), 3) if scores else ""
    return {"count": len(scores), "average_final_score": avg, "decisions": decisions}


def render_report(
    *,
    memory_dir: Path,
    quality: dict[str, Any],
    label_counts: dict[str, int],
    error_counts: dict[str, int],
    provider_failures: dict[str, int],
    duplicate_citations: int,
    reviewer_scores: dict[str, Any],
) -> str:
    lines = [
        "# Research Memory Audit",
        "",
        f"Memory directory: `{memory_dir}`",
        "",
        "## File Quality",
        "",
        "| Memory Type | Entries | Missing Case ID | Missing Run ID | Missing DOI |",
        "|---|---:|---:|---:|---:|",
    ]
    for memory_type, row in quality.items():
        lines.append(
            f"| {memory_type} | {row['entries']} | {row['missing_case_id']} | "
            f"{row['missing_run_id']} | {row['missing_doi']} |"
        )
    lines.extend(
        [
            "",
            "## Citation Label History",
            "",
        ]
    )
    append_counts(lines, label_counts)
    lines.extend(["", "## Citation Error Types", ""])
    append_counts(lines, error_counts)
    lines.extend(["", "## Provider Failure Memory", ""])
    append_counts(lines, provider_failures)
    lines.extend(
        [
            "",
            "## Reviewer Memory",
            "",
            f"- Reviewer memory entries with numeric final score: {reviewer_scores['count']}",
            f"- Average final score: {reviewer_scores['average_final_score']}",
            f"- Decisions: {json.dumps(reviewer_scores['decisions'], ensure_ascii=False)}",
            "",
            "## Dedupe",
            "",
            f"- Citation entries seen more than once: {duplicate_citations}",
        ]
    )
    return "\n".join(lines) + "\n"


def append_counts(lines: list[str], counts: dict[str, int]) -> None:
    if not counts:
        lines.append("- none")
        return
    for key, value in counts.items():
        lines.append(f"- {key}: {value}")


if __name__ == "__main__":
    raise SystemExit(main())
