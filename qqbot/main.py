#!/usr/bin/env python
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qqbot.bot import HypothesisQQBot, QQBotSettings, parse_args
from qqbot.utils import setup_logging


def main() -> None:
    args = parse_args()
    setup_logging(
        level="DEBUG" if args.debug else "INFO",
        log_file=str(ROOT / "qqbot_logs" / "hypothesis_bot.log"),
    )
    bot = HypothesisQQBot(
        QQBotSettings(
            host=args.host,
            port=args.port,
            bot_name=args.bot_name,
            auto_respond_group=args.auto_respond_group,
        )
    )
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("Hypothesis QQ bot stopped.")


if __name__ == "__main__":
    main()
