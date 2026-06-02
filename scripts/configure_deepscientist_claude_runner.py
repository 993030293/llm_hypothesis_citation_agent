#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enable Claude Code as the local DeepScientist runner.")
    parser.add_argument(
        "--deepscientist-home",
        default=str(Path.home() / "DeepScientist"),
        help="DeepScientist home containing config/config.yaml and config/runners.yaml.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    home = Path(args.deepscientist_home).expanduser()
    config_path = home / "config" / "config.yaml"
    runners_path = home / "config" / "runners.yaml"
    report: dict[str, Any] = {
        "home": str(home),
        "config_path": str(config_path),
        "runners_path": str(runners_path),
        "dry_run": bool(args.dry_run),
        "changes": [],
    }
    if not config_path.exists() or not runners_path.exists():
        print(json.dumps({**report, "ok": False, "error": "DeepScientist config files are missing."}, indent=2), flush=True)
        return 2

    config_text = config_path.read_text(encoding="utf-8")
    updated_config = set_top_level_value(config_text, "default_runner", "claude")
    if updated_config != config_text:
        report["changes"].append("Set config.default_runner to claude.")
        if not args.dry_run:
            backup_once(config_path)
            config_path.write_text(updated_config, encoding="utf-8")

    runners_text = runners_path.read_text(encoding="utf-8")
    updated_runners = set_runner_enabled(runners_text, "claude", True)
    if updated_runners != runners_text:
        report["changes"].append("Set runners.claude.enabled to true.")
        if not args.dry_run:
            backup_once(runners_path)
            runners_path.write_text(updated_runners, encoding="utf-8")

    report["ok"] = True
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def set_top_level_value(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    replaced = False
    for idx, line in enumerate(lines):
        if line.startswith(f"{key}:"):
            lines[idx] = f"{key}: {value}"
            replaced = True
            break
    if not replaced:
        lines.insert(0, f"{key}: {value}")
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def set_runner_enabled(text: str, runner: str, enabled: bool) -> str:
    lines = text.splitlines()
    runner_start = None
    for idx, line in enumerate(lines):
        if line == f"{runner}:":
            runner_start = idx
            break
    if runner_start is None:
        suffix = "\n" if text.endswith("\n") else ""
        return text + suffix + f"{runner}:\n  enabled: {str(enabled).lower()}\n"

    runner_end = len(lines)
    for idx in range(runner_start + 1, len(lines)):
        if lines[idx] and not lines[idx].startswith(" "):
            runner_end = idx
            break

    enabled_line = f"  enabled: {str(enabled).lower()}"
    for idx in range(runner_start + 1, runner_end):
        if lines[idx].startswith("  enabled:"):
            lines[idx] = enabled_line
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    lines.insert(runner_start + 1, enabled_line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".citation-agent.bak")
    if not backup.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
