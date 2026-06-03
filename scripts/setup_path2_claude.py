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
SKILL_SOURCE = ROOT / "integrations" / "deepscientist" / "citation-evidence-audit"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare official DeepScientist + Claude Code for the path-2 citation audit workflow."
    )
    parser.add_argument("--skip-install-ds", action="store_true", help="Do not install @researai/deepscientist if ds is missing.")
    parser.add_argument("--skip-doctor", action="store_true", help="Skip `ds doctor --runner claude`.")
    parser.add_argument("--force-skill", action="store_true", help="Overwrite an existing DeepScientist skill install.")
    parser.add_argument(
        "--report-dir",
        default=str(ROOT / "outputs" / "path2_setup"),
        help="Directory for setup report artifacts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_dir = Path(args.report_dir) / time.strftime("%Y%m%d_%H%M%S")
    report_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {"report_dir": str(report_dir), "steps": []}

    node = run(["node", "--version"])
    npm = run(["npm", "--version"])
    results["steps"].append(step("node", node))
    results["steps"].append(step("npm", npm))
    if node["returncode"] != 0 or npm["returncode"] != 0:
        return finish(report_dir, results, 2, "Node.js/npm is required for official DeepScientist.")

    claude_version = run(["claude", "--version"])
    results["steps"].append(step("claude_version", claude_version))
    if claude_version["returncode"] != 0:
        return finish(report_dir, results, 2, "Claude Code CLI is not available. Install/login Claude Code first.")

    claude_smoke = run(
        [
            "claude",
            "-p",
            "Reply with exactly HELLO.",
            "--output-format",
            "json",
            "--tools=",
        ],
        timeout_seconds=180,
    )
    results["steps"].append(step("claude_smoke", claude_smoke))
    if claude_smoke["returncode"] != 0 or "HELLO" not in (claude_smoke["stdout"] + claude_smoke["stderr"]).upper():
        return finish(report_dir, results, 3, "Claude Code did not return HELLO in headless mode.")

    ds_path = shutil.which("ds")
    if not ds_path and not args.skip_install_ds:
        install = run(["npm", "install", "-g", "@researai/deepscientist"], timeout_seconds=300)
        results["steps"].append(step("install_deepscientist", install))
        if install["returncode"] != 0:
            return finish(report_dir, results, 4, "Failed to install @researai/deepscientist.")
        ds_path = shutil.which("ds")
    results["ds_path"] = ds_path
    if not ds_path:
        return finish(report_dir, results, 4, "DeepScientist CLI `ds` is missing.")

    ds_help = run(["ds", "--help"], timeout_seconds=60)
    results["steps"].append(step("ds_help", ds_help))
    if ds_help["returncode"] != 0:
        return finish(report_dir, results, 4, "`ds --help` failed.")

    probe_patch = run([sys.executable, str(ROOT / "scripts" / "patch_deepscientist_claude_probe.py")], timeout_seconds=120)
    results["steps"].append(step("patch_deepscientist_claude_probe", probe_patch))
    if probe_patch["returncode"] != 0:
        return finish(report_dir, results, 4, "Failed to patch DeepScientist Claude startup probe compatibility.")

    configure_claude = run(
        [sys.executable, str(ROOT / "scripts" / "configure_deepscientist_claude_runner.py")],
        timeout_seconds=120,
    )
    results["steps"].append(step("configure_deepscientist_claude_runner", configure_claude))
    if configure_claude["returncode"] != 0:
        return finish(report_dir, results, 4, "Failed to enable Claude runner in DeepScientist config.")

    ds_root = resolve_global_deepscientist_root()
    results["deepscientist_root"] = str(ds_root) if ds_root else ""
    if not ds_root:
        return finish(report_dir, results, 4, "Could not locate global @researai/deepscientist package root.")
    skill_install = install_skill(ds_root, force=args.force_skill)
    results["steps"].append(skill_install)
    if not skill_install["ok"]:
        return finish(report_dir, results, 5, skill_install["message"])

    if not args.skip_doctor:
        doctor = run(["ds", "doctor", "--runner", "claude"], timeout_seconds=300)
        results["steps"].append(step("ds_doctor_claude", doctor))
        if doctor["returncode"] != 0 or "Everything looks ready" not in doctor["stdout"]:
            return finish(report_dir, results, 6, "`ds doctor --runner claude` did not pass.")

    return finish(report_dir, results, 0, "Path-2 DeepScientist + Claude setup is ready.")


def resolve_global_deepscientist_root() -> Path | None:
    npm_root = run(["npm", "root", "-g"])
    if npm_root["returncode"] != 0:
        return None
    root = Path(npm_root["stdout"].strip()) / "@researai" / "deepscientist"
    if (root / "pyproject.toml").exists() and (root / "src" / "deepscientist").exists():
        return root
    return None


def install_skill(ds_root: Path, *, force: bool) -> dict[str, Any]:
    target = ds_root / "src" / "skills" / "citation-evidence-audit"
    if target.exists():
        if not force:
            return {
                "name": "install_skill",
                "ok": True,
                "message": "DeepScientist citation audit skill already installed.",
                "target": str(target),
            }
        shutil.rmtree(target)
    shutil.copytree(SKILL_SOURCE, target)
    return {
        "name": "install_skill",
        "ok": True,
        "message": "Installed DeepScientist citation audit skill.",
        "target": str(target),
    }


def run(cmd: list[str], *, timeout_seconds: int = 120) -> dict[str, Any]:
    resolved_cmd = resolve_windows_command(cmd)
    try:
        completed = subprocess.run(
            resolved_cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "cmd": resolved_cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout or "",
            "stderr": completed.stderr or "",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": resolved_cmd,
            "returncode": -1,
            "stdout": str(exc.stdout or ""),
            "stderr": f"Timed out after {timeout_seconds}s",
        }
    except OSError as exc:
        return {"cmd": resolved_cmd, "returncode": 127, "stdout": "", "stderr": str(exc)}


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


def step(name: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "ok": result["returncode"] == 0,
        "returncode": result["returncode"],
        "cmd": result["cmd"],
        "stdout_tail": tail(result["stdout"]),
        "stderr_tail": tail(result["stderr"]),
    }


def finish(report_dir: Path, results: dict[str, Any], code: int, message: str) -> int:
    results["ok"] = code == 0
    results["message"] = message
    (report_dir / "path2_setup_report.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Path-2 DeepScientist Claude Setup Report",
        "",
        f"Status: {'PASS' if code == 0 else 'FAIL'}",
        "",
        message,
        "",
        f"Report directory: `{report_dir}`",
        "",
        "## Steps",
        "",
    ]
    for item in results.get("steps", []):
        lines.append(f"- {item.get('name')}: {'PASS' if item.get('ok') else 'FAIL'}")
        if item.get("stderr_tail"):
            lines.append(f"  stderr: `{item.get('stderr_tail')}`")
    (report_dir / "path2_setup_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(message)
    print(f"Report: {report_dir / 'path2_setup_report.md'}")
    return code


def tail(text: str, limit: int = 900) -> str:
    value = " ".join(str(text or "").split())
    return value[-limit:] if len(value) > limit else value


if __name__ == "__main__":
    raise SystemExit(main())
