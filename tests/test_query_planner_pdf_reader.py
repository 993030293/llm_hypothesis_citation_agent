from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from agent.pdf_reader import PdfReaderTool
from agent.fulltext_evidence import FullTextEvidenceExtractor
from agent.query_planner import QueryPlanner
from agent.run_logging import EvidenceStore, ToolCallLogger


def test_pdf_reader_and_query_planner(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    c = canvas.Canvas(str(pdf), pagesize=letter)
    c.setTitle("Evidence Grounded Hypothesis Generation")
    c.drawString(72, 720, "Evidence Grounded Hypothesis Generation")
    c.drawString(72, 700, "Abstract. This paper studies citation verification for large language models.")
    c.drawString(72, 680, "Keywords: citation verification; evidence tracking; literature search")
    c.save()

    logger = ToolCallLogger(tmp_path)
    evidence = EvidenceStore(tmp_path)
    summary = PdfReaderTool(logger, evidence).read(pdf, max_pages=1)
    queries = QueryPlanner(logger).plan(summary, max_queries=3)

    assert summary["title"]
    assert "citation" in " ".join(summary["keywords"]).lower()
    assert len(queries) >= 1
    assert (tmp_path / "tool_calls.jsonl").exists()
    assert (tmp_path / "evidence_items.jsonl").exists()


def test_pdf_reader_extracts_line_based_keywords(tmp_path: Path) -> None:
    pdf = tmp_path / "line_keywords.pdf"
    c = canvas.Canvas(str(pdf), pagesize=letter)
    c.drawString(72, 720, "EvoMarket: A High-Fidelity and Scalable Financial Market Simulator")
    c.drawString(72, 700, "ARTICLE INFO")
    c.drawString(72, 680, "Keywords:")
    c.drawString(72, 660, "Agent-based modeling")
    c.drawString(72, 640, "financial market simulation")
    c.drawString(72, 620, "calibration")
    c.drawString(72, 600, "scalability")
    c.drawString(72, 580, "multi-agent systems")
    c.drawString(72, 560, "simulation fidelity")
    c.drawString(300, 680, "ABSTRACT")
    c.drawString(300, 660, "High-fidelity market simulation supports stress testing.")
    c.save()

    logger = ToolCallLogger(tmp_path)
    evidence = EvidenceStore(tmp_path)
    summary = PdfReaderTool(logger, evidence).read(pdf, max_pages=1)

    assert summary["keywords"] == [
        "agent-based modeling",
        "financial market simulation",
        "calibration",
        "scalability",
        "multi-agent systems",
        "simulation fidelity",
    ]


def test_fulltext_evidence_extractor_records_page_sentence_rows(tmp_path: Path) -> None:
    pdf = tmp_path / "fulltext.pdf"
    c = canvas.Canvas(str(pdf), pagesize=letter)
    c.drawString(72, 720, "Evidence Grounded Hypothesis Generation")
    c.drawString(72, 700, "This paper studies citation verification for large language models.")
    c.drawString(72, 680, "Citation verification improves auditability in scientific writing workflows.")
    c.save()

    logger = ToolCallLogger(tmp_path)
    evidence = EvidenceStore(tmp_path)
    rows = FullTextEvidenceExtractor(logger, evidence).extract(pdf, max_pages=1)

    assert rows
    assert rows[0]["fulltext_evidence_id"].startswith("FT")
    assert rows[0]["page_number"] == 1
    assert rows[0]["source_location"].startswith("input_pdf page 1")
    assert (tmp_path / "tool_calls.jsonl").exists()
