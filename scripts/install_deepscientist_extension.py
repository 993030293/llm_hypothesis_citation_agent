#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_SOURCES = (
    ROOT / "integrations" / "deepscientist" / "citation-hypothesis-claims",
    ROOT / "integrations" / "deepscientist" / "citation-evidence-audit",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install citation audit skill into official DeepScientist")
    parser.add_argument(
        "--deepscientist-root",
        default=None,
        help=(
            "Path to the official ResearAI/DeepScientist repository clone or npm package root. "
            "When omitted, the script tries the globally installed @researai/deepscientist package."
        ),
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing installed skill")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ds_root = resolve_deepscientist_root(args.deepscientist_root)
    if ds_root is None:
        print(
            "ERROR: could not find DeepScientist. Install it with "
            "`npm install -g @researai/deepscientist`, or pass --deepscientist-root.",
            file=sys.stderr,
        )
        return 2
    if not (ds_root / "pyproject.toml").exists() or not (ds_root / "src" / "deepscientist").exists():
        print(f"ERROR: not an official DeepScientist repository root: {ds_root}", file=sys.stderr)
        return 2
    for source in SKILL_SOURCES:
        if not source.exists():
            print(f"ERROR: missing project skill source: {source}", file=sys.stderr)
            return 3
        target = ds_root / "src" / "skills" / source.name
        if target.exists():
            if not args.force:
                print(f"ERROR: target skill already exists: {target}. Use --force to overwrite.", file=sys.stderr)
                return 3
            shutil.rmtree(target)
        shutil.copytree(source, target)
        print(f"Installed DeepScientist skill: {source.name}")
        print(f"Source: {source}")
        print(f"Target: {target}")
    print("")
    print("Next step inside a DeepScientist quest:")
    print("1. Run `ds run citation-hypothesis-claims ...` or ask DeepScientist to produce citation_audit_claims.json.")
    print("2. Run from llm_hypothesis_citation_agent:")
    print('   python scripts/audit_deepscientist_output.py --quest-root "C:\\path\\to\\quest"')
    return 0


def resolve_deepscientist_root(value: str | None) -> Path | None:
    if value:
        root = Path(value)
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
        return root
    try:
        completed = subprocess.run(
            resolve_windows_command(["npm", "root", "-g"]),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    npm_root = Path((completed.stdout or "").strip())
    if not npm_root:
        return None
    candidate = npm_root / "@researai" / "deepscientist"
    return candidate if candidate.exists() else None


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


if __name__ == "__main__":
    raise SystemExit(main())
