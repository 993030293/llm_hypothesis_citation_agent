from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from agent.run_logging import EvidenceStore, ToolCallLogger
from agent.utils import clean_text, split_sentences


class FullTextEvidenceExtractor:
    """Extract sentence-level evidence rows from an input PDF.

    This is intentionally OCR-free. Low-text or scanned PDFs are preserved as
    risky extraction cases instead of inventing evidence.
    """

    def __init__(self, logger: ToolCallLogger, evidence: EvidenceStore):
        self.logger = logger
        self.evidence = evidence

    def extract(self, pdf_path: Path, max_pages: int = 999) -> list[dict[str, Any]]:
        call_id = self.logger.next_id()
        started = time.perf_counter()
        rows: list[dict[str, Any]] = []
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(pdf_path))
            page_count = len(reader.pages)
            pages_to_read = min(max_pages, page_count)
            for page_idx in range(pages_to_read):
                raw_text = reader.pages[page_idx].extract_text() or ""
                rows.extend(self._page_rows(pdf_path, page_idx + 1, raw_text))

            extraction_quality = self._overall_quality(rows)
            evidence_id = self.evidence.record(
                source_type="pdf_fulltext",
                source=str(pdf_path),
                content_snippet=f"Extracted {len(rows)} sentence-level fulltext evidence rows.",
                category="fulltext_evidence",
                tool_call_id=call_id,
                locator=f"first {pages_to_read} pages",
                metadata={
                    "page_count": page_count,
                    "pages_read": pages_to_read,
                    "sentence_count": len(rows),
                    "extraction_quality": extraction_quality,
                },
            )
            self.logger.log(
                tool_call_id=call_id,
                tool_name="fulltext_evidence.extract_pdf_sentences",
                inputs={"pdf": str(pdf_path), "max_pages": max_pages},
                status="success",
                output_summary=(
                    f"Extracted {len(rows)} sentence-level rows from {pages_to_read}/{page_count} pages; "
                    f"quality={extraction_quality}."
                ),
                started_at=started,
                outputs={"evidence_id": evidence_id, "sentence_count": len(rows)},
            )
            return rows
        except Exception as exc:
            self.logger.log(
                tool_call_id=call_id,
                tool_name="fulltext_evidence.extract_pdf_sentences",
                inputs={"pdf": str(pdf_path), "max_pages": max_pages},
                status="error",
                output_summary="Fulltext PDF extraction failed.",
                started_at=started,
                error=str(exc),
            )
            return []

    def _page_rows(self, pdf_path: Path, page_number: int, raw_text: str) -> list[dict[str, Any]]:
        paragraphs = self._paragraphs(raw_text)
        rows: list[dict[str, Any]] = []
        sequence = 0
        for paragraph_idx, paragraph in enumerate(paragraphs, start=1):
            sentences = split_sentences(paragraph) or ([clean_text(paragraph)] if len(clean_text(paragraph)) >= 30 else [])
            for sentence_idx, sentence in enumerate(sentences, start=1):
                text = clean_text(sentence)
                if not text:
                    continue
                sequence += 1
                quality = self._text_quality(text)
                rows.append(
                    {
                        "fulltext_evidence_id": f"FT{page_number:03d}_{sequence:04d}",
                        "source_pdf": str(pdf_path),
                        "page_number": page_number,
                        "paragraph_id": f"p{page_number:03d}_{paragraph_idx:03d}",
                        "sentence_id": f"s{page_number:03d}_{paragraph_idx:03d}_{sentence_idx:03d}",
                        "text": text,
                        "char_count": len(text),
                        "extraction_quality": quality,
                        "source_location": f"input_pdf page {page_number}, paragraph {paragraph_idx}",
                    }
                )
        if not rows and clean_text(raw_text):
            text = clean_text(raw_text)[:1000]
            rows.append(
                {
                    "fulltext_evidence_id": f"FT{page_number:03d}_0001",
                    "source_pdf": str(pdf_path),
                    "page_number": page_number,
                    "paragraph_id": f"p{page_number:03d}_001",
                    "sentence_id": f"s{page_number:03d}_001_001",
                    "text": text,
                    "char_count": len(text),
                    "extraction_quality": self._text_quality(text),
                    "source_location": f"input_pdf page {page_number}, fallback text chunk",
                }
            )
        return rows

    def _paragraphs(self, raw_text: str) -> list[str]:
        normalized = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n")
        blocks = [clean_text(block) for block in re.split(r"\n\s*\n+", normalized)]
        blocks = [block for block in blocks if len(block) >= 30]
        if blocks:
            return blocks
        lines = [clean_text(line) for line in normalized.splitlines()]
        return [line for line in lines if len(line) >= 30]

    def _overall_quality(self, rows: list[dict[str, Any]]) -> str:
        if len(rows) < 3:
            return "risky"
        usable = sum(1 for row in rows if row.get("extraction_quality") == "ready")
        if usable >= max(2, len(rows) // 2):
            return "ready"
        return "usable_with_caution"

    def _text_quality(self, text: str) -> str:
        cleaned = clean_text(text)
        if len(cleaned) < 30:
            return "risky"
        alpha = sum(1 for ch in cleaned if ch.isalpha())
        ratio = alpha / max(1, len(cleaned))
        if ratio >= 0.45:
            return "ready"
        if ratio >= 0.25:
            return "usable_with_caution"
        return "risky"
