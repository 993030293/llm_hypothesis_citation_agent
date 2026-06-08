#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import shutil
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download the 20 real PDFs used by the DeepScientist 20x campaign.")
    parser.add_argument("--manifest", default=str(ROOT / "inputs" / "deepscientist_20_cases" / "manifest.json"))
    parser.add_argument("--out-dir", default=str(ROOT / "inputs" / "deepscientist_20_cases" / "papers"))
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = []

    for idx, case in enumerate(manifest.get("cases", []), 1):
        case_id = case["case_id"]
        dest = out_dir / f"{case_id}.pdf"
        source = case.get("pdf_url") or case.get("pdf_path") or ""
        status, error = materialize_case_pdf(source, dest, force=args.force)
        size = dest.stat().st_size if dest.exists() else 0
        rows.append(
            {
                "index": idx,
                "case_id": case_id,
                "field": case.get("field", ""),
                "source": source,
                "local_pdf": str(dest.relative_to(ROOT)) if dest.is_relative_to(ROOT) else str(dest),
                "status": status,
                "bytes": size,
                "error": error,
            }
        )
        suffix = f", error={error}" if error else ""
        print(f"{idx:02d}/{len(manifest.get('cases', []))} {case_id}: {status}, bytes={size}{suffix}", flush=True)

    audit_path = manifest_path.parent / "download_audit.csv"
    with audit_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["index", "case_id", "field", "source", "local_pdf", "status", "bytes", "error"],
        )
        writer.writeheader()
        writer.writerows(rows)

    ok = sum(
        1
        for row in rows
        if row["status"] in {"downloaded", "skipped_existing", "copied_local", "copied_path"}
        and int(row["bytes"]) > 1000
    )
    print(f"DONE downloaded/copied usable PDFs: {ok}/{len(rows)}")
    return 0 if ok == len(rows) else 1


def materialize_case_pdf(source: str, dest: Path, *, force: bool = False) -> tuple[str, str]:
    if dest.exists() and dest.stat().st_size > 1000 and not force:
        return "skipped_existing", ""
    if source.startswith("local:"):
        return copy_local(ROOT / source[len("local:") :], dest)
    if source.startswith("http://") or source.startswith("https://"):
        return download_pdf(source, dest)
    source_path = ROOT / source
    if source_path.exists():
        return copy_local(source_path, dest)
    return "failed", f"unsupported source: {source}"


def copy_local(source: Path, dest: Path) -> tuple[str, str]:
    if not source.exists():
        return "failed", f"local source missing: {source}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return "copied_local", ""


def download_pdf(url: str, dest: Path) -> tuple[str, str]:
    headers = {"User-Agent": "llm-hypothesis-citation-agent/0.1 course project downloader"}
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=45) as response:
                data = response.read()
            if len(data) < 1000:
                raise RuntimeError(f"downloaded content is too small to be a PDF, bytes={len(data)}")
            if not data[:40].lstrip().startswith(b"%PDF") and b"<html" in data[:500].lower():
                raise RuntimeError(f"downloaded content looks like HTML, bytes={len(data)}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return "downloaded", ""
        except Exception as exc:
            if attempt < 3:
                time.sleep(2 * attempt)
                continue
            return "failed", str(exc)
    return "failed", "unknown failure"


if __name__ == "__main__":
    raise SystemExit(main())
