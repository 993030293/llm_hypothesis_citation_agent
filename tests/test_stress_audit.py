from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from agent.online_audit import OnlineCitationAuditor
from agent.pdf_preflight import preflight_pdf
from agent.utils import extract_declared_keywords
from scripts.stress_audit import artifact_complete, audit_extraction, expected_overlap


def test_index_terms_are_extracted_as_declared_keywords() -> None:
    text = (
        "Abstract. Retrieval augmented generation improves scientific writing.\n"
        "Index Terms: retrieval augmented generation; citation verification; large language models\n"
        "1. Introduction\n"
    )
    assert extract_declared_keywords(text) == [
        "retrieval augmented generation",
        "citation verification",
        "large language models",
    ]


def test_low_text_pdf_preflight_is_risky(tmp_path: Path) -> None:
    pdf = tmp_path / "scan_placeholder.pdf"
    c = canvas.Canvas(str(pdf), pagesize=letter)
    c.drawString(72, 720, "SCAN")
    c.save()
    result = preflight_pdf(pdf, max_pages=1)
    assert result["readiness"] == "risky"
    assert "very_low_extractable_text" in result["risk_flags"]


def test_extraction_audit_detects_keyword_overlap() -> None:
    case = {
        "case_id": "demo",
        "discipline": "cs",
        "layout_type": "index_terms_style",
        "expected_keyword_source": "declared",
        "expected_readiness": "ready",
        "expected_keywords": ["citation verification", "large language models"],
    }
    preflight = {"readiness": "ready", "risk_flags": []}
    paper_summary = {
        "title": "Demo",
        "abstract": "This paper studies citation verification.",
        "keywords": ["citation verification", "large language models"],
    }
    row = audit_extraction(case, preflight, paper_summary)
    assert row["keyword_source"] == "declared"
    assert row["expected_keywords_overlap"] == 1.0
    assert row["failure_category"] == ""


def test_artifact_complete_reports_missing_files(tmp_path: Path) -> None:
    (tmp_path / "input_task.md").write_text("x", encoding="utf-8")
    status = artifact_complete(tmp_path)
    assert status["complete"] is False
    assert "final_report.md" in status["missing"]


def test_online_audit_classification_is_independent_of_original_label() -> None:
    auditor = OnlineCitationAuditor()
    row = {
        "claim_id": "C001",
        "claim_text": "Prior work reports that retrieval augmented generation improves factual grounding.",
        "cited_title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "cited_authors": "Patrick Lewis",
        "cited_year": "2020",
        "doi": "10.0000/example",
        "color_label": "Yellow",
    }
    candidate = {
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "authors": ["Patrick Lewis"],
        "year": 2020,
        "abstract": "Retrieval augmented generation improves factual grounding by combining models with retrieved passages.",
    }
    audit = auditor._classify(row, "fixture", candidate, [])
    assert audit["audited_color"] == "Green"
    assert audit["agreement_status"] == "manual_review_recommended"


def test_expected_overlap_for_missing_expected_keywords() -> None:
    assert expected_overlap([], ["fallback keyword"]) == 1.0
