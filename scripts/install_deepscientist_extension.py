#!/usr/bin/env python
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_SOURCE = ROOT / "integrations" / "deepscientist" / "citation-evidence-audit"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install citation audit skill into official DeepScientist")
    parser.add_argument(
        "--deepscientist-root",
        required=True,
        help="Path to the official ResearAI/DeepScientist repository clone",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing installed skill")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ds_root = Path(args.deepscientist_root)
    if not ds_root.is_absolute():
        ds_root = (Path.cwd() / ds_root).resolve()
    if not (ds_root / "pyproject.toml").exists() or not (ds_root / "src" / "deepscientist").exists():
        print(f"ERROR: not an official DeepScientist repository root: {ds_root}", file=sys.stderr)
        return 2
    target = ds_root / "src" / "skills" / "citation-evidence-audit"
    if target.exists():
        if not args.force:
            print(f"ERROR: target skill already exists: {target}. Use --force to overwrite.", file=sys.stderr)
            return 3
        shutil.rmtree(target)
    shutil.copytree(SKILL_SOURCE, target)
    print("Installed DeepScientist citation evidence audit skill")
    print(f"Source: {SKILL_SOURCE}")
    print(f"Target: {target}")
    print("")
    print("Next step inside a DeepScientist quest:")
    print("1. Produce citation_audit_claims.json at the quest root.")
    print("2. Run from llm_hypothesis_citation_agent:")
    print('   python scripts/audit_deepscientist_output.py --quest-root "C:\\path\\to\\quest"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
