#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.pdf_preflight import preflight_pdf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preflight a teacher-supplied PDF before the live demo workflow.")
    parser.add_argument("pdf", help="PDF path supplied during the classroom demo")
    parser.add_argument("--max-pages", type=int, default=2, help="Pages to inspect without external API calls")
    parser.add_argument("--json", action="store_true", help="Print the full preflight result as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pdf_path = Path(args.pdf)
    if not pdf_path.is_absolute():
        pdf_path = (Path.cwd() / pdf_path).resolve()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    result = preflight_pdf(pdf_path, max_pages=args.max_pages)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print("Live PDF preflight")
    print(f"PDF: {result['pdf']}")
    print(f"Readiness: {result['readiness']}")
    print(f"Pages checked: {result['pages_checked']} / {result['page_count']}")
    print(f"Extracted characters: {result['total_extracted_characters']}")
    print(f"Title preview: {result['title_preview']}")
    print(f"Keywords preview: {', '.join(result['keywords_preview'])}")
    print(f"Risk flags: {', '.join(result['risk_flags']) or 'none'}")
    print("")
    print("Recommended live command:")
    print(result["recommended_command"])
    if result["readiness"] == "risky":
        print("")
        print("Fallback:")
        print(result["fallback_instruction"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
