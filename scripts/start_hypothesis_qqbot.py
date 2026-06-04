#!/usr/bin/env python
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAPCAT_ROOT = ROOT.parent / "qqbot-agent" / "napcat" / "napcat_app"
CREATE_NEW_CONSOLE = 0x00000010


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the hypothesis QQ bot and optionally NapCat.")
    parser.add_argument("--port", type=int, default=3002)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--start-napcat", action="store_true", help="Also start NapCat from qqbot-agent/napcat.")
    parser.add_argument("--napcat-root", default=str(DEFAULT_NAPCAT_ROOT))
    parser.add_argument("--same-window", action="store_true", help="Run bot in the current console for debugging.")
    return parser.parse_args()


def start_bot(args: argparse.Namespace) -> subprocess.Popen | None:
    cmd = [
        sys.executable,
        str(ROOT / "qqbot" / "main.py"),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--debug",
    ]
    if args.same_window:
        subprocess.run(cmd, cwd=str(ROOT), check=False)
        return None
    return subprocess.Popen(cmd, cwd=str(ROOT), creationflags=CREATE_NEW_CONSOLE)


def start_napcat(args: argparse.Namespace) -> subprocess.Popen | None:
    napcat_root = Path(args.napcat_root)
    node = napcat_root / "node.exe"
    index = napcat_root / "index.js"
    if not node.exists() or not index.exists():
        print(f"NapCat not found at {napcat_root}")
        print("Start NapCat manually from C:\\Users\\99303\\git\\qqbot-agent if needed.")
        return None
    return subprocess.Popen([str(node), str(index)], cwd=str(napcat_root), creationflags=CREATE_NEW_CONSOLE)


def main() -> int:
    args = parse_args()
    print(f"[1/2] Starting hypothesis QQ bot on ws://{args.host}:{args.port}")
    start_bot(args)
    time.sleep(1)
    if args.start_napcat:
        print("[2/2] Starting NapCat from qqbot-agent")
        start_napcat(args)
    else:
        print("[2/2] NapCat not started. Configure/start NapCat manually.")
    print("")
    print("QQ commands:")
    print('/official "C:\\Users\\99303\\Desktop\\paper.pdf"')
    print('/local "C:\\Users\\99303\\Desktop\\paper.pdf"')
    print("")
    print("If the PDF path contains spaces, keep the quotes.")
    print("")
    print("NapCat reverse WebSocket should connect to:")
    print(f"ws://{args.host}:{args.port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
