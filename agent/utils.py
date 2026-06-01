from __future__ import annotations

import html
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable


STOPWORDS = {
    "about",
    "above",
    "across",
    "after",
    "again",
    "against",
    "also",
    "among",
    "analysis",
    "based",
    "because",
    "between",
    "could",
    "data",
    "does",
    "during",
    "each",
    "and",
    "are",
    "but",
    "can",
    "effect",
    "for",
    "from",
    "have",
    "into",
    "large",
    "many",
    "method",
    "methods",
    "model",
    "models",
    "more",
    "most",
    "paper",
    "present",
    "research",
    "result",
    "results",
    "show",
    "shows",
    "study",
    "such",
    "than",
    "that",
    "the",
    "their",
    "there",
    "these",
    "this",
    "was",
    "through",
    "using",
    "were",
    "when",
    "where",
    "which",
    "while",
    "with",
    "within",
    "would",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def configure_utf8_stdio() -> None:
    """Prefer UTF-8 console output for PDF titles and metadata on Windows."""

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def timestamp_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(clean_text(item) for item in value)
    text = str(value)
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\u00ad", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_title(title: str) -> str:
    text = clean_text(title).lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def similarity(left: str, right: str) -> float:
    left_norm = normalize_title(left)
    right_norm = normalize_title(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", clean_text(text).lower())
    cleaned: list[str] = []
    for token in tokens:
        token = token.strip("-")
        if len(token) < 3 or token in STOPWORDS:
            continue
        cleaned.append(token)
    return cleaned


def top_keywords(text: str, limit: int = 12) -> list[str]:
    counts = Counter(tokenize(text))
    return [token for token, _count in counts.most_common(limit)]


def extract_declared_keywords(text: str, limit: int = 12) -> list[str]:
    """Extract an explicit Keywords block from raw PDF text when present.

    Many two-column papers extract as:
    ``Keywords:\nterm one\nterm two\nABSTRACT``.
    IEEE-style papers often use ``Index Terms`` instead.
    Keeping this parser line-aware prevents the abstract from being treated as
    keyword text.
    """

    raw_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    line_block = _keyword_block_from_lines(raw_text)
    if line_block:
        items = _keyword_items_from_block(line_block)
        if items:
            return items[:limit]

    compact = clean_text(raw_text)
    match = re.search(
        r"\b(?:key\s*words?|index\s+terms?)\b[:\s.-]*(.*?)(?:\babstract\b|\barticle\s+info\b|\b1\.?\s+introduction\b|\bintroduction\b|$)",
        compact,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    items = _keyword_items_from_block(match.group(1))
    return items[:limit]


def _keyword_block_from_lines(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    capture = False
    captured: list[str] = []
    for line in lines:
        cleaned = clean_text(line)
        if not cleaned:
            if capture and captured:
                break
            continue
        lower = cleaned.lower()
        if not capture:
            match = re.match(r"^(?:key\s*words?|index\s+terms?)\s*[:.-]?\s*(.*)$", cleaned, flags=re.IGNORECASE)
            if match:
                capture = True
                inline = clean_text(match.group(1))
                if inline:
                    captured.append(inline)
            continue
        if re.match(r"^(abstract|article\s+info|introduction|1\.?\s+introduction)\b", lower):
            break
        if re.match(r"^(corresponding author|received|accepted|available online)\b", lower):
            break
        captured.append(cleaned)
    return "\n".join(captured)


def _keyword_items_from_block(block: str) -> list[str]:
    normalized_block = block.replace("\u2022", "\n").replace("\u00b7", "\n")
    raw_parts: list[str] = []
    if "\n" in normalized_block:
        for line in normalized_block.splitlines():
            raw_parts.extend(re.split(r"[,;|]", line))
    else:
        raw_parts.extend(re.split(r"[,;|]", normalized_block))

    items: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        item = clean_text(re.sub(r"^[-*\d.)\s]+", "", part)).lower()
        if not item or item in {"keywords", "keyword", "index terms", "index term"}:
            continue
        if not (3 <= len(item) <= 80):
            continue
        if item in seen:
            continue
        seen.add(item)
        items.append(item)
    return items


def split_sentences(text: str, limit: int | None = None) -> list[str]:
    raw = re.split(r"(?<=[.!?])\s+", clean_text(text))
    sentences = [s.strip() for s in raw if len(s.strip()) >= 30]
    return sentences[:limit] if limit else sentences


def overlap_score(left: str, right: str) -> tuple[float, list[str]]:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0, []
    shared = sorted(left_tokens & right_tokens)
    denom = max(1, min(len(left_tokens), len(right_tokens)))
    return len(shared) / denom, shared


def author_last_names(authors: Iterable[str] | None) -> set[str]:
    names: set[str] = set()
    for author in authors or []:
        parts = re.findall(r"[A-Za-z]+", clean_text(author).lower())
        if parts:
            names.add(parts[-1])
    return names


def author_match_score(left: Iterable[str] | None, right: Iterable[str] | None) -> float:
    left_names = author_last_names(left)
    right_names = author_last_names(right)
    if not left_names or not right_names:
        return 0.0
    return len(left_names & right_names) / max(1, len(left_names | right_names))


def metadata_completeness(row: dict[str, Any]) -> float:
    fields = ("title", "authors", "year", "doi", "url", "abstract")
    hits = 0
    for field in fields:
        value = row.get(field)
        if field == "authors":
            hits += 1 if value else 0
        else:
            hits += 1 if clean_text(value) else 0
    return round(hits / len(fields), 3)


def dedupe_key_for_literature(row: dict[str, Any]) -> str:
    doi = clean_text(row.get("doi")).lower()
    if doi:
        return f"doi:{doi}"
    return f"title:{normalize_title(row.get('title', ''))}"


def normalize_authors(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [clean_text(value)]
    authors: list[str] = []
    for item in value:
        if isinstance(item, dict):
            if item.get("name"):
                authors.append(clean_text(item.get("name")))
            else:
                given = clean_text(item.get("given"))
                family = clean_text(item.get("family"))
                full = " ".join(part for part in (given, family) if part)
                if full:
                    authors.append(full)
                elif item.get("display_name"):
                    authors.append(clean_text(item.get("display_name")))
        else:
            authors.append(clean_text(item))
    return [author for author in authors if author]


def first_year_from_crossref(item: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "published", "issued", "created"):
        parts = item.get(key, {}).get("date-parts", [])
        if parts and parts[0] and isinstance(parts[0][0], int):
            return parts[0][0]
    return None


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def safe_filename(text: str, fallback: str = "run") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", clean_text(text)).strip("_")
    return cleaned or fallback
