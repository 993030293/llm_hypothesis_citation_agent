from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from agent.utils import (
    author_match_score,
    clean_text,
    first_year_from_crossref,
    normalize_authors,
    overlap_score,
    similarity,
)


AUDIT_FIELDS = [
    "case_id",
    "claim_id",
    "original_color",
    "audited_color",
    "agreement_status",
    "doi_resolves",
    "crossref_match",
    "openalex_match",
    "semantic_scholar_match",
    "arxiv_match",
    "title_similarity",
    "author_match_score",
    "year_match",
    "abstract_available",
    "support_evidence_available",
    "audit_reason",
    "manual_review_required",
]


class OnlineCitationAuditor:
    """Independent online audit for citation verification rows.

    This does not overwrite the original verifier output. It queries public
    services again and emits a second opinion for stress-test reporting.
    """

    USER_AGENT = "llm-hypothesis-citation-agent-stress-audit/0.1 (course project; mailto:none)"

    def __init__(self, timeout_seconds: int = 12):
        self.timeout_seconds = timeout_seconds

    def audit_row(self, row: dict[str, Any], case_id: str = "") -> dict[str, Any]:
        cited_title = clean_text(row.get("cited_title"))
        doi = clean_text(row.get("doi"))
        errors: list[str] = []
        matches = {
            "crossref_match": "false",
            "openalex_match": "false",
            "semantic_scholar_match": "false",
            "arxiv_match": "false",
        }
        doi_resolves = "unknown"
        candidates: list[tuple[str, dict[str, Any]]] = []

        if doi and re.match(r"^10\.\d{4,9}/\S+$", doi, flags=re.IGNORECASE):
            doi_resolves = self._doi_landing_resolves(doi)
            for source_name, lookup in (
                ("crossref_match", self._lookup_crossref_doi),
                ("openalex_match", self._lookup_openalex_doi),
            ):
                try:
                    candidate = lookup(doi)
                    if candidate:
                        matches[source_name] = "true"
                        candidates.append((source_name, candidate))
                except Exception as exc:  # noqa: BLE001 - preserve provider-specific failures.
                    matches[source_name] = "error"
                    errors.append(f"{source_name}: {exc}")
        elif doi:
            doi_resolves = "false"
            errors.append(f"invalid DOI format: {doi}")

        if cited_title:
            for source_name, lookup in (
                ("crossref_match", self._lookup_crossref_title),
                ("openalex_match", self._lookup_openalex_title),
                ("semantic_scholar_match", self._lookup_semantic_scholar_title),
                ("arxiv_match", self._lookup_arxiv_title),
            ):
                if matches[source_name] == "true":
                    continue
                try:
                    candidate = lookup(cited_title)
                    if candidate:
                        matches[source_name] = "true"
                        candidates.append((source_name, candidate))
                except Exception as exc:  # noqa: BLE001
                    if matches[source_name] != "true":
                        matches[source_name] = "error"
                    errors.append(f"{source_name}: {exc}")

        best_source, best_candidate = self._best_candidate(cited_title, candidates)
        audit = self._classify(row, best_source, best_candidate, errors)
        return {
            "case_id": case_id,
            "claim_id": row.get("claim_id", ""),
            "original_color": row.get("color_label", ""),
            **audit,
            "doi_resolves": doi_resolves,
            **matches,
        }

    def _classify(
        self,
        row: dict[str, Any],
        best_source: str,
        candidate: dict[str, Any] | None,
        errors: list[str],
    ) -> dict[str, Any]:
        original_color = row.get("color_label", "")
        if not candidate:
            if errors:
                audited_color = "Red"
                agreement = "network_inconclusive" if any("timed out" in err.lower() for err in errors) else "label_disagreement"
                reason = "No independent public metadata match; errors: " + "; ".join(errors[:3])
            else:
                audited_color = "Red"
                agreement = "agree" if original_color == "Red" else "label_disagreement"
                reason = "No independent public metadata match was found."
            return {
                "audited_color": audited_color,
                "agreement_status": agreement if original_color != audited_color else "agree",
                "title_similarity": 0.0,
                "author_match_score": 0.0,
                "year_match": False,
                "abstract_available": False,
                "support_evidence_available": False,
                "audit_reason": reason,
                "manual_review_required": original_color != audited_color,
            }

        title_score = similarity(row.get("cited_title", ""), candidate.get("title", ""))
        author_score = author_match_score(_split_authors(row.get("cited_authors", "")), candidate.get("authors", []))
        row_year = clean_text(row.get("cited_year"))
        candidate_year = clean_text(candidate.get("year"))
        year_match = not row_year or not candidate_year or row_year == candidate_year
        metadata_match = title_score >= 0.86 and year_match and (author_score > 0 or not row.get("cited_authors"))
        evidence_text = clean_text(f"{candidate.get('title','')}. {candidate.get('abstract') or candidate.get('snippet')}")
        support_score, shared = overlap_score(row.get("claim_text", ""), evidence_text)
        abstract_available = len(clean_text(candidate.get("abstract") or candidate.get("snippet"))) >= 80
        support_available = abstract_available and support_score >= 0.18 and len(shared) >= 4

        if not metadata_match:
            audited_color = "Red"
            reason = (
                f"Independent {best_source} match has weak metadata agreement "
                f"(title={title_score:.2f}, author={author_score:.2f}, year_match={year_match})."
            )
        elif support_available:
            audited_color = "Green"
            reason = (
                f"Independent {best_source} metadata matches and abstract/snippet supports the claim "
                f"(support={support_score:.2f}; shared={', '.join(shared[:8])})."
            )
        else:
            audited_color = "Yellow"
            reason = (
                f"Independent {best_source} metadata exists, but concrete support needs manual review "
                f"(abstract_available={abstract_available}, support={support_score:.2f})."
            )

        agreement = "agree" if audited_color == original_color else "label_disagreement"
        manual_review = audited_color == "Yellow" or agreement != "agree"
        if original_color == "Yellow" and audited_color == "Green":
            agreement = "manual_review_recommended"
            manual_review = True
        return {
            "audited_color": audited_color,
            "agreement_status": agreement,
            "title_similarity": round(title_score, 3),
            "author_match_score": round(author_score, 3),
            "year_match": bool(year_match),
            "abstract_available": bool(abstract_available),
            "support_evidence_available": bool(support_available),
            "audit_reason": reason,
            "manual_review_required": bool(manual_review),
        }

    def _best_candidate(
        self,
        cited_title: str,
        candidates: list[tuple[str, dict[str, Any]]],
    ) -> tuple[str, dict[str, Any] | None]:
        if not candidates:
            return "none", None
        ranked = sorted(
            candidates,
            key=lambda item: (
                similarity(cited_title, item[1].get("title", "")),
                bool(clean_text(item[1].get("abstract") or item[1].get("snippet"))),
            ),
            reverse=True,
        )
        return ranked[0]

    def _request_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset))

    def _doi_landing_resolves(self, doi: str) -> str:
        url = "https://doi.org/" + urllib.parse.quote(doi, safe="/")
        try:
            request = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT}, method="HEAD")
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return "true" if 200 <= response.status < 400 else "false"
        except Exception:
            return "false"

    def _lookup_crossref_doi(self, doi: str) -> dict[str, Any] | None:
        encoded = urllib.parse.quote(doi, safe="")
        try:
            payload = self._request_json(f"https://api.crossref.org/works/{encoded}")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        return _normalize_crossref_item(payload.get("message", {}))

    def _lookup_crossref_title(self, title: str) -> dict[str, Any] | None:
        params = {"query.bibliographic": title, "rows": "1"}
        payload = self._request_json("https://api.crossref.org/works?" + urllib.parse.urlencode(params))
        items = payload.get("message", {}).get("items", [])
        if not items:
            return None
        candidate = _normalize_crossref_item(items[0])
        return candidate if similarity(title, candidate.get("title", "")) >= 0.55 else None

    def _lookup_openalex_doi(self, doi: str) -> dict[str, Any] | None:
        params = {"filter": "doi:" + doi}
        payload = self._request_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
        items = payload.get("results", [])
        return _normalize_openalex_item(items[0]) if items else None

    def _lookup_openalex_title(self, title: str) -> dict[str, Any] | None:
        params = {"search": title, "per-page": "1"}
        payload = self._request_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
        items = payload.get("results", [])
        if not items:
            return None
        candidate = _normalize_openalex_item(items[0])
        return candidate if similarity(title, candidate.get("title", "")) >= 0.55 else None

    def _lookup_semantic_scholar_title(self, title: str) -> dict[str, Any] | None:
        params = {
            "query": title,
            "limit": "1",
            "fields": "title,authors,year,venue,url,abstract,externalIds",
        }
        payload = self._request_json("https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params))
        items = payload.get("data", [])
        if not items:
            return None
        item = items[0]
        candidate = {
            "title": clean_text(item.get("title")),
            "authors": normalize_authors(item.get("authors")),
            "year": item.get("year"),
            "doi": clean_text((item.get("externalIds") or {}).get("DOI")),
            "venue": clean_text(item.get("venue")),
            "url": clean_text(item.get("url")),
            "abstract": clean_text(item.get("abstract")),
            "snippet": "",
        }
        return candidate if similarity(title, candidate.get("title", "")) >= 0.55 else None

    def _lookup_arxiv_title(self, title: str) -> dict[str, Any] | None:
        params = {"search_query": "ti:" + title, "start": "0", "max_results": "1"}
        request = urllib.request.Request(
            "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params),
            headers={"User-Agent": self.USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            root = ET.fromstring(response.read().decode("utf-8"))
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        candidate = {
            "title": clean_text(entry.findtext("atom:title", default="", namespaces=ns)),
            "authors": [
                clean_text(author.findtext("atom:name", default="", namespaces=ns))
                for author in entry.findall("atom:author", ns)
            ],
            "year": _year_from_text(entry.findtext("atom:published", default="", namespaces=ns)),
            "doi": "",
            "venue": "arXiv",
            "url": clean_text(entry.findtext("atom:id", default="", namespaces=ns)),
            "abstract": clean_text(entry.findtext("atom:summary", default="", namespaces=ns)),
            "snippet": "",
        }
        return candidate if similarity(title, candidate.get("title", "")) >= 0.55 else None


def _normalize_crossref_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": clean_text(item.get("title", [""])[0] if item.get("title") else ""),
        "authors": normalize_authors(item.get("author")),
        "year": first_year_from_crossref(item),
        "doi": clean_text(item.get("DOI")),
        "venue": clean_text(item.get("container-title", [""])[0] if item.get("container-title") else ""),
        "url": clean_text(item.get("URL")),
        "abstract": clean_text(item.get("abstract")),
        "snippet": clean_text(item.get("subtitle")),
    }


def _normalize_openalex_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": clean_text(item.get("title") or item.get("display_name")),
        "authors": [
            clean_text(authorship.get("author", {}).get("display_name"))
            for authorship in item.get("authorships", [])
            if clean_text(authorship.get("author", {}).get("display_name"))
        ],
        "year": item.get("publication_year"),
        "doi": clean_text(item.get("doi")).replace("https://doi.org/", ""),
        "venue": clean_text((item.get("primary_location") or {}).get("source", {}).get("display_name")),
        "url": clean_text((item.get("primary_location") or {}).get("landing_page_url") or item.get("id")),
        "abstract": _openalex_abstract(item.get("abstract_inverted_index")),
        "snippet": clean_text(item.get("type")),
    }


def _openalex_abstract(inverted: dict[str, list[int]] | None) -> str:
    if not inverted:
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in inverted.items():
        for pos in positions:
            positioned.append((pos, word))
    return clean_text(" ".join(word for _pos, word in sorted(positioned)))


def _split_authors(value: str) -> list[str]:
    return [clean_text(item) for item in re.split(r";|,", clean_text(value)) if clean_text(item)]


def _year_from_text(text: str) -> int | None:
    match = re.search(r"\b(19|20)\d{2}\b", clean_text(text))
    return int(match.group(0)) if match else None
