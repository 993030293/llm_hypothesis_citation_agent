#!/usr/bin/env python
from __future__ import annotations

"""Backward-compatible wrapper for the renamed 20-paper campaign runner."""

import sys

from scripts.deepscientist_20x_campaign import main


if __name__ == "__main__":
    print(
        "WARNING: scripts/deepscientist_15x_campaign.py is deprecated. "
        "Use scripts/deepscientist_20x_campaign.py for the current 20-paper campaign.",
        file=sys.stderr,
    )
    raise SystemExit(main())
