#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.research_memory import DEFAULT_MEMORY_DIR, ResearchMemory, load_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write citation-audit case results to persistent research memory.")
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--case-id", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--pdf-path-or-url", default="")
    parser.add_argument("--quest-root", default="")
    parser.add_argument("--final-status", default="")
    parser.add_argument("--claims-source", default="")
    parser.add_argument("--citation-audit-dir", default="")
    parser.add_argument("--multi-review-dir", default="")
    parser.add_argument("--memory-dir", default=str(DEFAULT_MEMORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    status, case_dir, audit_dir, review_dir = resolve_inputs(args)
    memory = ResearchMemory(args.memory_dir)

    updates_path = case_dir / "memory_updates.jsonl"
    updates = memory.update_from_artifacts(
        case_dir=case_dir,
        status=status,
        citation_audit_dir=audit_dir,
        multi_review_dir=review_dir if review_dir.exists() else None,
        updates_path=updates_path,
    )

    summary = {
        "case_dir": str(case_dir),
        "citation_audit_dir": str(audit_dir),
        "multi_review_dir": str(review_dir) if review_dir.exists() else "",
        "memory_dir": str(Path(args.memory_dir).resolve()),
        "updates": len(updates),
        "append_count": sum(1 for item in updates if item.get("update_action") == "append"),
        "update_count": sum(1 for item in updates if item.get("update_action") == "update"),
        "case_id": status.get("case_id", ""),
        "run_id": status.get("run_id", ""),
    }
    (case_dir / "memory_update_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Memory updated: {updates_path} ({len(updates)} entries)")
    return 0


def resolve_inputs(args: argparse.Namespace) -> tuple[dict[str, Any], Path, Path, Path]:
    case_dir = Path(args.case_dir).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    status = load_json(case_dir / "case_status.json")
    status.update(overrides_from_args(args, case_dir))

    audit_dir = Path(args.citation_audit_dir).resolve() if args.citation_audit_dir else case_dir / "citation_audit"
    review_dir = Path(args.multi_review_dir).resolve() if args.multi_review_dir else case_dir / "multi_review"
    return status, case_dir, audit_dir, review_dir


def overrides_from_args(args: argparse.Namespace, case_dir: Path) -> dict[str, Any]:
    overrides: dict[str, Any] = {"case_dir": str(case_dir)}
    mapping = {
        "case_id": args.case_id,
        "run_id": args.run_id,
        "pdf_path_or_url": args.pdf_path_or_url,
        "quest_root": args.quest_root,
        "final_status": args.final_status,
        "claims_source": args.claims_source,
    }
    for key, value in mapping.items():
        if value:
            overrides[key] = value
    return overrides


if __name__ == "__main__":
    raise SystemExit(main())
