from __future__ import annotations

from agent.qq_demo_bridge import parse_message


def test_parse_qq_message_resolves_pdf_and_flags() -> None:
    pdf_path, flags = parse_message("/hypothesis inputs/papers/success_demo.pdf --bad --no-followup")
    assert pdf_path.name == "success_demo.pdf"
    assert "--inject-bad-citation" in flags
    assert "--disable-followup" in flags

