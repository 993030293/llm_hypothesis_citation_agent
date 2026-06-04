from __future__ import annotations

import re
from typing import Any

from agent.utils import clean_text


def normalize_deepscientist_claims_payload(payload: Any) -> list[dict[str, Any]]:
    """Normalize official DeepScientist claim variants for citation audit.

    The official `idea` skill may write a hypothesis-centric JSON where each
    top-level row has `hypothesis`, `supporting_evidence`, and `citations`
    rather than the local verifier's `claim_text` + `cited_work` schema. This
    function turns both formats into the verifier contract without changing
    Green/Yellow/Red logic.
    """

    if isinstance(payload, dict):
        raw_claims = payload.get("claims", [])
    elif isinstance(payload, list):
        raw_claims = payload
    else:
        raw_claims = []
    if not isinstance(raw_claims, list):
        return []

    normalized: list[dict[str, Any]] = []
    for raw_idx, claim in enumerate(raw_claims, start=1):
        if not isinstance(claim, dict):
            continue
        if _is_local_claim_schema(claim):
            normalized.append(_normalize_local_claim(claim, len(normalized) + 1))
            continue

        citations = claim.get("citations") if isinstance(claim.get("citations"), list) else []
        if not citations:
            continue
        hypothesis_id = clean_text(claim.get("claim_id") or claim.get("hypothesis_id")) or f"H{raw_idx:03d}"
        hypothesis_text = clean_text(claim.get("hypothesis") or claim.get("new_hypothesis") or claim.get("claim_text"))
        support_context = _supporting_evidence_text(claim.get("supporting_evidence"))
        for citation_idx, citation in enumerate(citations, start=1):
            if not isinstance(citation, dict):
                continue
            cited_work = _cited_work_from_deepscientist_citation(citation)
            claim_text = clean_text(
                " ".join(
                    part
                    for part in (
                        hypothesis_text,
                        f"Citation role: {clean_text(citation.get('role'))}." if citation.get("role") else "",
                        support_context,
                    )
                    if part
                )
            )
            normalized.append(
                {
                    "claim_id": f"C{len(normalized) + 1:03d}",
                    "hypothesis_id": hypothesis_id,
                    "claim_text": claim_text or clean_text(claim.get("title")) or f"DeepScientist hypothesis {hypothesis_id}",
                    "claim_role": "deepscientist_hypothesis_citation",
                    "cited_work": cited_work,
                    "source_claim_id": clean_text(claim.get("claim_id")),
                    "source_citation_id": clean_text(citation.get("id")) or f"{hypothesis_id}_{citation_idx}",
                }
            )
    return normalized


def _is_local_claim_schema(claim: dict[str, Any]) -> bool:
    cited = claim.get("cited_work")
    return bool(clean_text(claim.get("claim_text")) and isinstance(cited, dict))


def _normalize_local_claim(claim: dict[str, Any], idx: int) -> dict[str, Any]:
    cited = claim.get("cited_work") or {}
    return {
        "claim_id": clean_text(claim.get("claim_id")) or f"C{idx:03d}",
        "claim_text": clean_text(claim.get("claim_text")),
        "hypothesis_id": clean_text(claim.get("hypothesis_id")) or "H_UNKNOWN",
        "claim_role": clean_text(claim.get("claim_role")) or "deepscientist_generated_claim",
        "cited_work": _normalize_cited_work(cited),
    }


def _normalize_cited_work(cited: dict[str, Any]) -> dict[str, Any]:
    authors = cited.get("authors")
    return {
        "title": clean_text(cited.get("title")),
        "authors": authors if isinstance(authors, list) else [],
        "year": cited.get("year") or "",
        "doi": clean_text(cited.get("doi")),
        "venue": clean_text(cited.get("venue")),
        "url": clean_text(cited.get("url")),
        "retrieval_source": clean_text(cited.get("retrieval_source")) or "deepscientist_output",
        "literature_id": cited.get("literature_id"),
        "evidence_id": cited.get("evidence_id"),
        "abstract": clean_text(cited.get("abstract")),
        "snippet": clean_text(cited.get("snippet")),
        "arxiv_id": clean_text(cited.get("arxiv_id")),
    }


def _cited_work_from_deepscientist_citation(citation: dict[str, Any]) -> dict[str, Any]:
    ref = clean_text(citation.get("ref"))
    arxiv_id = clean_text(citation.get("arxiv_id"))
    title, authors, year = _parse_reference(ref)
    cited = {
        "title": clean_text(citation.get("title")) or title,
        "authors": citation.get("authors") if isinstance(citation.get("authors"), list) else authors,
        "year": citation.get("year") or year,
        "doi": clean_text(citation.get("doi")),
        "venue": clean_text(citation.get("venue")),
        "url": clean_text(citation.get("url")) or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""),
        "retrieval_source": clean_text(citation.get("retrieval_source")) or "official_deepscientist",
        "abstract": clean_text(citation.get("abstract")),
        "snippet": clean_text(citation.get("snippet") or citation.get("detail") or ref),
        "arxiv_id": arxiv_id,
    }
    if not cited["title"] and arxiv_id:
        cited["title"] = f"arXiv:{arxiv_id}"
    return cited


def _parse_reference(ref: str) -> tuple[str, list[str], str]:
    if not ref:
        return "", [], ""
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", ref)
    year = year_match.group(1) if year_match else ""
    authors = []
    title = ref
    if year_match:
        author_text = clean_text(ref[: year_match.start()].strip(" .,(;"))
        if author_text:
            authors = [author_text]
        title = clean_text(ref[year_match.end() :].strip(" .,)"))
    return title, authors, year


def _supporting_evidence_text(value: Any) -> str:
    if not isinstance(value, list):
        return clean_text(value)
    snippets = []
    for item in value[:3]:
        if isinstance(item, dict):
            snippets.append(clean_text(item.get("detail") or item.get("text") or item.get("source")))
        else:
            snippets.append(clean_text(item))
    snippets = [snippet for snippet in snippets if snippet]
    return "Supporting evidence noted by DeepScientist: " + " ".join(snippets) if snippets else ""
