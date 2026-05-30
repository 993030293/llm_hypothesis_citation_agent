from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from agent.run_logging import EvidenceStore, ToolCallLogger
from agent.utils import clean_text, extract_declared_keywords, split_sentences, top_keywords


class PdfReaderTool:
    """Extract the first pages of a PDF and derive a compact paper summary."""

    def __init__(self, logger: ToolCallLogger, evidence: EvidenceStore):
        self.logger = logger
        self.evidence = evidence

    def read(self, pdf_path: Path, max_pages: int = 3) -> dict[str, Any]:
        call_id = self.logger.next_id()
        started = time.perf_counter()
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(pdf_path))
            page_count = len(reader.pages)
            pages_to_read = min(max_pages, page_count)
            raw_page_texts: list[str] = []
            for idx in range(pages_to_read):
                raw_page_texts.append(reader.pages[idx].extract_text() or "")

            raw_text = "\n".join(raw_page_texts)
            text = clean_text(raw_text)
            metadata_title = clean_text(getattr(reader.metadata, "title", "") if reader.metadata else "")
            title = self._extract_title(raw_text, metadata_title)
            abstract = self._extract_abstract(raw_text)
            keywords = self._extract_keywords(raw_text, title, abstract)
            research_problem = self._extract_research_problem(text, title)
            summary = {
                "source_pdf": str(pdf_path),
                "title": title,
                "abstract": abstract,
                "keywords": keywords,
                "research_problem": research_problem,
                "page_count": page_count,
                "pages_read": pages_to_read,
                "text_excerpt": text[:4000],
                "extraction_warning": "" if text else "No extractable text found in first pages.",
            }
            evidence_id = self.evidence.record(
                source_type="pdf",
                source=str(pdf_path),
                content_snippet=f"{title}\n\n{abstract or text[:800]}",
                category="input_pdf_summary",
                tool_call_id=call_id,
                locator=f"first {pages_to_read} pages",
                metadata={"title": title, "keywords": keywords},
            )
            summary["evidence_id"] = evidence_id
            self.logger.log(
                tool_call_id=call_id,
                tool_name="pdf_reader.extract_first_pages",
                inputs={"pdf": str(pdf_path), "max_pages": max_pages},
                status="success",
                output_summary=f"Extracted {pages_to_read}/{page_count} pages; title={title}",
                started_at=started,
                outputs={"evidence_id": evidence_id, "characters": len(text)},
            )
            return summary
        except Exception as exc:
            self.logger.log(
                tool_call_id=call_id,
                tool_name="pdf_reader.extract_first_pages",
                inputs={"pdf": str(pdf_path), "max_pages": max_pages},
                status="error",
                output_summary="PDF extraction failed",
                started_at=started,
                error=str(exc),
            )
            raise

    def _extract_title(self, text: str, metadata_title: str) -> str:
        if metadata_title and metadata_title.lower() not in {"untitled", "none"}:
            return metadata_title[:240]
        for line in re.split(r"[\n\r]+|(?<=\.)\s{2,}", text[:1500]):
            line = clean_text(line)
            if 8 <= len(line) <= 220 and not line.lower().startswith("abstract"):
                return line
        return "Untitled PDF"

    def _extract_abstract(self, text: str) -> str:
        match = re.search(
            r"\babstract\b[:\s.-]*(.*?)(?:\bkeywords?\b|\b1\.?\s+introduction\b|\bintroduction\b)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            return clean_text(match.group(1))[:1800]
        sentences = split_sentences(text, limit=6)
        return clean_text(" ".join(sentences[:4]))[:1400]

    def _extract_keywords(self, text: str, title: str, abstract: str) -> list[str]:
        declared = extract_declared_keywords(text, limit=12)
        if declared:
            return declared
        match = re.search(
            r"\bkey\s*words?\b[:\s.-]*(.*?)(?:\babstract\b|\barticle\s+info\b|\b1\.?\s+introduction\b|\bintroduction\b|$)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            raw = re.split(r"[,;|]", clean_text(match.group(1))[:500])
            words = [item.strip().lower() for item in raw if 3 <= len(item.strip()) <= 60]
            if words:
                return words[:12]
        return top_keywords(f"{title} {abstract} {text[:2500]}", limit=12)

    def _extract_research_problem(self, text: str, title: str) -> str:
        signals = (
            "challenge",
            "problem",
            "gap",
            "we propose",
            "this paper",
            "aim",
            "hypothesis",
            "investigate",
            "question",
        )
        selected: list[str] = []
        for sentence in split_sentences(text):
            lower = sentence.lower()
            if any(signal in lower for signal in signals):
                selected.append(sentence)
            if len(selected) >= 2:
                break
        if selected:
            return clean_text(" ".join(selected))[:1000]
        return f"Investigate extensions and related evidence around: {title}"
