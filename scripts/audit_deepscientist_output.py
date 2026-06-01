#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.deepscientist_adapter import DeepScientistCitationAuditModule


CLAIM_FILE_NAMES = (
    "citation_audit_claims.json",
    "generated_claims.json",
    "deepscientist_claims.json",
    "claims.json",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run citation evidence audit on official DeepScientist output")
    parser.add_argument("--claims", default=None, help="Explicit DeepScientist claims JSON file")
    parser.add_argument("--quest-root", default=None, help="Official DeepScientist quest/output directory")
    parser.add_argument("--run-dir", default=None, help="Explicit audit output directory")
    parser.add_argument(
        "--output-root",
        default=str(ROOT / "outputs" / "deepscientist_audits"),
        help="Audit output root when --run-dir is not provided",
    )
    parser.add_argument("--timeout-seconds", type=int, default=15)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    claims_path = resolve_claims_path(args.claims, args.quest_root)
    if not claims_path:
        print(
            "ERROR: no claims JSON found. Provide --claims or place citation_audit_claims.json "
            "inside the DeepScientist quest/output directory.",
            file=sys.stderr,
        )
        return 2
    run_dir = Path(args.run_dir).resolve() if args.run_dir else None
    module = DeepScientistCitationAuditModule(Path(args.output_root), timeout_seconds=args.timeout_seconds)
    result = module.audit_claims_file(claims_path, run_dir=run_dir)
    counts = result["label_counts"]
    print("Official DeepScientist citation evidence audit complete")
    print(f"Claims file: {claims_path}")
    print(f"Run directory: {result['run_dir']}")
    print(f"Green={counts['Green']} Yellow={counts['Yellow']} Red={counts['Red']}")
    print("Key files:")
    for name in (
        "citation_verification.csv",
        "evidence_chain.csv",
        "evidence_chain.md",
        "deepscientist_audit_summary.md",
        "tool_calls.jsonl",
        "evidence_items.jsonl",
    ):
        print(f"- {Path(result['run_dir']) / name}")
    return 0


def resolve_claims_path(claims: str | None, quest_root: str | None) -> Path | None:
    if claims:
        path = Path(claims)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        return path if path.exists() else None
    if not quest_root:
        return None
    root = Path(quest_root)
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    if not root.exists():
        return None
    for name in CLAIM_FILE_NAMES:
        direct = root / name
        if direct.exists():
            return direct
    for name in CLAIM_FILE_NAMES:
        matches = sorted(root.rglob(name), key=lambda item: len(item.parts))
        if matches:
            return matches[0]
    return None


if __name__ == "__main__":
    raise SystemExit(main())
