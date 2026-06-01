from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from agent.evidence_chain_tracer import build_evidence_chain_rows
from agent.run_logging import EvidenceStore, ToolCallLogger
from agent.utils import clean_text, now_iso, write_json, write_jsonl


CITATION_FIELDS = [
    "claim_id",
    "claim_text",
    "cited_title",
    "cited_authors",
    "cited_year",
    "doi",
    "retrieval_source",
    "exists_status",
    "metadata_match_status",
    "support_status",
    "color_label",
    "reason",
    "evidence_id",
    "url",
    "title_similarity",
    "author_match_score",
    "year_match",
    "support_score",
    "matched_evidence_text",
    "verification_method",
]


class ReportWriter:
    def __init__(self, logger: ToolCallLogger, evidence: EvidenceStore):
        self.logger = logger
        self.evidence = evidence

    def write_all(
        self,
        run_dir: Path,
        *,
        task: str,
        pdf_path: Path,
        paper_summary: dict[str, Any],
        queries: list[dict[str, Any]],
        literature: list[dict[str, Any]],
        hypothesis_payload: dict[str, Any],
        verification_rows: list[dict[str, Any]],
    ) -> None:
        call_id = self.logger.next_id()
        started = time.perf_counter()
        (run_dir / "input_task.md").write_text(
            f"# Input Task\n\nTask: {task}\n\nPDF: {pdf_path}\n\nGenerated: {now_iso()}\n",
            encoding="utf-8",
        )
        write_json(run_dir / "paper_summary.json", paper_summary)
        write_json(run_dir / "search_queries.json", {"queries": queries})
        write_jsonl(run_dir / "retrieved_literature.jsonl", literature)
        (run_dir / "generated_hypothesis.md").write_text(hypothesis_payload["markdown"], encoding="utf-8")
        write_json(run_dir / "generated_claims.json", hypothesis_payload)
        self._write_csv(run_dir / "citation_verification.csv", verification_rows)
        (run_dir / "final_report.md").write_text(
            self._render_final_report(
                task=task,
                pdf_path=pdf_path,
                paper_summary=paper_summary,
                queries=queries,
                literature=literature,
                hypotheses=hypothesis_payload.get("hypotheses", []),
                claims=hypothesis_payload.get("claims", []),
                verification_rows=verification_rows,
                evidence_items=self.evidence.get_all(),
            ),
            encoding="utf-8",
        )
        self.logger.log(
            tool_call_id=call_id,
            tool_name="report_writer.write_run_outputs",
            inputs={"run_dir": str(run_dir)},
            status="success",
            output_summary="Wrote required run artifacts including final_report.md and citation_verification.csv.",
            started_at=started,
            outputs={
                "files": [
                    "input_task.md",
                    "paper_summary.json",
                    "search_queries.json",
                    "retrieved_literature.jsonl",
                "generated_hypothesis.md",
                "citation_verification.csv",
                "evidence_chain.csv",
                "evidence_chain.md",
                "final_report.md",
                "tool_calls.jsonl",
                "evidence_items.jsonl",
                ]
            },
        )

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=CITATION_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in CITATION_FIELDS})

    def _render_final_report(
        self,
        *,
        task: str,
        pdf_path: Path,
        paper_summary: dict[str, Any],
        queries: list[dict[str, Any]],
        literature: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
        claims: list[dict[str, Any]],
        verification_rows: list[dict[str, Any]],
        evidence_items: list[dict[str, Any]],
    ) -> str:
        counts = {label: 0 for label in ("Green", "Yellow", "Red")}
        for row in verification_rows:
            counts[row.get("color_label", "Red")] = counts.get(row.get("color_label", "Red"), 0) + 1
        evidence_chain_rows = build_evidence_chain_rows(
            hypothesis_payload={"claims": claims},
            literature=literature,
            verification_rows=verification_rows,
            evidence_items=evidence_items,
            tool_calls=self._read_jsonl(self.logger.path),
        )

        lines = [
            "# Final Report",
            "",
            f"Generated: {now_iso()}",
            f"Task: {task}",
            f"Input PDF: {pdf_path}",
            "",
            "## Paper Summary",
            "",
            f"Title: {paper_summary.get('title')}",
            f"Pages read: {paper_summary.get('pages_read')} / {paper_summary.get('page_count')}",
            f"Keywords: {', '.join(paper_summary.get('keywords') or [])}",
            "",
            "Research problem:",
            "",
            clean_text(paper_summary.get("research_problem")),
            "",
            "## Toolchain Evidence",
            "",
            f"- Search queries generated: {len(queries)}",
            f"- Literature records retrieved: {len(literature)}",
            f"- Hypotheses generated: {len(hypotheses)}",
            f"- Citation-backed claims checked: {len(claims)}",
            f"- Evidence items recorded: {len(evidence_items)}",
            "",
            "Required run artifacts are in this same run directory: tool_calls.jsonl, retrieved_literature.jsonl, citation_verification.csv, and final_report.md.",
            "Evidence-chain artifacts are also written as evidence_chain.csv and evidence_chain.md.",
            "",
            "## Search Queries",
            "",
                "| Query ID | Stage | Type | Query | Purpose |",
                "|---|---|---|---|---|",
        ]
        for query in queries:
            lines.append(
                f"| {query['query_id']} | {query.get('query_stage', 'initial')} | {query.get('query_type', '')} | "
                f"{self._cell(query['query'])} | {self._cell(query['purpose'])} |"
            )

        lines.extend(["", "## Generated Research Ideas", ""])
        for hypothesis in hypotheses:
            lines.append(f"### {hypothesis['hypothesis_id']}: {hypothesis.get('idea_type', 'idea')}")
            lines.append(f"Evidence status: `{hypothesis.get('evidence_status', 'unknown')}`")
            lines.append("")
            lines.append(f"Research gap: {clean_text(hypothesis.get('research_gap'))}")
            lines.append("")
            lines.append(f"New hypothesis: {clean_text(hypothesis.get('new_hypothesis') or hypothesis.get('hypothesis_text'))}")
            lines.append("")
            lines.append(f"Risk or limitation: {clean_text(hypothesis.get('risk_or_limitation'))}")
            if hypothesis.get("citation_claim_ids"):
                lines.append(f"Citation claims: {', '.join(hypothesis.get('citation_claim_ids', []))}")
            lines.append("")

        lines.extend(
            [
                "## Citation Verification Summary",
                "",
                f"Green: {counts.get('Green', 0)}; Yellow: {counts.get('Yellow', 0)}; Red: {counts.get('Red', 0)}",
                "",
                "| Claim ID | Color | Exists | Metadata | Support | Scores | Reason | Evidence |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        for row in verification_rows:
            scores = (
                f"title={row.get('title_similarity', '')}; "
                f"author={row.get('author_match_score', '')}; "
                f"support={row.get('support_score', '')}"
            )
            lines.append(
                f"| {row.get('claim_id')} | {row.get('color_label')} | {row.get('exists_status')} | "
                f"{row.get('metadata_match_status')} | {row.get('support_status')} | "
                f"{self._cell(scores)} | {self._cell(row.get('reason', ''))} | {row.get('evidence_id')} |"
            )

        lines.extend(
            [
                "",
                "## Evidence Chain Table",
                "",
                "| Claim ID | Hypothesis | Color | Support Category | Evidence IDs | Tool Calls | Manual Review |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for row in evidence_chain_rows:
            evidence_ids = ";".join(
                item for item in [row.get("source_evidence_ids"), row.get("verification_evidence_id")] if item
            )
            lines.append(
                f"| {row.get('claim_id')} | {row.get('hypothesis_id')} | {row.get('color_label')} | "
                f"{row.get('support_category')} | {evidence_ids} | {row.get('tool_call_ids')} | "
                f"{row.get('manual_review_required')} |"
            )

        lines.extend(
            [
                "",
                "## Retrieved Literature Preview",
                "",
                "| Literature ID | Selected | Relevance | Source | Year | Title | DOI | Evidence |",
                "|---|---:|---:|---|---|---|---|---|",
            ]
        )
        for item in literature[:12]:
            lines.append(
                f"| {item.get('literature_id')} | {item.get('selected_for_hypothesis')} | "
                f"{item.get('relevance_score', '')} | {item.get('retrieval_source')} | {item.get('year') or ''} | "
                f"{self._cell(item.get('title', ''))} | {item.get('doi') or ''} | {item.get('evidence_id')} |"
            )

        lines.extend(
            [
                "",
                "## Boundary And Failure Handling",
                "",
                "- Missing DOI/title matches are labeled Red.",
                "- Existing papers with weak or abstract-only support are labeled Yellow.",
                "- Green requires both metadata match and concrete support from title/abstract/snippet.",
                "- API failures are preserved in tool_calls.jsonl and do not become fabricated evidence.",
            ]
        )
        return "\n".join(lines)

    def _cell(self, text: Any) -> str:
        return clean_text(text).replace("|", "\\|")

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
