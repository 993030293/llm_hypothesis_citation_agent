from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from agent.research_memory import ResearchMemory
from scripts import audit_research_memory, update_research_memory


def write_case_artifacts(case_dir: Path, audit_dir: Path, review_dir: Path) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    with (audit_dir / "citation_verification.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "claim_id",
                "cited_title",
                "doi",
                "cited_year",
                "color_label",
                "error_type",
                "supporting_sentence",
                "evidence_id",
                "manual_review_action",
                "reason",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "claim_id": "C001",
                "cited_title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
                "doi": "",
                "cited_year": "2020",
                "color_label": "Yellow",
                "error_type": "supporting_sentence_missing",
                "supporting_sentence": "",
                "evidence_id": "E001",
                "manual_review_action": "Check full text.",
                "reason": "weak support " + ("s" + "k-this-secret-must-be-redacted"),
            }
        )
    (audit_dir / "provider_verification.jsonl").write_text(
        json.dumps({"provider": "openalex", "status": "exists"}) + "\n",
        encoding="utf-8",
    )
    (audit_dir / "tool_calls.jsonl").write_text(
        json.dumps({"tool_name": "openalex_lookup", "status": "success"}) + "\n",
        encoding="utf-8",
    )
    (review_dir / "reviewer_scores.jsonl").write_text(
        json.dumps({"reviewer_id": "R1", "role": "novelty_reviewer", "score_1_to_6": 4}) + "\n",
        encoding="utf-8",
    )
    (review_dir / "meta_decision.json").write_text(
        json.dumps(
            {
                "decision": "revise_before_demo",
                "final_score_1_to_6": 4,
                "must_fix_before_demo": ["Explain Yellow."],
            }
        ),
        encoding="utf-8",
    )


def test_research_memory_dedupes_citation_and_keeps_case_metadata(tmp_path: Path) -> None:
    case_dir = tmp_path / "case"
    audit_dir = case_dir / "citation_audit_ratio_final"
    review_dir = case_dir / "multi_review_ratio_final"
    memory_dir = tmp_path / "memory"
    write_case_artifacts(case_dir, audit_dir, review_dir)
    memory = ResearchMemory(memory_dir)

    status = {
        "case_id": "ai_rag_knowledge_nlp",
        "run_id": "run001",
        "case_dir": str(case_dir),
        "pdf_path_or_url": "https://arxiv.org/pdf/2005.11401",
        "quest_root": str(tmp_path / "quest"),
        "final_status": "success",
        "claims_source": "official_deepscientist",
    }
    first = memory.update_from_artifacts(
        case_dir=case_dir,
        status=status,
        citation_audit_dir=audit_dir,
        multi_review_dir=review_dir,
        updates_path=case_dir / "memory_updates.jsonl",
    )
    second = memory.update_from_artifacts(
        case_dir=case_dir,
        status=status,
        citation_audit_dir=audit_dir,
        multi_review_dir=review_dir,
        updates_path=case_dir / "memory_updates_second.jsonl",
    )

    citation_rows = memory.read("citation")
    assert len(citation_rows) == 1
    assert citation_rows[0]["case_id"] == "ai_rag_knowledge_nlp"
    assert citation_rows[0]["run_id"] == "run001"
    assert citation_rows[0]["seen_count"] == 2
    assert "Yellow" in citation_rows[0]["label_history"]
    assert "sk-this-secret" not in (memory_dir / "failure_memory.jsonl").read_text(encoding="utf-8")
    assert len(first) >= 4
    assert any(item.get("update_action") == "update" for item in second)


def test_update_research_memory_cli_accepts_explicit_dirs(tmp_path: Path, monkeypatch) -> None:
    case_dir = tmp_path / "case"
    audit_dir = case_dir / "citation_audit_ratio_final"
    review_dir = case_dir / "multi_review_ratio_final"
    memory_dir = tmp_path / "memory"
    write_case_artifacts(case_dir, audit_dir, review_dir)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_research_memory.py",
            "--case-dir",
            str(case_dir),
            "--case-id",
            "finance_finrl",
            "--run-id",
            "run002",
            "--pdf-path-or-url",
            "paper.pdf",
            "--quest-root",
            str(tmp_path / "quest"),
            "--final-status",
            "success",
            "--claims-source",
            "local_fallback_generator",
            "--citation-audit-dir",
            str(audit_dir),
            "--multi-review-dir",
            str(review_dir),
            "--memory-dir",
            str(memory_dir),
        ],
    )

    assert update_research_memory.main() == 0
    summary = json.loads((case_dir / "memory_update_summary.json").read_text(encoding="utf-8"))
    assert summary["case_id"] == "finance_finrl"
    assert summary["run_id"] == "run002"
    assert (case_dir / "memory_updates.jsonl").exists()
    assert "finance_finrl" in (memory_dir / "case_run_memory.jsonl").read_text(encoding="utf-8")


def test_memory_audit_report_is_written(tmp_path: Path) -> None:
    memory_dir = tmp_path / "memory"
    memory = ResearchMemory(memory_dir)
    memory.upsert(
        "citation",
        "title:test paper",
        {
            "memory_type": "citation_audit",
            "case_id": "case001",
            "run_id": "run001",
            "title": "Test Paper",
            "doi": "",
            "color_label": "Green",
            "error_type": "none",
        },
        merge_label_history=True,
    )
    out_dir = tmp_path / "audit"

    result = audit_research_memory.audit_memory(memory_dir=memory_dir, out_dir=out_dir)

    assert Path(result["report_path"]).exists()
    assert Path(result["csv_path"]).exists()
    report = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "Research Memory Audit" in report
    assert "Citation Label History" in report
