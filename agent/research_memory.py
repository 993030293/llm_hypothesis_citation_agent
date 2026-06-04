from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MEMORY_DIR = ROOT / "outputs" / "memory"


MEMORY_FILES = {
    "citation": ("citation_audit_memory.jsonl", "M_CIT"),
    "provider": ("provider_reliability_memory.jsonl", "M_PROV"),
    "reviewer": ("reviewer_decision_memory.jsonl", "M_REV"),
    "failure": ("failure_memory.jsonl", "M_FAIL"),
    "case": ("case_run_memory.jsonl", "M_CASE"),
}


class ResearchMemory:
    """Persistent JSONL memory for citation audit campaigns.

    The memory is intentionally file-based so it can be inspected during a course
    demo. Citation/provider/case/failure memories are upserted by stable keys;
    reviewer memories remain append-only because each review panel is useful
    historical evidence.
    """

    def __init__(self, memory_dir: Path | str = DEFAULT_MEMORY_DIR) -> None:
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def update_from_artifacts(
        self,
        *,
        case_dir: Path | str,
        status: dict[str, Any],
        citation_audit_dir: Path | str,
        multi_review_dir: Path | str | None = None,
        updates_path: Path | str | None = None,
    ) -> list[dict[str, Any]]:
        case_dir = Path(case_dir)
        audit_dir = Path(citation_audit_dir)
        review_dir = Path(multi_review_dir) if multi_review_dir else None
        status = normalize_status(status, case_dir)

        citation_rows = load_csv(audit_dir / "citation_verification.csv")
        provider_rows = load_jsonl(audit_dir / "provider_verification.jsonl")
        tool_rows = load_jsonl(audit_dir / "tool_calls.jsonl")
        meta = load_json((review_dir / "meta_decision.json") if review_dir else Path())
        reviewer_rows = load_jsonl((review_dir / "reviewer_scores.jsonl") if review_dir else Path())

        updates: list[dict[str, Any]] = []
        updates.extend(self.write_citation_memory(status, citation_rows))
        updates.extend(self.write_provider_memory(status, provider_rows, tool_rows))
        updates.extend(self.write_reviewer_memory(status, reviewer_rows, meta))
        updates.extend(self.write_failure_memory(status, citation_rows))
        updates.extend(self.write_case_memory(status, citation_rows, meta))

        if updates_path:
            write_jsonl(Path(updates_path), updates)
        return updates

    def write_citation_memory(self, status: dict[str, Any], rows: list[dict[str, str]]) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        for row in rows:
            title = row.get("cited_title", "")
            doi = row.get("doi", "")
            key = citation_memory_key(title=title, doi=doi)
            entry = {
                "memory_type": "citation_audit",
                "memory_key": key,
                "case_id": status.get("case_id", ""),
                "run_id": status.get("run_id", ""),
                "claim_id": row.get("claim_id", ""),
                "title": title,
                "doi": doi,
                "year": row.get("cited_year", ""),
                "color_label": row.get("color_label", ""),
                "error_type": row.get("error_type", ""),
                "supporting_sentence": row.get("supporting_sentence", "") or row.get("matched_evidence_text", ""),
                "evidence_id": row.get("evidence_id", ""),
                "manual_review_action": row.get("manual_review_action", ""),
                "source_case_dir": status.get("case_dir", ""),
            }
            updates.append(self.upsert("citation", key, entry, merge_label_history=True))
        return updates

    def write_provider_memory(
        self,
        status: dict[str, Any],
        provider_rows: list[dict[str, Any]],
        tool_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        provider_counts: dict[str, dict[str, int]] = {}
        for row in provider_rows:
            provider = str(row.get("provider") or row.get("retrieval_source") or "unknown")
            state = str(row.get("status") or row.get("exists_status") or "unknown")
            provider_counts.setdefault(provider, {})
            provider_counts[provider][state] = provider_counts[provider].get(state, 0) + 1

        tool_errors = [
            row
            for row in tool_rows
            if str(row.get("status") or "").lower() in {"error", "failed", "timeout"} or row.get("error")
        ]
        for provider, counts in sorted(provider_counts.items()):
            key = "|".join([provider, str(status.get("case_id", "")), str(status.get("run_id", ""))])
            entry = {
                "memory_type": "provider_reliability",
                "memory_key": key,
                "case_id": status.get("case_id", ""),
                "run_id": status.get("run_id", ""),
                "provider": provider,
                "counts": counts,
                "tool_error_count": len(tool_errors),
                "source_case_dir": status.get("case_dir", ""),
            }
            updates.append(self.upsert("provider", key, entry))
        return updates

    def write_reviewer_memory(
        self,
        status: dict[str, Any],
        reviewer_rows: list[dict[str, Any]],
        meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not reviewer_rows and not meta:
            return []
        entry = {
            "memory_type": "reviewer_decision",
            "case_id": status.get("case_id", ""),
            "run_id": status.get("run_id", ""),
            "reviewer_scores": [
                {
                    "reviewer_id": row.get("reviewer_id", ""),
                    "role": row.get("role", ""),
                    "score_1_to_6": row.get("score_1_to_6", ""),
                    "model": row.get("model", ""),
                    "review_source": row.get("review_source", ""),
                }
                for row in reviewer_rows
            ],
            "meta_decision": meta.get("decision", ""),
            "final_score_1_to_6": meta.get("final_score_1_to_6", ""),
            "must_fix_before_demo": meta.get("must_fix_before_demo", []),
            "source_case_dir": status.get("case_dir", ""),
        }
        return [self.append("reviewer", entry)]

    def write_failure_memory(self, status: dict[str, Any], rows: list[dict[str, str]]) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        failure_type = status.get("failure_type", "")
        if failure_type:
            key = "|".join([str(status.get("case_id", "")), str(status.get("run_id", "")), str(failure_type)])
            entry = {
                "memory_type": "case_failure",
                "memory_key": key,
                "case_id": status.get("case_id", ""),
                "run_id": status.get("run_id", ""),
                "failure_type": failure_type,
                "failure_reason": status.get("failure_reason", ""),
                "source_case_dir": status.get("case_dir", ""),
            }
            updates.append(self.upsert("failure", key, entry))

        for row in rows:
            label = row.get("color_label", "")
            if label in {"Yellow", "Red"}:
                key = "|".join(
                    [
                        str(status.get("case_id", "")),
                        str(status.get("run_id", "")),
                        str(row.get("claim_id", "")),
                        label,
                    ]
                )
                entry = {
                    "memory_type": "citation_risk",
                    "memory_key": key,
                    "case_id": status.get("case_id", ""),
                    "run_id": status.get("run_id", ""),
                    "claim_id": row.get("claim_id", ""),
                    "color_label": label,
                    "error_type": row.get("error_type", ""),
                    "reason": row.get("reason", ""),
                    "source_case_dir": status.get("case_dir", ""),
                }
                updates.append(self.upsert("failure", key, entry))
        return updates

    def write_case_memory(
        self,
        status: dict[str, Any],
        rows: list[dict[str, str]],
        meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        counts = {"Green": 0, "Yellow": 0, "Red": 0}
        for row in rows:
            label = row.get("color_label", "")
            if label in counts:
                counts[label] += 1
        key = "|".join([str(status.get("case_id", "")), str(status.get("run_id", ""))])
        entry = {
            "memory_type": "case_run",
            "memory_key": key,
            "case_id": status.get("case_id", ""),
            "run_id": status.get("run_id", ""),
            "paper": status.get("pdf_path_or_url", ""),
            "quest_root": status.get("quest_root", ""),
            "case_dir": status.get("case_dir", ""),
            "final_status": status.get("final_status", ""),
            "claims_source": status.get("claims_source", ""),
            "green": counts["Green"],
            "yellow": counts["Yellow"],
            "red": counts["Red"],
            "multi_review_decision": meta.get("decision", ""),
            "multi_review_score": meta.get("final_score_1_to_6", ""),
        }
        return [self.upsert("case", key, entry)]

    def lookup_citations(self, rows: list[dict[str, str]], limit: int = 20) -> list[dict[str, Any]]:
        citation_entries = self.read("citation")
        wanted = {citation_memory_key(title=row.get("cited_title", ""), doi=row.get("doi", "")) for row in rows}
        hits: list[dict[str, Any]] = []
        for entry in citation_entries:
            if entry.get("memory_key") in wanted:
                hits.append(
                    {
                        "memory_id": entry.get("memory_id", ""),
                        "memory_key": entry.get("memory_key", ""),
                        "title": entry.get("title", ""),
                        "doi": entry.get("doi", ""),
                        "latest_color_label": entry.get("latest_color_label", entry.get("color_label", "")),
                        "label_history": entry.get("label_history", []),
                        "error_type": entry.get("error_type", ""),
                        "seen_count": entry.get("seen_count", 1),
                    }
                )
        return hits[:limit]

    def summarize_for_review(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        hits = self.lookup_citations(rows, limit=20)
        provider_entries = self.read("provider")
        failure_entries = self.read("failure")
        provider_error_count = sum(int(entry.get("tool_error_count") or 0) for entry in provider_entries)
        return {
            "citation_hits": hits,
            "citation_hit_count": len(hits),
            "provider_memory_count": len(provider_entries),
            "provider_tool_error_count": provider_error_count,
            "failure_memory_count": len(failure_entries),
        }

    def audit_quality(self) -> dict[str, Any]:
        report: dict[str, Any] = {}
        for memory_type in MEMORY_FILES:
            rows = self.read(memory_type)
            missing_case = sum(1 for row in rows if not row.get("case_id"))
            missing_run = sum(1 for row in rows if not row.get("run_id"))
            missing_doi = sum(1 for row in rows if row.get("memory_type") == "citation_audit" and not row.get("doi"))
            report[memory_type] = {
                "entries": len(rows),
                "missing_case_id": missing_case,
                "missing_run_id": missing_run,
                "missing_doi": missing_doi,
            }
        return report

    def append(self, memory_type: str, entry: dict[str, Any]) -> dict[str, Any]:
        filename, prefix = MEMORY_FILES[memory_type]
        path = self.memory_dir / filename
        rows = self.read(memory_type)
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        safe_entry = redact_secrets({**entry})
        safe_entry.setdefault("memory_id", next_memory_id(rows, prefix))
        safe_entry.setdefault("created_at", now)
        safe_entry["updated_at"] = now
        rows.append(safe_entry)
        write_jsonl(path, rows)
        safe_entry["update_action"] = "append"
        return safe_entry

    def upsert(
        self,
        memory_type: str,
        key: str,
        entry: dict[str, Any],
        *,
        merge_label_history: bool = False,
    ) -> dict[str, Any]:
        filename, prefix = MEMORY_FILES[memory_type]
        path = self.memory_dir / filename
        rows = self.read(memory_type)
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        safe_entry = redact_secrets({**entry, "memory_key": key})

        for index, existing in enumerate(rows):
            if existing.get("memory_key") == key:
                merged = {**existing, **safe_entry}
                merged["memory_id"] = existing.get("memory_id") or next_memory_id(rows, prefix)
                merged["created_at"] = existing.get("created_at") or now
                merged["updated_at"] = now
                merged["seen_count"] = int(existing.get("seen_count") or 1) + 1
                merged["source_case_dirs"] = merge_unique_list(
                    existing.get("source_case_dirs", []),
                    existing.get("source_case_dir"),
                    safe_entry.get("source_case_dir"),
                )
                if merge_label_history:
                    merged["label_history"] = merge_unique_list(
                        existing.get("label_history", []),
                        existing.get("latest_color_label") or existing.get("color_label"),
                        safe_entry.get("color_label"),
                    )
                    merged["latest_color_label"] = safe_entry.get("color_label", "")
                rows[index] = merged
                write_jsonl(path, rows)
                merged["update_action"] = "update"
                return merged

        safe_entry.setdefault("memory_id", next_memory_id(rows, prefix))
        safe_entry.setdefault("created_at", now)
        safe_entry["updated_at"] = now
        safe_entry["seen_count"] = 1
        safe_entry["source_case_dirs"] = merge_unique_list([], safe_entry.get("source_case_dir"))
        if merge_label_history:
            safe_entry["label_history"] = merge_unique_list([], safe_entry.get("color_label"))
            safe_entry["latest_color_label"] = safe_entry.get("color_label", "")
        rows.append(safe_entry)
        write_jsonl(path, rows)
        safe_entry["update_action"] = "append"
        return safe_entry

    def read(self, memory_type: str) -> list[dict[str, Any]]:
        filename, _prefix = MEMORY_FILES[memory_type]
        return load_jsonl(self.memory_dir / filename)


def normalize_status(status: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    normalized = {**(status or {})}
    normalized.setdefault("case_dir", str(case_dir))
    return normalized


def citation_memory_key(*, title: str, doi: str) -> str:
    doi_value = str(doi or "").strip().lower()
    if doi_value:
        return f"doi:{doi_value}"
    return f"title:{normalize_title(title)}"


def normalize_title(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())
    return " ".join(text.split())


def next_memory_id(rows: list[dict[str, Any]], prefix: str) -> str:
    max_seen = 0
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    for row in rows:
        match = pattern.match(str(row.get("memory_id", "")))
        if match:
            max_seen = max(max_seen, int(match.group(1)))
    return f"{prefix}_{max_seen + 1:04d}"


def merge_unique_list(values: Any, *more_values: Any) -> list[Any]:
    result: list[Any] = []
    for value in [values, *more_values]:
        if isinstance(value, list):
            candidates = value
        elif value in (None, ""):
            candidates = []
        else:
            candidates = [value]
        for candidate in candidates:
            if candidate not in result and candidate not in (None, ""):
                result.append(candidate)
    return result


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(redact_secrets(row), ensure_ascii=False) + "\n")


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: redact_secrets(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"sk-[A-Za-z0-9_-]{12,}", "sk-***REDACTED***", value)
    return value
