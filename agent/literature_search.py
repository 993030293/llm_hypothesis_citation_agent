from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Callable

from agent.run_logging import EvidenceStore, ToolCallLogger
from agent.utils import (
    clean_text,
    dedupe_key_for_literature,
    first_year_from_crossref,
    metadata_completeness,
    normalize_authors,
    now_iso,
    overlap_score,
)


JsonRows = list[dict[str, Any]]


class LiteratureSearcher:
    """Self-implemented wrappers over public literature APIs."""

    USER_AGENT = "llm-hypothesis-citation-agent/0.1 (course project; mailto:none)"

    def __init__(self, logger: ToolCallLogger, evidence: EvidenceStore, timeout_seconds: int = 15):
        self.logger = logger
        self.evidence = evidence
        self.timeout_seconds = timeout_seconds

    def search(
        self,
        queries: list[dict[str, Any]],
        providers: list[str],
        max_results_per_query: int = 3,
    ) -> list[dict[str, Any]]:
        provider_map: dict[str, Callable[[str, int], JsonRows]] = {
            "crossref": self._query_crossref,
            "openalex": self._query_openalex,
            "semantic_scholar": self._query_semantic_scholar,
            "arxiv": self._query_arxiv,
        }
        raw_rows: list[dict[str, Any]] = []
        for query in queries:
            for provider in providers:
                provider = provider.strip()
                if not provider:
                    continue
                if provider not in provider_map:
                    call_id = self.logger.next_id()
                    started = time.perf_counter()
                    self.logger.log(
                        tool_call_id=call_id,
                        tool_name=f"literature_search.{provider}",
                        inputs={"query": query.get("query")},
                        status="error",
                        output_summary=f"Unsupported provider: {provider}",
                        started_at=started,
                        error=f"Unsupported provider: {provider}",
                    )
                    continue
                call_id = self.logger.next_id()
                started = time.perf_counter()
                try:
                    rows = provider_map[provider](query["query"], max_results_per_query)
                    for row in rows:
                        row.update(
                            {
                                "query_id": query["query_id"],
                                "query": query["query"],
                                "query_stage": query.get("query_stage", "initial"),
                                "query_type": query.get("query_type", "seed"),
                                "retrieval_source": provider,
                                "retrieved_at": now_iso(),
                                "_tool_call_id": call_id,
                            }
                        )
                        score, shared = overlap_score(query["query"], f"{row.get('title','')} {row.get('abstract','')} {row.get('snippet','')}")
                        row["query_overlap_score"] = round(score, 3)
                        row["query_overlap_terms"] = shared[:12]
                        self._enrich_record(row)
                    raw_rows.extend(rows)
                    self.logger.log(
                        tool_call_id=call_id,
                        tool_name=f"literature_search.{provider}",
                        inputs={"query_id": query["query_id"], "query": query["query"], "max_results": max_results_per_query},
                        status="success",
                        output_summary=f"{provider} returned {len(rows)} normalized results.",
                        started_at=started,
                        outputs={"result_count": len(rows)},
                    )
                except Exception as exc:
                    self.logger.log(
                        tool_call_id=call_id,
                        tool_name=f"literature_search.{provider}",
                        inputs={"query_id": query["query_id"], "query": query["query"], "max_results": max_results_per_query},
                        status="error",
                        output_summary=f"{provider} search failed.",
                        started_at=started,
                        error=str(exc),
                    )

        return self._dedupe_and_record(raw_rows)

    def combine_records(self, record_groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
        """Dedupe already-normalized records from multiple search stages."""
        rows: list[dict[str, Any]] = []
        for group in record_groups:
            rows.extend(group)
        return self._dedupe_rows(rows, record_evidence=False)

    def _dedupe_and_record(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._dedupe_rows(rows, record_evidence=True)

    def _dedupe_rows(self, rows: list[dict[str, Any]], *, record_evidence: bool) -> list[dict[str, Any]]:
        by_key: dict[str, dict[str, Any]] = {}
        for source_row in rows:
            row = dict(source_row)
            self._enrich_record(row)
            key = row.get("dedupe_key") or dedupe_key_for_literature(row)
            if key in {"doi:", "title:"}:
                continue
            existing = by_key.get(key)
            if not existing:
                row["matched_query_ids"] = [row.get("query_id")] if row.get("query_id") else []
                row["matched_query_stages"] = [row.get("query_stage")] if row.get("query_stage") else []
                row["merged_sources"] = [row.get("retrieval_source")]
                by_key[key] = row
                continue
            if row.get("retrieval_source") and row.get("retrieval_source") not in existing.setdefault("merged_sources", []):
                existing["merged_sources"].append(row.get("retrieval_source"))
            if row.get("query_id") and row.get("query_id") not in existing.setdefault("matched_query_ids", []):
                existing["matched_query_ids"].append(row.get("query_id"))
            if row.get("query_stage") and row.get("query_stage") not in existing.setdefault("matched_query_stages", []):
                existing["matched_query_stages"].append(row.get("query_stage"))
            for field in ("abstract", "snippet", "doi", "url", "venue"):
                if not existing.get(field) and row.get(field):
                    existing[field] = row.get(field)
            if not existing.get("authors") and row.get("authors"):
                existing["authors"] = row.get("authors")
            if not existing.get("year") and row.get("year"):
                existing["year"] = row.get("year")
            if row.get("relevance_score", 0) > existing.get("relevance_score", 0):
                existing["relevance_score"] = row.get("relevance_score")
                existing["query_overlap_score"] = row.get("query_overlap_score")
                existing["query_overlap_terms"] = row.get("query_overlap_terms")
                existing["query_id"] = row.get("query_id")
                existing["query"] = row.get("query")
                existing["query_stage"] = row.get("query_stage")
                existing["query_type"] = row.get("query_type")
            self._enrich_record(existing)

        records = sorted(by_key.values(), key=lambda item: item.get("relevance_score", 0), reverse=True)
        for idx, row in enumerate(records, start=1):
            row["literature_id"] = f"L{idx:03d}"
            if record_evidence or not row.get("evidence_id"):
                evidence_id = self.evidence.record(
                    source_type="literature_api",
                    source=row.get("retrieval_source", "unknown"),
                    content_snippet=f"{row.get('title','')} {row.get('abstract') or row.get('snippet','')}",
                    category="retrieved_literature",
                    tool_call_id=row.get("_tool_call_id"),
                    locator=row.get("doi") or row.get("url") or row.get("title"),
                    url=row.get("url"),
                    metadata={
                        "literature_id": row["literature_id"],
                        "doi": row.get("doi"),
                        "authors": row.get("authors", []),
                        "year": row.get("year"),
                        "query_id": row.get("query_id"),
                        "query_stage": row.get("query_stage"),
                        "merged_sources": row.get("merged_sources", []),
                        "relevance_score": row.get("relevance_score"),
                    },
                )
                row["evidence_id"] = evidence_id
            row.pop("_tool_call_id", None)
        return records

    def _enrich_record(self, row: dict[str, Any]) -> None:
        row["dedupe_key"] = row.get("dedupe_key") or dedupe_key_for_literature(row)
        row["metadata_completeness"] = metadata_completeness(row)
        row["abstract_available"] = bool(clean_text(row.get("abstract") or row.get("snippet")))
        overlap = float(row.get("query_overlap_score") or 0.0)
        completeness = float(row.get("metadata_completeness") or 0.0)
        abstract_bonus = 0.12 if row.get("abstract_available") else 0.0
        doi_bonus = 0.08 if clean_text(row.get("doi")) else 0.0
        row["relevance_score"] = round(min(1.0, 0.70 * overlap + 0.20 * completeness + abstract_bonus + doi_bonus), 3)
        row.setdefault("selected_for_hypothesis", False)
        row.setdefault("selection_reason", "")

    def _request_json(self, url: str) -> dict[str, Any]:
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        request = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"})
        with opener.open(request, timeout=self.timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset))

    def _query_crossref(self, query: str, max_results: int) -> JsonRows:
        params = {"query.bibliographic": query, "rows": str(max_results)}
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
        payload = self._request_json(url)
        rows: JsonRows = []
        for item in payload.get("message", {}).get("items", []):
            title = clean_text(item.get("title", [""])[0] if item.get("title") else "")
            if not title:
                continue
            rows.append(
                {
                    "title": title,
                    "authors": normalize_authors(item.get("author")),
                    "year": first_year_from_crossref(item),
                    "doi": clean_text(item.get("DOI")),
                    "venue": clean_text(item.get("container-title", [""])[0] if item.get("container-title") else ""),
                    "url": clean_text(item.get("URL")),
                    "abstract": clean_text(item.get("abstract")),
                    "snippet": clean_text(item.get("subtitle")),
                }
            )
        return rows

    def _query_openalex(self, query: str, max_results: int) -> JsonRows:
        params = {"search": query, "per-page": str(max_results)}
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
        payload = self._request_json(url)
        rows: JsonRows = []
        for item in payload.get("results", []):
            title = clean_text(item.get("title") or item.get("display_name"))
            if not title:
                continue
            doi = clean_text(item.get("doi")).replace("https://doi.org/", "")
            authors = [
                clean_text(authorship.get("author", {}).get("display_name"))
                for authorship in item.get("authorships", [])
            ]
            rows.append(
                {
                    "title": title,
                    "authors": [author for author in authors if author],
                    "year": item.get("publication_year"),
                    "doi": doi,
                    "venue": clean_text((item.get("primary_location") or {}).get("source", {}).get("display_name")),
                    "url": clean_text((item.get("primary_location") or {}).get("landing_page_url") or item.get("id")),
                    "abstract": self._openalex_abstract(item.get("abstract_inverted_index")),
                    "snippet": clean_text(item.get("type")),
                }
            )
        return rows

    def _query_semantic_scholar(self, query: str, max_results: int) -> JsonRows:
        params = {
            "query": query,
            "limit": str(max_results),
            "fields": "title,authors,year,venue,url,abstract,externalIds",
        }
        url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params)
        payload = self._request_json(url)
        rows: JsonRows = []
        for item in payload.get("data", []):
            title = clean_text(item.get("title"))
            if not title:
                continue
            rows.append(
                {
                    "title": title,
                    "authors": normalize_authors(item.get("authors")),
                    "year": item.get("year"),
                    "doi": clean_text((item.get("externalIds") or {}).get("DOI")),
                    "venue": clean_text(item.get("venue")),
                    "url": clean_text(item.get("url")),
                    "abstract": clean_text(item.get("abstract")),
                    "snippet": "",
                }
            )
        return rows

    def _query_arxiv(self, query: str, max_results: int) -> JsonRows:
        params = {"search_query": "all:" + query, "start": "0", "max_results": str(max_results)}
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            xml_text = response.read().decode("utf-8")
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        rows: JsonRows = []
        for entry in root.findall("atom:entry", ns):
            published = clean_text(entry.findtext("atom:published", default="", namespaces=ns))
            authors = [
                clean_text(author.findtext("atom:name", default="", namespaces=ns))
                for author in entry.findall("atom:author", ns)
            ]
            rows.append(
                {
                    "title": clean_text(entry.findtext("atom:title", default="", namespaces=ns)),
                    "authors": [author for author in authors if author],
                    "year": int(published[:4]) if published[:4].isdigit() else None,
                    "doi": "",
                    "venue": "arXiv",
                    "url": clean_text(entry.findtext("atom:id", default="", namespaces=ns)),
                    "abstract": clean_text(entry.findtext("atom:summary", default="", namespaces=ns)),
                    "snippet": "",
                }
            )
        return [row for row in rows if row.get("title")]

    def _openalex_abstract(self, inverted: dict[str, list[int]] | None) -> str:
        if not inverted:
            return ""
        positioned: list[tuple[int, str]] = []
        for word, positions in inverted.items():
            for pos in positions:
                positioned.append((pos, word))
        return clean_text(" ".join(word for _pos, word in sorted(positioned)))
