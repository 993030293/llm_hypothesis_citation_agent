from __future__ import annotations

from pathlib import Path

from agent.pdf_preflight import preflight_pdf, recommended_live_command


ROOT = Path(__file__).resolve().parents[1]


def test_preflight_demo_pdf_is_ready_or_usable() -> None:
    result = preflight_pdf(ROOT / "inputs" / "papers" / "success_demo.pdf", max_pages=2)
    assert result["readiness"] in {"ready", "usable_with_caution"}
    assert result["total_extracted_characters"] > 200
    assert result["keywords_preview"]
    assert "--live-demo" in result["recommended_command"]


def test_recommended_live_command_quotes_pdf_path() -> None:
    pdf_path = Path("C:/tmp/teacher paper.pdf")
    command = recommended_live_command(pdf_path)
    assert str(pdf_path) in command
    assert "--live-demo" in command
