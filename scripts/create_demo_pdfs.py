from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = ROOT / "inputs" / "papers"


def draw_wrapped(c: canvas.Canvas, text: str, x: int, y: int, width_chars: int = 92, line_height: int = 14) -> int:
    words = text.split()
    line: list[str] = []
    for word in words:
        candidate = " ".join([*line, word])
        if len(candidate) > width_chars:
            c.drawString(x, y, " ".join(line))
            y -= line_height
            line = [word]
        else:
            line.append(word)
    if line:
        c.drawString(x, y, " ".join(line))
        y -= line_height
    return y


def write_pdf(path: Path, title: str, paragraphs: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle(title)
    width, height = letter
    x = 54
    y = int(height) - 60
    c.setFont("Helvetica-Bold", 14)
    y = draw_wrapped(c, title, x, y, width_chars=78, line_height=17)
    y -= 8
    c.setFont("Helvetica", 10)
    for paragraph in paragraphs:
        if y < 90:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = int(height) - 60
        y = draw_wrapped(c, paragraph, x, y)
        y -= 8
    c.save()


def main() -> None:
    write_pdf(
        PAPER_DIR / "success_demo.pdf",
        "Retrieval Augmented Generation for Evidence Grounded Scientific Writing",
        [
            "Abstract. Large language models can produce fluent scientific prose, but they often fail to ground claims in verifiable sources. This paper investigates retrieval augmented generation, citation verification, and evidence tracking as a workflow for improving factual grounding in scientific writing.",
            "Keywords: retrieval augmented generation; large language models; citation verification; scientific writing; evidence tracking",
            "Introduction. The research problem is that generated scientific hypotheses need both creative synthesis and careful reference checking. We propose studying whether a tool-based workflow can retrieve related literature, generate conservative research ideas, and label citations according to whether public metadata and abstracts support the claim.",
            "The expected contribution is an auditable pipeline that logs tool calls, stores retrieved literature, and produces a citation verification table for human review.",
        ],
    )
    write_pdf(
        PAPER_DIR / "boundary_demo.pdf",
        "Ambiguous Cross Domain Hypothesis Generation with Citation Risk",
        [
            "Abstract. Cross domain hypothesis generation often combines partial signals from multiple disciplines. This creates a risk that a system may cite papers that exist but only weakly support the generated claim, or cite papers that cannot be found at all.",
            "Keywords: hypothesis generation; citation risk; metadata matching; literature search; boundary cases",
            "Introduction. The research problem is how to expose uncertain support and incorrect references during a live demonstration. This demo input is designed to be used with the workflow flag that injects one deliberately invalid citation, so the final verification table should include a Red row.",
            "The goal is not to fabricate evidence. The invalid reference is explicitly labeled as a boundary case and should be rejected by the verifier.",
        ],
    )
    print(f"Wrote demo PDFs to {PAPER_DIR}")


if __name__ == "__main__":
    main()

