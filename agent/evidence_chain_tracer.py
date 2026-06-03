from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from agent.run_logging import EvidenceStore, ToolCallLogger
from agent.utils import clean_text, now_iso


EVIDENCE_CHAIN_FIELDS = [
    "claim_id",
    "hypothesis_id",
    "claim_text",
    "cited_title",
    "color_label",
    "support_category",
    "source_evidence_ids",
    "verification_evidence_id",
    "tool_call_ids",
    "source_locations",
    "reason",
    "manual_review_required",
]


class EvidenceChainTracer:
    """Build a claim-level evidence chain table from workflow artifacts."""

    def __init__(self, logger: ToolCallLogger, evidence: EvidenceStore):
        self.logger = logger
        self.evidence = evidence

    def trace_and_write(
        self,
        run_dir: Path,
        *,
        hypothesis_payload: dict[str, Any],
        literature: list[dict[str, Any]],
        verification_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        call_id = self.logger.next_id()
        started = time.perf_counter()
        evidence_items = self.evidence.get_all()
        tool_calls = self._read_jsonl(self.logger.path)
        rows = build_evidence_chain_rows(
            hypothesis_payload=hypothesis_payload,
            literature=literature,
            verification_rows=verification_rows,
            evidence_items=evidence_items,
            tool_calls=tool_calls,
        )
        self._write_csv(run_dir / "evidence_chain.csv", rows)
        (run_dir / "evidence_chain.md").write_text(render_evidence_chain_markdown(rows), encoding="utf-8")
        evidence_id = self.evidence.record(
            source_type="evidence_chain",
            source="evidence_chain_tracer",
            content_snippet=render_evidence_chain_markdown(rows)[:1000],
            category="evidence_chain",
            tool_call_id=call_id,
            locator="evidence_chain.csv",
            metadata={"claim_count": len(rows)},
        )
        self.logger.log(
            tool_call_id=call_id,
            tool_name="evidence_chain_tracer.build_claim_evidence_chain",
            inputs={"claim_count": len(hypothesis_payload.get("claims", []))},
            status="success",
            output_summary=f"Built evidence chain for {len(rows)} claims.",
            started_at=started,
            outputs={
                "evidence_chain_csv": str(run_dir / "evidence_chain.csv"),
                "evidence_chain_md": str(run_dir / "evidence_chain.md"),
                "evidence_id": evidence_id,
            },
        )
        return rows

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=EVIDENCE_CHAIN_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in EVIDENCE_CHAIN_FIELDS})

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows


def build_evidence_chain_rows(
    *,
    hypothesis_payload: dict[str, Any],
    literature: list[dict[str, Any]],
    verification_rows: list[dict[str, Any]],
    evidence_items: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    claims = hypothesis_payload.get("claims", [])
    verification_by_claim = {row.get("claim_id"): row for row in verification_rows}
    evidence_by_id = {item.get("evidence_id"): item for item in evidence_items}
    literature_by_id = {item.get("literature_id"): item for item in literature}
    tool_by_id = {item.get("tool_call_id"): item for item in tool_calls}
    rows: list[dict[str, Any]] = []

    for claim in claims:
        cited = claim.get("cited_work") or {}
        claim_id = clean_text(claim.get("claim_id"))
        verification = verification_by_claim.get(claim_id, {})
        source_evidence_ids = _source_evidence_ids(cited, literature_by_id)
        verification_evidence_id = clean_text(verification.get("evidence_id"))
        tool_call_ids = _tool_call_ids(source_evidence_ids, verification_evidence_id, evidence_by_id, tool_by_id)
        source_locations = _source_locations(source_evidence_ids, verification_evidence_id, evidence_by_id)
        color = clean_text(verification.get("color_label")) or "Red"
        rows.append(
            {
                "claim_id": claim_id,
                "hypothesis_id": clean_text(claim.get("hypothesis_id")),
                "claim_text": clean_text(claim.get("claim_text")),
                "cited_title": clean_text(cited.get("title") or verification.get("cited_title")),
                "color_label": color,
                "support_category": support_category_from_color(color),
                "source_evidence_ids": ";".join(source_evidence_ids),
                "verification_evidence_id": verification_evidence_id,
                "tool_call_ids": ";".join(tool_call_ids),
                "source_locations": " | ".join(source_locations),
                "reason": clean_text(verification.get("reason")),
                "manual_review_required": color != "Green",
            }
        )
    return rows


def support_category_from_color(color_label: str) -> str:
    normalized = clean_text(color_label).lower()
    if normalized == "green":
        return "directly_supported"
    if normalized == "yellow":
        return "reasonable_inference_or_uncertain"
    return "insufficient_or_unsupported"


def render_evidence_chain_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Evidence Chain",
        "",
        f"Generated: {now_iso()}",
        "",
        "| Claim ID | Hypothesis | Color | Support Category | Evidence IDs | Tool Calls | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        evidence_ids = ";".join(
            item for item in [row.get("source_evidence_ids"), row.get("verification_evidence_id")] if item
        )
        lines.append(
            f"| {row.get('claim_id')} | {row.get('hypothesis_id')} | {row.get('color_label')} | "
            f"{row.get('support_category')} | {evidence_ids} | {row.get('tool_call_ids')} | "
            f"{_cell(row.get('reason'))} |"
        )
    lines.extend(
        [
            "",
            "## Category Meaning",
            "",
            "- `directly_supported`: the cited literature exists, metadata matches, and available abstract/snippet supports the claim.",
            "- `reasonable_inference_or_uncertain`: the cited literature exists, but support is partial or requires manual review.",
            "- `insufficient_or_unsupported`: the citation is missing, mismatched, or unsupported by available evidence.",
        ]
    )
    return "\n".join(lines)


def _source_evidence_ids(cited: dict[str, Any], literature_by_id: dict[str, dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    cited_evidence = clean_text(cited.get("evidence_id"))
    if cited_evidence:
        ids.append(cited_evidence)
    literature_id = cited.get("literature_id")
    literature = literature_by_id.get(literature_id)
    if literature:
        literature_evidence = clean_text(literature.get("evidence_id"))
        if literature_evidence and literature_evidence not in ids:
            ids.append(literature_evidence)
    return ids


def _tool_call_ids(
    source_evidence_ids: list[str],
    verification_evidence_id: str,
    evidence_by_id: dict[str, dict[str, Any]],
    tool_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    ids: list[str] = []
    for evidence_id in [*source_evidence_ids, verification_evidence_id]:
        item = evidence_by_id.get(evidence_id)
        tool_id = clean_text((item or {}).get("tool_call_id"))
        if tool_id and tool_id not in ids and tool_id in tool_by_id:
            ids.append(tool_id)
    return ids


def _source_locations(
    source_evidence_ids: list[str],
    verification_evidence_id: str,
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    locations: list[str] = []
    for evidence_id in [*source_evidence_ids, verification_evidence_id]:
        item = evidence_by_id.get(evidence_id)
        if not item:
            continue
        locator = clean_text(item.get("locator"))
        url = clean_text(item.get("url"))
        source = clean_text(item.get("source"))
        location = " ".join(part for part in [evidence_id, source, locator, url] if part)
        if location:
            locations.append(location)
    return locations


def _cell(text: Any) -> str:
    return clean_text(text).replace("|", "\\|")
