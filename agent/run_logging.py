from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from agent.utils import clean_text, now_iso


class ToolCallLogger:
    """Append-only tool call log for grading and live demos."""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.path = run_dir / "tool_calls.jsonl"
        self._counter = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def next_id(self) -> str:
        self._counter += 1
        return f"T{self._counter:03d}"

    def log(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        inputs: dict[str, Any],
        status: str,
        output_summary: str,
        started_at: float,
        outputs: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        row = {
            "tool_call_id": tool_call_id,
            "timestamp": now_iso(),
            "tool_name": tool_name,
            "inputs": inputs,
            "status": status,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "output_summary": clean_text(output_summary)[:800],
            "outputs": outputs or {},
            "error": clean_text(error)[:800] if error else None,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class EvidenceStore:
    """Append-only evidence inventory with stable per-run evidence IDs."""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.path = run_dir / "evidence_items.jsonl"
        self._counter = 0
        self.items: list[dict[str, Any]] = []
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        source_type: str,
        source: str,
        content_snippet: str,
        category: str,
        tool_call_id: str | None = None,
        locator: str | None = None,
        url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        self._counter += 1
        evidence_id = f"E{self._counter:03d}"
        row = {
            "evidence_id": evidence_id,
            "timestamp": now_iso(),
            "source_type": source_type,
            "source": source,
            "locator": locator or "record-level",
            "url": url,
            "content_snippet": clean_text(content_snippet)[:1000],
            "category": category,
            "tool_call_id": tool_call_id,
            "metadata": metadata or {},
        }
        self.items.append(row)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return evidence_id

    def get_all(self) -> list[dict[str, Any]]:
        return list(self.items)

