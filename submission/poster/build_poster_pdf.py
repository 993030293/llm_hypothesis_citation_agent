from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("poster_120x80.pdf")


def draw_wrapped(c: canvas.Canvas, text: str, x: float, y: float, max_width: float, font: str, size: int, leading: int) -> float:
    c.setFont(font, size)
    words = text.split()
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if c.stringWidth(candidate, font, size) <= max_width:
            line = candidate
        else:
            c.drawString(x, y, line)
            y -= leading
            line = word
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def panel(c: canvas.Canvas, x: float, y: float, w: float, h: float, title: str, body: list[str], color: colors.Color) -> None:
    c.setFillColor(colors.white)
    c.setStrokeColor(color)
    c.setLineWidth(4)
    c.roundRect(x, y - h, w, h, 10, fill=1, stroke=1)
    c.setFillColor(color)
    c.rect(x, y - 44, w, 44, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(x + 22, y - 30, title)
    c.setFillColor(colors.HexColor("#1f2937"))
    yy = y - 76
    for item in body:
        yy = draw_wrapped(c, f"- {item}", x + 24, yy, w - 48, "Helvetica", 17, 23)
        yy -= 8


def main() -> None:
    width = 120 * cm
    height = 80 * cm
    c = canvas.Canvas(str(OUT), pagesize=(width, height))
    c.setTitle("DeepScientist-style Hypothesis and Citation Verification Agent")

    margin = 3 * cm
    c.setFillColor(colors.HexColor("#0f172a"))
    c.rect(0, 0, width, height, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 52)
    c.drawString(margin, height - margin, "DeepScientist-style Hypothesis and Citation Verification Agent")
    c.setFont("Helvetica", 24)
    c.drawString(margin, height - margin - 42, "PDF input -> literature retrieval -> research idea cards -> Green / Yellow / Red citation verification")

    col_w = (width - 2 * margin - 2 * cm) / 3
    top = height - margin - 95
    row_h = 330
    gap = 1 * cm

    panel(
        c,
        margin,
        top,
        col_w,
        row_h,
        "Problem",
        [
            "LLM research agents can generate plausible ideas with weak or fabricated citations.",
            "The project checks whether cited literature exists, matches metadata, and supports each claim.",
            "The grading evidence is the auditable tool chain, not only a chat answer.",
        ],
        colors.HexColor("#2563eb"),
    )
    panel(
        c,
        margin + col_w + gap,
        top,
        col_w,
        row_h,
        "Pipeline",
        [
            "Read first PDF pages and extract title, abstract, keywords, and research problem.",
            "Generate initial and follow-up search queries.",
            "Retrieve literature through Crossref and OpenAlex wrappers.",
            "Generate structured hypothesis cards and verify citations.",
        ],
        colors.HexColor("#7c3aed"),
    )
    panel(
        c,
        margin + 2 * (col_w + gap),
        top,
        col_w,
        row_h,
        "Self-built Tools",
        [
            "PDF reader, query planner, literature searcher, evidence store, hypothesis generator, verifier, report writer, QQ command adapter.",
            "Every run writes tool_calls.jsonl, retrieved_literature.jsonl, citation_verification.csv, and final_report.md.",
        ],
        colors.HexColor("#0891b2"),
    )

    second_top = top - row_h - gap
    panel(
        c,
        margin,
        second_top,
        col_w,
        row_h,
        "Label Rules",
        [
            "Green: exists, metadata matches, and abstract or snippet directly supports the claim.",
            "Yellow: exists, but support is partial, weak, abstract-only, or needs human inspection.",
            "Red: missing paper, invalid DOI, metadata mismatch, or unsupported claim.",
        ],
        colors.HexColor("#16a34a"),
    )
    panel(
        c,
        margin + col_w + gap,
        second_top,
        col_w,
        row_h,
        "Demo Results",
        [
            "Success case: submission/evidence/success_case, observed Green 3, Yellow 1, Red 0.",
            "Boundary case: submission/evidence/boundary_case, observed Green 0, Yellow 1, Red 1.",
            "The Red row is intentionally invalid and demonstrates rejection of bad citations.",
        ],
        colors.HexColor("#dc2626"),
    )
    panel(
        c,
        margin + 2 * (col_w + gap),
        second_top,
        col_w,
        row_h,
        "Reproducibility",
        [
            "Run python -m pytest -q.",
            "Run workflow.py on success_demo.pdf and boundary_demo.pdf.",
            "Inspect tool_calls.jsonl, retrieved_literature.jsonl, citation_verification.csv, and final_report.md.",
        ],
        colors.HexColor("#ca8a04"),
    )

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 30)
    c.drawString(margin, margin + 55, "Core message")
    c.setFont("Helvetica", 21)
    c.drawString(
        margin,
        margin + 20,
        "The system favors conservative, auditable verification: uncertain citation support stays Yellow instead of becoming false Green.",
    )

    c.save()


if __name__ == "__main__":
    main()
