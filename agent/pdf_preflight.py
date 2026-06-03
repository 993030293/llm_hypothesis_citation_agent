from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.utils import clean_text, extract_declared_keywords, split_sentences, top_keywords


def preflight_pdf(pdf_path: Path, max_pages: int = 2) -> dict[str, Any]:
    """Inspect a teacher-supplied PDF before running the full workflow.

    The preflight deliberately avoids external API calls. It answers the live
    demo question: can this PDF provide enough extractable text to generate
    meaningful queries, or should the presenter switch to prepared evidence?
    """

    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    pages_checked = min(max_pages, page_count)
    page_character_counts: list[int] = []
    raw_page_texts: list[str] = []
    page_texts: list[str] = []
    for idx in range(pages_checked):
        raw = reader.pages[idx].extract_text() or ""
        text = clean_text(raw)
        raw_page_texts.append(raw)
        page_texts.append(text)
        page_character_counts.append(len(text))

    raw_text = "\n".join(raw_page_texts)
    text = clean_text(" ".join(page_texts))
    metadata_title = clean_text(getattr(reader.metadata, "title", "") if reader.metadata else "")
    title = _guess_title(text, metadata_title)
    abstract_preview = _guess_abstract(text)
    keywords = extract_declared_keywords(raw_text, limit=10) or top_keywords(
        f"{title} {abstract_preview} {text[:2500]}",
        limit=10,
    )
    risk_flags = _risk_flags(
        total_characters=len(text),
        page_count=page_count,
        pages_checked=pages_checked,
        abstract_preview=abstract_preview,
        keywords=keywords,
    )
    readiness = _readiness_from_flags(risk_flags)
    return {
        "pdf": str(pdf_path),
        "readiness": readiness,
        "page_count": page_count,
        "pages_checked": pages_checked,
        "page_character_counts": page_character_counts,
        "total_extracted_characters": len(text),
        "title_preview": title,
        "abstract_preview": abstract_preview[:700],
        "keywords_preview": keywords,
        "risk_flags": risk_flags,
        "recommended_command": recommended_live_command(pdf_path),
        "fallback_instruction": (
            "If readiness is risky, explain that the PDF appears to be scanned or metadata-poor, "
            "then show prepared logs under submission/evidence/ instead of forcing a weak live run."
        ),
    }


def recommended_live_command(pdf_path: Path) -> str:
    return (
        f'python agent/workflow.py --pdf "{pdf_path}" '
        '--task "Teacher-supplied live PDF: generate a research hypothesis and verify citations" '
        "--live-demo"
    )


def _guess_title(text: str, metadata_title: str) -> str:
    if metadata_title and metadata_title.lower() not in {"untitled", "none"}:
        return metadata_title[:240]
    for sentence in split_sentences(text[:1600], limit=6):
        sentence = clean_text(sentence)
        if 8 <= len(sentence) <= 220:
            return sentence
    return "Untitled or low-text PDF"


def _guess_abstract(text: str) -> str:
    sentences = split_sentences(text, limit=6)
    return clean_text(" ".join(sentences[:4]))[:900]


def _risk_flags(
    *,
    total_characters: int,
    page_count: int,
    pages_checked: int,
    abstract_preview: str,
    keywords: list[str],
) -> list[str]:
    flags: list[str] = []
    if total_characters < 200:
        flags.append("very_low_extractable_text")
    elif total_characters < 800:
        flags.append("limited_extractable_text")
    if not abstract_preview or len(abstract_preview) < 120:
        flags.append("weak_abstract_preview")
    if len(keywords) < 4:
        flags.append("few_keywords")
    if page_count > pages_checked and pages_checked < 3:
        flags.append("only_first_pages_checked")
    return flags


def _readiness_from_flags(flags: list[str]) -> str:
    if "very_low_extractable_text" in flags:
        return "risky"
    if "limited_extractable_text" in flags or "few_keywords" in flags:
        return "usable_with_caution"
    return "ready"
