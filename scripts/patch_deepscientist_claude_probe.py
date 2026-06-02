#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


PATCHES = (
    (
        'command.extend(["--tools", ""])',
        'command.append("--tools=")',
        "Use Claude Code --tools= form that works reliably on Windows.",
    ),
    (
        "temp_home_handle = tempfile.TemporaryDirectory()",
        'temp_home_handle = tempfile.TemporaryDirectory(ignore_cleanup_errors=os.name == "nt")',
        "Avoid Windows probe failure when Claude/plugin temp files are still locked during cleanup.",
    ),
    (
        'temp_home = tempfile.TemporaryDirectory(prefix="ds-codex-probe-")',
        'temp_home = tempfile.TemporaryDirectory(prefix="ds-codex-probe-", ignore_cleanup_errors=os.name == "nt")',
        "Avoid Windows cleanup failure for the Codex probe temp directory.",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Patch the local official DeepScientist install so Claude Code startup probes "
            "work reliably on Windows."
        )
    )
    parser.add_argument(
        "--deepscientist-root",
        default=None,
        help="Optional global @researai/deepscientist package root. Defaults to npm root -g lookup.",
    )
    parser.add_argument(
        "--deepscientist-home",
        default=str(Path.home() / "DeepScientist"),
        help="DeepScientist home containing runtime/python-env.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report target files without modifying them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = find_targets(args.deepscientist_root, Path(args.deepscientist_home))
    report: dict[str, Any] = {"targets": [], "dry_run": bool(args.dry_run)}
    if not targets:
        print("ERROR: no DeepScientist service.py files found to patch.", file=sys.stderr)
        return 2

    changed_any = False
    for target in targets:
        item = patch_file(target, dry_run=args.dry_run)
        report["targets"].append(item)
        changed_any = changed_any or bool(item.get("changed"))

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.dry_run:
        return 0
    if changed_any:
        print("Patched DeepScientist Claude probe compatibility.")
    else:
        print("DeepScientist Claude probe compatibility patch was already applied.")
    return 0


def find_targets(ds_root_value: str | None, ds_home: Path) -> list[Path]:
    targets: list[Path] = []
    ds_root = resolve_ds_root(ds_root_value)
    if ds_root:
        targets.extend(
            [
                ds_root / "src" / "deepscientist" / "config" / "service.py",
                ds_root / "build" / "lib" / "deepscientist" / "config" / "service.py",
            ]
        )
    targets.append(ds_home / "runtime" / "python-env" / "Lib" / "site-packages" / "deepscientist" / "config" / "service.py")
    targets.append(ds_home / "runtime" / "python-env" / "lib" / "python3.11" / "site-packages" / "deepscientist" / "config" / "service.py")
    return unique_existing(targets)


def resolve_ds_root(value: str | None) -> Path | None:
    if value:
        path = Path(value)
        return path if path.is_absolute() else (Path.cwd() / path).resolve()
    try:
        completed = subprocess.run(
            resolve_windows_command(["npm", "root", "-g"]),
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    npm_root = Path((completed.stdout or "").strip())
    candidate = npm_root / "@researai" / "deepscientist"
    return candidate if candidate.exists() else None


def patch_file(path: Path, *, dry_run: bool) -> dict[str, Any]:
    original = path.read_text(encoding="utf-8")
    updated = original
    applied: list[str] = []
    for old, new, reason in PATCHES:
        if old in updated:
            updated = updated.replace(old, new)
            applied.append(reason)
    changed = updated != original
    if changed and not dry_run:
        backup = path.with_suffix(path.suffix + ".citation-agent.bak")
        if not backup.exists():
            backup.write_text(original, encoding="utf-8")
        path.write_text(updated, encoding="utf-8")
    return {
        "path": str(path),
        "changed": changed,
        "applied": applied,
        "backup": str(path.with_suffix(path.suffix + ".citation-agent.bak")) if changed else "",
    }


def unique_existing(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        key = str(resolved).lower()
        if key in seen or not resolved.exists():
            continue
        seen.add(key)
        result.append(resolved)
    return result


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
