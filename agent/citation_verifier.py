from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from agent.run_logging import EvidenceStore, ToolCallLogger
from agent.utils import (
    author_last_names,
    author_match_score,
    clean_text,
    first_year_from_crossref,
    normalize_authors,
    overlap_score,
    similarity,
    split_sentences,
    write_jsonl,
)
from agent.verifier_params import load_verifier_params


class CitationVerifier:
    """Verify citation existence, metadata match, and claim support.

    The final Green/Yellow/Red label is produced by deterministic rules over
    public metadata and textual evidence. LLM output is only an optional
    explanation layer and never upgrades a label.
    """

    USER_AGENT = "llm-hypothesis-citation-agent/0.1 (course project; mailto:none)"

    def __init__(
        self,
        logger: ToolCallLogger,
        evidence: EvidenceStore,
        timeout_seconds: int = 15,
        *,
        fulltext_evidence: list[dict[str, Any]] | None = None,
        run_dir: Path | str | None = None,
        providers: list[str] | None = None,
        verifier_params: dict[str, Any] | None = None,
        verifier_params_path: Path | str | None = None,
    ):
        self.logger = logger
        self.evidence = evidence
        self.timeout_seconds = timeout_seconds
        self.fulltext_evidence = fulltext_evidence or []
        self.run_dir = Path(run_dir) if run_dir else None
        self.providers = providers or ["crossref", "openalex", "semantic_scholar", "arxiv"]
        self.params = load_verifier_params(
            verifier_params_path or os.environ.get("CITATION_VERIFIER_PARAMS"),
            verifier_params,
        )
        self.provider_rows: list[dict[str, Any]] = []
        self.version_rows: list[dict[str, Any]] = []
        self.paragraph_support_matches: list[dict[str, Any]] = []

    def verify(self, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.provider_rows = []
        self.version_rows = []
        self.paragraph_support_matches = []
        rows = [self.verify_one(claim) for claim in claims]
        self._write_audit_artifacts()
        return rows

    def verify_one(self, claim: dict[str, Any]) -> dict[str, Any]:
        cited = claim.get("cited_work", {})
        call_id = self.logger.next_id()
        started = time.perf_counter()
        try:
            candidate, lookup_source, lookup_error = self._lookup_citation(
                cited,
                claim_id=claim.get("claim_id", ""),
            )
            row = self._classify_claim_support(claim, cited, candidate, lookup_source, lookup_error)
            evidence_id = self.evidence.record(
                source_type="citation_verification",
                source=lookup_source or "no_match",
                content_snippet=self._candidate_snippet(candidate) if candidate else row["reason"],
                category="citation_verification",
                tool_call_id=call_id,
                locator=cited.get("doi") or cited.get("title"),
                url=(candidate or {}).get("url"),
                metadata={
                    "claim_id": claim.get("claim_id"),
                    "color_label": row["color_label"],
                    "metadata_match_status": row["metadata_match_status"],
                    "support_status": row["support_status"],
                    "error_type": row.get("error_type"),
                },
            )
            row["evidence_id"] = evidence_id
            self.logger.log(
                tool_call_id=call_id,
                tool_name="citation_verifier.verify_citation",
                inputs={"claim_id": claim.get("claim_id"), "cited_title": cited.get("title"), "doi": cited.get("doi")},
                status="success",
                output_summary=f"{claim.get('claim_id')} labeled {row['color_label']}: {row['reason']}",
                started_at=started,
                outputs={
                    "evidence_id": evidence_id,
                    "lookup_source": lookup_source,
                    "version_group_id": row.get("version_group_id"),
                    "error_type": row.get("error_type"),
                    "green_gate_passed": row.get("green_gate_passed"),
                },
            )
            return row
        except Exception as exc:
            row = self._unexpected_error_row(claim, cited, exc)
            evidence_id = self.evidence.record(
                source_type="citation_verification_error",
                source="verification_error",
                content_snippet=row["reason"],
                category="citation_verification",
                tool_call_id=call_id,
                locator=cited.get("doi") or cited.get("title"),
                url=cited.get("url"),
                metadata={
                    "claim_id": claim.get("claim_id"),
                    "color_label": row["color_label"],
                    "metadata_match_status": row["metadata_match_status"],
                    "support_status": row["support_status"],
                    "error_type": row.get("error_type"),
                },
            )
            row["evidence_id"] = evidence_id
            self.logger.log(
                tool_call_id=call_id,
                tool_name="citation_verifier.verify_citation",
                inputs={"claim_id": claim.get("claim_id"), "cited_title": cited.get("title"), "doi": cited.get("doi")},
                status="error",
                output_summary=f"{claim.get('claim_id')} labeled Yellow after verifier error: {exc}",
                started_at=started,
                error=str(exc),
                outputs={"evidence_id": evidence_id},
            )
            return row

    def _lookup_citation(
        self,
        cited: dict[str, Any],
        *,
        claim_id: str = "",
    ) -> tuple[dict[str, Any] | None, str, str]:
        doi = clean_text(cited.get("doi"))
        title = clean_text(cited.get("title"))
        if doi and not re.match(r"^10\.\d{4,9}/\S+$", doi, flags=re.IGNORECASE):
            self.provider_rows.append(
                self._provider_row(
                    claim_id=claim_id,
                    provider="doi_format_check",
                    query_type="doi",
                    query=doi,
                    status="error",
                    error=f"Invalid DOI format: {doi}",
                    candidate=None,
                )
            )
            return None, "doi_format_check", f"Invalid DOI format: {doi}"

        provider_errors: list[str] = []
        candidates: list[dict[str, Any]] = []
        for provider in self.providers:
            provider = provider.strip()
            if not provider:
                continue
            query_type = "doi" if doi and provider != "arxiv" else "title"
            query = doi if query_type == "doi" else title
            if not query:
                continue
            row = self._lookup_provider(provider, query_type, query, claim_id)
            self.provider_rows.append(row)
            candidate = row.get("candidate")
            if row.get("status") == "success" and isinstance(candidate, dict):
                candidates.append(candidate)
            elif row.get("status") == "error":
                provider_errors.append(f"{provider}: {row.get('error')}")

        if not candidates:
            if provider_errors:
                return None, "lookup_error", " ".join(provider_errors)
            return None, "not_found", "No matching citation found through DOI/title lookup."

        resolution = self._resolve_versions(cited, candidates, claim_id)
        self.version_rows.append(resolution)
        best = dict(resolution.get("best_candidate") or candidates[0])
        best["source_agreement_count"] = resolution.get("source_agreement_count", 1)
        best["source_agreement_summary"] = resolution.get("source_agreement_summary", "")
        best["version_group_id"] = resolution.get("version_group_id", "")
        best["version_match_status"] = resolution.get("version_match_status", "")
        best["provider_records"] = [
            {
                "provider": row.get("provider"),
                "status": row.get("status"),
                "lookup_source": row.get("lookup_source"),
                "title": (row.get("candidate") or {}).get("title") if isinstance(row.get("candidate"), dict) else "",
                "doi": (row.get("candidate") or {}).get("doi") if isinstance(row.get("candidate"), dict) else "",
                "year": (row.get("candidate") or {}).get("year") if isinstance(row.get("candidate"), dict) else "",
                "error": row.get("error"),
            }
            for row in self.provider_rows
            if row.get("claim_id") == claim_id
        ]
        return best, clean_text(resolution.get("lookup_source")) or "multi_source", ""

    def _classify_claim_support(
        self,
        claim: dict[str, Any],
        cited: dict[str, Any],
        candidate: dict[str, Any] | None,
        lookup_source: str,
        lookup_error: str,
    ) -> dict[str, Any]:
        base = {
            "claim_id": claim.get("claim_id", ""),
            "claim_text": clean_text(claim.get("claim_text")),
            "cited_title": clean_text(cited.get("title")),
            "cited_authors": "; ".join(cited.get("authors") or []),
            "cited_year": cited.get("year") or "",
            "doi": clean_text(cited.get("doi") or (candidate or {}).get("doi")),
            "retrieval_source": clean_text(cited.get("retrieval_source") or lookup_source),
            "url": clean_text(cited.get("url") or (candidate or {}).get("url")),
        }
        if not candidate and lookup_source == "lookup_error":
            return self._base_row(
                base,
                exists_status="unknown",
                metadata_match_status="unknown",
                support_status="partial_or_uncertain",
                color_label="Yellow",
                reason=lookup_error or "Public API lookup failed, so citation support is inconclusive.",
                verification_method=lookup_source,
                error_type="api_inconclusive",
                manual_review_action="Retry provider lookup or inspect the citation manually.",
            )

        if not candidate:
            error_type = "invalid_doi" if lookup_source == "doi_format_check" else "not_found"
            return self._base_row(
                base,
                exists_status="not_found",
                metadata_match_status="unknown",
                support_status="not_supported",
                color_label="Red",
                reason=lookup_error or "No DOI/title match was found in public APIs.",
                verification_method=lookup_source,
                error_type=error_type,
                manual_review_action="Check whether the citation title/DOI was fabricated or mistyped.",
            )

        if not candidate.get("abstract") and cited.get("abstract"):
            candidate["abstract"] = cited.get("abstract")
        if not candidate.get("snippet") and cited.get("snippet"):
            candidate["snippet"] = cited.get("snippet")

        metadata = self._metadata_assessment(cited, candidate)
        support = self._support_assessment(
            claim.get("claim_text", ""),
            candidate,
            claim_id=claim.get("claim_id", ""),
        )
        metadata_status = metadata["metadata_match_status"]
        support_status = support["support_status"]
        source_agreement_count = int(candidate.get("source_agreement_count") or 1)
        version_match_status = clean_text(candidate.get("version_match_status")) or "single_record"
        authoritative_doi_lookup = lookup_source.endswith("_doi") and bool(clean_text(candidate.get("doi")))
        green_gate_passed = (
            metadata_status == "match"
            and support_status == "supports"
            and float(support.get("support_score") or 0.0) >= float(self.params["support_score_green_min"])
            and bool(clean_text(support.get("supporting_sentence")))
            and (
                bool(self.params["allow_input_pdf_fulltext_green"])
                or support.get("support_source_type") != "input_pdf_fulltext"
            )
            and (source_agreement_count >= int(self.params["green_min_source_agreement"]) or authoritative_doi_lookup)
            and version_match_status != "version_year_mismatch"
        )

        if metadata_status == "mismatch" or support_status == "not_supported":
            color = "Red"
        elif green_gate_passed:
            color = "Green"
        else:
            color = "Yellow"
        error_type = self._final_error_type(metadata, support, color, version_match_status, green_gate_passed)

        return {
            **base,
            "exists_status": "exists",
            "metadata_match_status": metadata_status,
            "support_status": support_status,
            "color_label": color,
            "reason": f"{metadata['metadata_reason']} {support['support_reason']}".strip(),
            "evidence_id": "",
            "url": clean_text(candidate.get("url") or base["url"]),
            "doi": clean_text(candidate.get("doi") or base["doi"]),
            "title_similarity": metadata["title_similarity"],
            "author_match_score": metadata["author_match_score"],
            "year_match": metadata["year_match"],
            "support_score": support["support_score"],
            "matched_evidence_text": support["matched_evidence_text"],
            "verification_method": lookup_source,
            "error_type": error_type,
            "source_agreement_count": source_agreement_count,
            "source_agreement_summary": clean_text(candidate.get("source_agreement_summary")),
            "version_group_id": clean_text(candidate.get("version_group_id")),
            "version_match_status": version_match_status,
            "supporting_sentence": clean_text(support.get("supporting_sentence")),
            "supporting_location": clean_text(support.get("supporting_location")),
            "support_source_type": clean_text(support.get("support_source_type")),
            "manual_review_action": self._manual_review_action(color, error_type, support.get("supporting_location")),
            "green_gate_passed": bool(green_gate_passed),
            "llm_explanation": clean_text(support.get("llm_explanation")),
        }

    def _metadata_assessment(self, cited: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        title_score = similarity(cited.get("title", ""), candidate.get("title", ""))
        cited_year = cited.get("year")
        candidate_year = candidate.get("year")
        year_match = not cited_year or not candidate_year or str(cited_year) == str(candidate_year)
        cited_authors = author_last_names(cited.get("authors"))
        candidate_authors = author_last_names(candidate.get("authors"))
        author_score = author_match_score(cited.get("authors"), candidate.get("authors"))
        author_match = (
            not cited_authors
            or not candidate_authors
            or author_score > float(self.params["author_min_match_score"])
        )
        cited_doi = clean_text(cited.get("doi")).lower()
        candidate_doi = clean_text(candidate.get("doi")).lower()
        doi_match = not cited_doi or not candidate_doi or cited_doi == candidate_doi

        status = "mismatch"
        error_type = ""
        if cited_doi and candidate_doi and cited_doi != candidate_doi:
            reason = "DOI resolves to a different record."
            error_type = "doi_metadata_mismatch"
        elif title_score < float(self.params["title_mismatch_threshold"]):
            reason = f"Title does not match public record (title similarity {title_score:.2f})."
            error_type = "title_mismatch"
        elif not author_match:
            reason = "Author metadata does not overlap with the public record."
            error_type = "author_mismatch"
        elif title_score >= float(self.params["title_match_threshold"]) and author_match and doi_match and not year_match:
            status = "partial_match"
            reason = (
                f"Year mismatch: cited {cited_year}, public record {candidate_year}. "
                "The title/authors/DOI point to the same public record, so this requires manual metadata review."
            )
            error_type = "year_mismatch_requires_review"
        elif title_score >= float(self.params["title_match_threshold"]) and year_match and author_match and doi_match:
            status = "match"
            reason = f"Metadata matches public record (title similarity {title_score:.2f})."
        elif title_score >= float(self.params["title_partial_threshold"]) and doi_match:
            status = "partial_match"
            reason = f"Metadata partially matches; title similarity {title_score:.2f}."
            error_type = "provider_disagreement"
        else:
            reason = f"Metadata mismatch; title similarity {title_score:.2f}."
            error_type = "title_mismatch"
        return {
            "metadata_match_status": status,
            "metadata_reason": reason,
            "title_similarity": round(title_score, 3),
            "author_match_score": round(author_score, 3),
            "year_match": bool(year_match),
            "error_type": error_type,
        }

    def _support_assessment(self, claim_text: str, candidate: dict[str, Any], *, claim_id: str = "") -> dict[str, Any]:
        result = self._deterministic_support_assessment(claim_text, candidate, claim_id=claim_id)
        result["llm_explanation"] = self._llm_explanation(claim_text, result) if self._llm_enabled() else ""
        return result

    def _deterministic_support_assessment(
        self,
        claim_text: str,
        candidate: dict[str, Any],
        *,
        claim_id: str = "",
    ) -> dict[str, Any]:
        sources = self._support_sources(candidate)
        matched_text = ""
        if not sources:
            return {
                "support_status": "partial_or_uncertain",
                "support_reason": "No abstract/snippet/fulltext sentence is available for concrete support.",
                "support_score": 0.0,
                "matched_evidence_text": "",
                "supporting_sentence": "",
                "supporting_location": "",
                "support_source_type": "",
                "error_type": "supporting_sentence_missing",
            }

        scored = []
        for source in sources:
            score, shared = overlap_score(claim_text, source["text"])
            text_similarity = similarity(claim_text, source["text"])
            combined = max(score, text_similarity)
            scored.append((combined, score, text_similarity, shared, source))
        scored.sort(key=lambda item: item[0], reverse=True)
        self._record_paragraph_matches(claim_id, scored[:5])
        combined, score, text_similarity, shared, best = scored[0]
        matched_text = clean_text(best["text"])
        unsupported_terms = self._unsupported_strong_claim_terms(claim_text, matched_text)

        if unsupported_terms:
            return {
                "support_status": "partial_or_uncertain",
                "support_reason": (
                    "The evidence is related, but it does not back the strong claim term(s): "
                    f"{', '.join(unsupported_terms)}. overlap={score:.2f}; shared={', '.join(shared[:8]) or 'none'}."
                ),
                "support_score": round(min(combined, 0.5), 3),
                "matched_evidence_text": matched_text[:500],
                "supporting_sentence": matched_text[:500],
                "supporting_location": best["location"],
                "support_source_type": best["source_type"],
                "error_type": "claim_too_strong",
            }
        if (
            score >= float(self.params["support_green_overlap_threshold"])
            or text_similarity >= float(self.params["support_green_similarity_threshold"])
        ):
            return {
                "support_status": "supports",
                "support_reason": (
                    "A concrete supporting sentence was found "
                    f"(overlap={score:.2f}, similarity={text_similarity:.2f}; "
                    f"shared={', '.join(shared[:8]) or 'none'})."
                ),
                "support_score": round(combined, 3),
                "matched_evidence_text": matched_text[:500],
                "supporting_sentence": matched_text[:500],
                "supporting_location": best["location"],
                "support_source_type": best["source_type"],
                "error_type": "",
            }
        if (
            score >= float(self.params["support_partial_overlap_threshold"])
            or text_similarity >= float(self.params["support_partial_similarity_threshold"])
        ):
            return {
                "support_status": "partial_or_uncertain",
                "support_reason": (
                    "The best evidence sentence is related, but it only partially supports the claim "
                    f"(overlap={score:.2f}, similarity={text_similarity:.2f})."
                ),
                "support_score": round(combined, 3),
                "matched_evidence_text": matched_text[:500],
                "supporting_sentence": matched_text[:500],
                "supporting_location": best["location"],
                "support_source_type": best["source_type"],
                "error_type": "supporting_sentence_missing",
            }
        return {
            "support_status": "not_supported",
            "support_reason": (
                "Available abstract/snippet/fulltext sentences do not support the claim "
                f"(overlap={score:.2f}, similarity={text_similarity:.2f})."
            ),
            "support_score": round(combined, 3),
            "matched_evidence_text": matched_text[:500],
            "supporting_sentence": matched_text[:500],
            "supporting_location": best["location"],
            "support_source_type": best["source_type"],
            "error_type": "supporting_sentence_missing",
        }

    def _lookup_provider(self, provider: str, query_type: str, query: str, claim_id: str) -> dict[str, Any]:
        call_id = self.logger.next_id()
        started = time.perf_counter()
        lookup_source = f"{provider}_{query_type}"
        try:
            if provider == "crossref":
                candidate = self._lookup_crossref_doi(query) if query_type == "doi" else self._lookup_crossref_title(query)
            elif provider == "openalex":
                candidate = self._lookup_openalex_doi(query) if query_type == "doi" else self._lookup_openalex_title(query)
            elif provider == "semantic_scholar":
                candidate = self._lookup_semantic_scholar_doi(query) if query_type == "doi" else self._lookup_semantic_scholar_title(query)
            elif provider == "arxiv":
                candidate = self._lookup_arxiv_title(query)
            else:
                raise ValueError(f"Unsupported provider: {provider}")
            status = "success" if candidate else "not_found"
            self.logger.log(
                tool_call_id=call_id,
                tool_name=f"citation_verifier.lookup_{provider}",
                inputs={"claim_id": claim_id, "query_type": query_type, "query": query},
                status=status,
                output_summary=f"{provider} matched {(candidate or {}).get('title')}" if candidate else f"{provider} returned no match.",
                started_at=started,
                outputs={
                    "lookup_source": lookup_source,
                    "title": (candidate or {}).get("title"),
                    "doi": (candidate or {}).get("doi"),
                    "year": (candidate or {}).get("year"),
                },
            )
            return self._provider_row(
                claim_id=claim_id,
                provider=provider,
                query_type=query_type,
                query=query,
                status=status,
                error="",
                candidate=candidate,
                lookup_source=lookup_source,
                tool_call_id=call_id,
            )
        except Exception as exc:
            self.logger.log(
                tool_call_id=call_id,
                tool_name=f"citation_verifier.lookup_{provider}",
                inputs={"claim_id": claim_id, "query_type": query_type, "query": query},
                status="error",
                output_summary=f"{provider} lookup failed.",
                started_at=started,
                error=str(exc),
                outputs={"lookup_source": lookup_source},
            )
            return self._provider_row(
                claim_id=claim_id,
                provider=provider,
                query_type=query_type,
                query=query,
                status="error",
                error=str(exc),
                candidate=None,
                lookup_source=lookup_source,
                tool_call_id=call_id,
            )

    def _provider_row(
        self,
        *,
        claim_id: str,
        provider: str,
        query_type: str,
        query: str,
        status: str,
        error: str,
        candidate: dict[str, Any] | None,
        lookup_source: str | None = None,
        tool_call_id: str | None = None,
    ) -> dict[str, Any]:
        return {
            "claim_id": claim_id,
            "provider": provider,
            "query_type": query_type,
            "query": query,
            "status": status,
            "lookup_source": lookup_source or f"{provider}_{query_type}",
            "tool_call_id": tool_call_id or "",
            "error": clean_text(error),
            "matched_title": clean_text((candidate or {}).get("title")),
            "matched_authors": "; ".join((candidate or {}).get("authors") or []),
            "matched_year": (candidate or {}).get("year") or "",
            "matched_doi": clean_text((candidate or {}).get("doi")),
            "matched_url": clean_text((candidate or {}).get("url")),
            "abstract_available": bool(clean_text((candidate or {}).get("abstract") or (candidate or {}).get("snippet"))),
            "candidate": candidate,
        }

    def _resolve_versions(self, cited: dict[str, Any], candidates: list[dict[str, Any]], claim_id: str) -> dict[str, Any]:
        cited_title = clean_text(cited.get("title"))
        cited_doi = clean_text(cited.get("doi")).lower()
        cited_year = cited.get("year")
        scored: list[tuple[float, dict[str, Any], str]] = []
        for candidate in candidates:
            title_score = similarity(cited_title, candidate.get("title", ""))
            author_score = author_match_score(cited.get("authors"), candidate.get("authors"))
            doi = clean_text(candidate.get("doi")).lower()
            year_delta = self._year_delta(cited_year, candidate.get("year"))
            rule = "title_similarity"
            score = title_score + min(author_score, 0.3)
            if cited_doi and doi and cited_doi == doi:
                rule = "doi_exact"
                score = 2.0
            elif self._arxiv_id(cited.get("url") or cited.get("doi")) and self._arxiv_id(cited.get("url") or cited.get("doi")) == self._arxiv_id(candidate.get("url") or candidate.get("doi")):
                rule = "arxiv_id_exact"
                score = 1.8
            elif title_score >= float(self.params["version_title_author_threshold"]) and author_score > 0:
                rule = "title_author_high_similarity"
                score = 1.5 + author_score
            elif (
                title_score >= float(self.params["version_preprint_title_threshold"])
                and year_delta is not None
                and year_delta <= int(self.params["version_year_delta_max"])
                and self._looks_like_preprint(candidate)
            ):
                rule = "preprint_journal_version_similarity"
                score = 1.2
            scored.append((score, candidate, rule))

        scored.sort(key=lambda item: item[0], reverse=True)
        best = scored[0][1]
        best_rule = scored[0][2]
        matching_candidates = [
            candidate
            for score, candidate, rule in scored
            if score >= 1.2 or rule in {"doi_exact", "arxiv_id_exact", "title_author_high_similarity"}
        ]
        source_names = sorted(
            {
                clean_text(candidate.get("source_provider"))
                for candidate in matching_candidates
                if candidate.get("source_provider")
            }
        )
        if not source_names:
            source_names = sorted(
                {
                    clean_text(row.get("provider"))
                    for row in self.provider_rows
                    if row.get("claim_id") == claim_id and row.get("status") == "success"
                }
            )
        version_match_status = "same_record"
        if best_rule in {"arxiv_id_exact", "preprint_journal_version_similarity"}:
            version_match_status = "preprint_or_journal_version"
        if self._year_delta(cited_year, best.get("year")) not in (None, 0) and version_match_status != "same_record":
            version_match_status = "version_year_mismatch"
        return {
            "claim_id": claim_id,
            "version_group_id": self._version_group_id(best),
            "version_match_status": version_match_status,
            "match_rule": best_rule,
            "lookup_source": clean_text(best.get("lookup_source")) or "multi_source",
            "source_agreement_count": len(source_names) or 1,
            "source_agreement_summary": ", ".join(source_names),
            "best_candidate": best,
            "candidate_count": len(candidates),
            "matching_candidate_count": len(matching_candidates),
            "candidate_titles": [clean_text(candidate.get("title")) for _score, candidate, _rule in scored[:5]],
        }

    def _support_sources(self, candidate: dict[str, Any]) -> list[dict[str, str]]:
        sources: list[dict[str, str]] = []
        abstract = clean_text(candidate.get("abstract") or candidate.get("snippet"))
        if abstract:
            for idx, sentence in enumerate(split_sentences(abstract) or [abstract], start=1):
                sources.append(
                    {
                        "text": clean_text(sentence),
                        "location": f"{candidate.get('source_provider', 'retrieved')} abstract/snippet sentence {idx}",
                        "source_type": "retrieved_abstract",
                    }
                )
        for row in self.fulltext_evidence:
            text = clean_text(row.get("text"))
            if text:
                sources.append(
                    {
                        "text": text,
                        "location": clean_text(row.get("source_location"))
                        or f"input_pdf page {row.get('page_number')}, paragraph {row.get('paragraph_id')}",
                        "source_type": "input_pdf_fulltext",
                    }
                )
        return sources

    def _record_paragraph_matches(self, claim_id: str, scored: list[tuple[float, float, float, list[str], dict[str, str]]]) -> None:
        for rank, (combined, score, text_similarity, shared, source) in enumerate(scored, start=1):
            self.paragraph_support_matches.append(
                {
                    "claim_id": claim_id,
                    "rank": rank,
                    "support_score": round(combined, 3),
                    "overlap_score": round(score, 3),
                    "text_similarity": round(text_similarity, 3),
                    "shared_terms": shared[:12],
                    "supporting_sentence": clean_text(source.get("text"))[:500],
                    "supporting_location": clean_text(source.get("location")),
                    "support_source_type": clean_text(source.get("source_type")),
                }
            )

    def _base_row(
        self,
        base: dict[str, Any],
        *,
        exists_status: str,
        metadata_match_status: str,
        support_status: str,
        color_label: str,
        reason: str,
        verification_method: str,
        error_type: str,
        manual_review_action: str,
    ) -> dict[str, Any]:
        return {
            **base,
            "exists_status": exists_status,
            "metadata_match_status": metadata_match_status,
            "support_status": support_status,
            "color_label": color_label,
            "reason": reason,
            "evidence_id": "",
            "title_similarity": 0.0,
            "author_match_score": 0.0,
            "year_match": False,
            "support_score": 0.0,
            "matched_evidence_text": "",
            "verification_method": verification_method,
            "error_type": error_type,
            "source_agreement_count": 0,
            "source_agreement_summary": "",
            "version_group_id": "",
            "version_match_status": "unknown",
            "supporting_sentence": "",
            "supporting_location": "",
            "manual_review_action": manual_review_action,
            "green_gate_passed": False,
            "llm_explanation": "",
        }

    def _final_error_type(
        self,
        metadata: dict[str, Any],
        support: dict[str, Any],
        color: str,
        version_match_status: str,
        green_gate_passed: bool,
    ) -> str:
        if color == "Green":
            return ""
        if version_match_status == "version_year_mismatch":
            return "version_year_mismatch"
        if support.get("support_status") == "supports" and support.get("support_source_type") == "input_pdf_fulltext":
            return "supporting_sentence_missing"
        if metadata.get("error_type"):
            return metadata["error_type"]
        if support.get("error_type"):
            return support["error_type"]
        if not green_gate_passed:
            return "provider_disagreement"
        return ""

    def _manual_review_action(self, color: str, error_type: str, supporting_location: Any) -> str:
        if color == "Green":
            return "No manual review required for the demo label; supporting sentence is recorded."
        if error_type in {"year_mismatch_requires_review", "version_year_mismatch"}:
            return "Check whether the citation refers to a preprint, online-first record, or journal version."
        if error_type in {"supporting_sentence_missing", "abstract_missing", "claim_too_strong"}:
            location = clean_text(supporting_location)
            return f"Inspect full text near {location}." if location else "Inspect the cited paper full text for a direct supporting sentence."
        if error_type == "api_inconclusive":
            return "Retry Crossref/OpenAlex/Semantic Scholar/arXiv lookup and inspect provider status."
        if color == "Red":
            return "Manually check whether the citation is fabricated, mistyped, or points to a different work."
        return "Manual review recommended before treating this citation as supported."

    def _llm_enabled(self) -> bool:
        return bool(os.environ.get("DEEPSEEK_API_KEY"))

    def _llm_explanation(self, claim_text: str, support: dict[str, Any]) -> str:
        try:
            from agent.llm_client import call_llm

            prompt = (
                "Explain the deterministic citation-support result in one concise Chinese sentence. "
                "Do not output or change any color label.\n\n"
                f"Claim: {claim_text}\n"
                f"Supporting sentence: {support.get('supporting_sentence')}\n"
                f"Rule reason: {support.get('support_reason')}\n"
            )
            response = call_llm([{"role": "user", "content": prompt}], temperature=0.0)
            return clean_text(response.get("content"))[:500]
        except Exception:
            return ""

    def _unsupported_strong_claim_terms(self, claim_text: str, evidence_text: str) -> list[str]:
        claim_lower = clean_text(claim_text).lower()
        evidence_lower = clean_text(evidence_text).lower()
        strong_terms = [
            "fully solves",
            "solves",
            "eliminates",
            "guarantees",
            "proves",
            "always",
            "never",
            "complete solution",
            "完全解决",
            "彻底解决",
            "保证",
        ]
        return [term for term in strong_terms if term in claim_lower and term not in evidence_lower]

    def _lookup_crossref_doi(self, doi: str) -> dict[str, Any] | None:
        encoded = urllib.parse.quote(doi, safe="")
        try:
            payload = self._request_json(f"https://api.crossref.org/works/{encoded}")
            candidate = self._normalize_crossref_item(payload.get("message", {}))
            candidate["source_provider"] = "crossref"
            candidate["lookup_source"] = "crossref_doi"
            return candidate
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def _lookup_crossref_title(self, title: str) -> dict[str, Any] | None:
        params = {"query.bibliographic": title, "rows": "1"}
        payload = self._request_json("https://api.crossref.org/works?" + urllib.parse.urlencode(params))
        items = payload.get("message", {}).get("items", [])
        if not items:
            return None
        candidate = self._normalize_crossref_item(items[0])
        candidate["source_provider"] = "crossref"
        candidate["lookup_source"] = "crossref_title"
        return candidate if similarity(title, candidate.get("title", "")) >= 0.55 else None

    def _lookup_openalex_doi(self, doi: str) -> dict[str, Any] | None:
        params = {"filter": f"doi:{doi}", "per-page": "1"}
        payload = self._request_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
        items = payload.get("results", [])
        if not items:
            return None
        candidate = self._normalize_openalex_item(items[0])
        candidate["source_provider"] = "openalex"
        candidate["lookup_source"] = "openalex_doi"
        return candidate

    def _lookup_openalex_title(self, title: str) -> dict[str, Any] | None:
        params = {"search": title, "per-page": "1"}
        payload = self._request_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
        items = payload.get("results", [])
        if not items:
            return None
        candidate = self._normalize_openalex_item(items[0] if isinstance(items[0], dict) else {})
        candidate["source_provider"] = "openalex"
        candidate["lookup_source"] = "openalex_title"
        return candidate if similarity(title, candidate.get("title", "")) >= 0.55 else None

    def _lookup_semantic_scholar_doi(self, doi: str) -> dict[str, Any] | None:
        encoded = urllib.parse.quote(doi, safe="")
        payload = self._request_json(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{encoded}?fields=title,authors,year,venue,url,abstract,externalIds"
        )
        if not payload.get("title"):
            return None
        candidate = self._normalize_semantic_scholar_item(payload)
        candidate["source_provider"] = "semantic_scholar"
        candidate["lookup_source"] = "semantic_scholar_doi"
        return candidate

    def _lookup_semantic_scholar_title(self, title: str) -> dict[str, Any] | None:
        params = {
            "query": title,
            "limit": "1",
            "fields": "title,authors,year,venue,url,abstract,externalIds",
        }
        payload = self._request_json(
            "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params)
        )
        items = payload.get("data", [])
        if not items:
            return None
        candidate = self._normalize_semantic_scholar_item(items[0])
        candidate["source_provider"] = "semantic_scholar"
        candidate["lookup_source"] = "semantic_scholar_title"
        return candidate if similarity(title, candidate.get("title", "")) >= 0.55 else None

    def _lookup_arxiv_title(self, title: str) -> dict[str, Any] | None:
        params = {"search_query": "all:" + title, "start": "0", "max_results": "1"}
        request = urllib.request.Request(
            "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params),
            headers={"User-Agent": self.USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            xml_text = response.read().decode("utf-8")
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        if entry is None:
            return None
        published = clean_text(entry.findtext("atom:published", default="", namespaces=ns))
        authors = [
            clean_text(author.findtext("atom:name", default="", namespaces=ns))
            for author in entry.findall("atom:author", ns)
        ]
        candidate = {
            "title": clean_text(entry.findtext("atom:title", default="", namespaces=ns)),
            "authors": [author for author in authors if author],
            "year": int(published[:4]) if published[:4].isdigit() else None,
            "doi": "",
            "venue": "arXiv",
            "url": clean_text(entry.findtext("atom:id", default="", namespaces=ns)),
            "abstract": clean_text(entry.findtext("atom:summary", default="", namespaces=ns)),
            "snippet": "",
            "source_provider": "arxiv",
            "lookup_source": "arxiv_title",
        }
        return candidate if similarity(title, candidate.get("title", "")) >= 0.55 else None

    def _normalize_crossref_item(self, item: dict[str, Any]) -> dict[str, Any]:
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

    def _normalize_openalex_item(self, item: dict[str, Any]) -> dict[str, Any]:
        primary_location = item.get("primary_location") or {}
        if not isinstance(primary_location, dict):
            primary_location = {}
        source = primary_location.get("source") or {}
        if not isinstance(source, dict):
            source = {}
        authors = []
        authorships = item.get("authorships") if isinstance(item.get("authorships"), list) else []
        for authorship in authorships:
            if not isinstance(authorship, dict):
                continue
            author = authorship.get("author") or {}
            if isinstance(author, dict):
                authors.append(clean_text(author.get("display_name")))
        return {
            "title": clean_text(item.get("title") or item.get("display_name")),
            "authors": [author for author in authors if author],
            "year": item.get("publication_year"),
            "doi": clean_text(item.get("doi")).replace("https://doi.org/", ""),
            "venue": clean_text(source.get("display_name")),
            "url": clean_text(primary_location.get("landing_page_url") or item.get("id")),
            "abstract": self._openalex_abstract(item.get("abstract_inverted_index")),
            "snippet": clean_text(item.get("type")),
        }

    def _normalize_semantic_scholar_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": clean_text(item.get("title")),
            "authors": normalize_authors(item.get("authors")),
            "year": item.get("year"),
            "doi": clean_text((item.get("externalIds") or {}).get("DOI")),
            "venue": clean_text(item.get("venue")),
            "url": clean_text(item.get("url")),
            "abstract": clean_text(item.get("abstract")),
            "snippet": "",
        }

    def _fetch_abstract(self, doi: str) -> str | None:
        if not doi:
            return None
        try:
            payload = self._request_json(
                f"https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(doi, safe='')}?fields=title,abstract"
            )
            abstract = payload.get("abstract")
            return clean_text(abstract) if abstract else None
        except Exception:
            return None

    def _request_json(self, url: str) -> dict[str, Any]:
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        request = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"})
        with opener.open(request, timeout=self.timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset))

    def _openalex_abstract(self, inverted: dict[str, list[int]] | None) -> str:
        if not inverted:
            return ""
        positioned: list[tuple[int, str]] = []
        for word, positions in inverted.items():
            for pos in positions:
                positioned.append((pos, word))
        return clean_text(" ".join(word for _pos, word in sorted(positioned)))

    def _candidate_snippet(self, candidate: dict[str, Any] | None) -> str:
        if not candidate:
            return ""
        return clean_text(f"{candidate.get('title','')} {candidate.get('abstract') or candidate.get('snippet','')}")

    def _year_delta(self, left: Any, right: Any) -> int | None:
        try:
            if left in ("", None) or right in ("", None):
                return None
            return abs(int(left) - int(right))
        except (TypeError, ValueError):
            return None

    def _looks_like_preprint(self, candidate: dict[str, Any]) -> bool:
        text = clean_text(f"{candidate.get('venue')} {candidate.get('url')} {candidate.get('source_provider')}").lower()
        return "arxiv" in text or "preprint" in text

    def _arxiv_id(self, value: Any) -> str:
        text = clean_text(value).lower()
        match = re.search(r"arxiv(?:\.org)?/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})(?:v[0-9]+)?", text)
        if match:
            return match.group(1)
        match = re.search(r"\barxiv:([0-9]{4}\.[0-9]{4,5})(?:v[0-9]+)?", text)
        return match.group(1) if match else ""

    def _version_group_id(self, candidate: dict[str, Any]) -> str:
        key = clean_text(candidate.get("doi")).lower() or clean_text(candidate.get("title")).lower()
        return f"VG_{abs(hash(key)) % 1000000:06d}"

    def _write_audit_artifacts(self) -> None:
        if not self.run_dir:
            return
        write_jsonl(self.run_dir / "provider_verification.jsonl", [self._serializable_provider_row(row) for row in self.provider_rows])
        write_jsonl(self.run_dir / "version_resolution.jsonl", [self._serializable_version_row(row) for row in self.version_rows])
        write_jsonl(self.run_dir / "paragraph_support_matches.jsonl", self.paragraph_support_matches)

    def _serializable_provider_row(self, row: dict[str, Any]) -> dict[str, Any]:
        candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
        return {
            **{key: value for key, value in row.items() if key != "candidate"},
            "candidate_title": clean_text(candidate.get("title")),
            "candidate_authors": "; ".join(candidate.get("authors") or []),
            "candidate_year": candidate.get("year") or "",
            "candidate_doi": clean_text(candidate.get("doi")),
            "candidate_url": clean_text(candidate.get("url")),
            "candidate_abstract_preview": clean_text(candidate.get("abstract") or candidate.get("snippet"))[:500],
        }

    def _serializable_version_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if key != "best_candidate"}

    def _unexpected_error_row(self, claim: dict[str, Any], cited: dict[str, Any], exc: Exception) -> dict[str, Any]:
        return self._base_row(
            {
                "claim_id": claim.get("claim_id", ""),
                "claim_text": clean_text(claim.get("claim_text")),
                "cited_title": clean_text(cited.get("title")),
                "cited_authors": "; ".join(cited.get("authors") or []),
                "cited_year": cited.get("year") or "",
                "doi": clean_text(cited.get("doi")),
                "retrieval_source": clean_text(cited.get("retrieval_source") or "verification_error"),
                "url": clean_text(cited.get("url")),
            },
            exists_status="unknown",
            metadata_match_status="unknown",
            support_status="partial_or_uncertain",
            color_label="Yellow",
            reason=f"Citation verification failed unexpectedly and requires manual review: {exc}",
            verification_method="verification_error",
            error_type="api_inconclusive",
            manual_review_action="Inspect tool_calls.jsonl and retry the citation verifier.",
        )
