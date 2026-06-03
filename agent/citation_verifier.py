from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from agent.run_logging import EvidenceStore, ToolCallLogger
from agent.utils import (
    author_match_score,
    author_last_names,
    clean_text,
    first_year_from_crossref,
    normalize_authors,
    overlap_score,
    similarity,
    split_sentences,
)


class CitationVerifier:
    """Verify citation existence, metadata match, and claim support."""

    USER_AGENT = "llm-hypothesis-citation-agent/0.1 (course project; mailto:none)"

    def __init__(self, logger: ToolCallLogger, evidence: EvidenceStore, timeout_seconds: int = 15):
        self.logger = logger
        self.evidence = evidence
        self.timeout_seconds = timeout_seconds

    def verify(self, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for claim in claims:
            rows.append(self.verify_one(claim))
        return rows

    def verify_one(self, claim: dict[str, Any]) -> dict[str, Any]:
        cited = claim.get("cited_work", {})
        call_id = self.logger.next_id()
        started = time.perf_counter()
        try:
            candidate, lookup_source, lookup_error = self._lookup_citation(cited)
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
                outputs={"evidence_id": evidence_id, "lookup_source": lookup_source},
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

    def _lookup_citation(self, cited: dict[str, Any]) -> tuple[dict[str, Any] | None, str, str]:
        lookup_errors: list[str] = []
        doi = clean_text(cited.get("doi"))
        if doi and re.match(r"^10\.\d{4,9}/\S+$", doi, flags=re.IGNORECASE):
            try:
                candidate = self._lookup_crossref_doi(doi)
                if candidate:
                    return candidate, "crossref_doi", ""
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
                lookup_errors.append(f"Crossref DOI lookup failed for {doi}: {exc}")
        elif doi:
            return None, "doi_format_check", f"Invalid DOI format: {doi}"

        title = clean_text(cited.get("title"))
        if title:
            try:
                candidate = self._lookup_crossref_title(title)
                if candidate:
                    return candidate, "crossref_title", ""
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
                lookup_errors.append(f"Crossref title lookup failed for {title}: {exc}")
            try:
                candidate = self._lookup_openalex_title(title)
                if candidate:
                    return candidate, "openalex_title", ""
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
                lookup_errors.append(f"OpenAlex title lookup failed for {title}: {exc}")
        if lookup_errors:
            return None, "lookup_error", " ".join(lookup_errors)
        return None, "not_found", "No matching citation found through DOI/title lookup."

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
            return {
                **base,
                "exists_status": "unknown",
                "metadata_match_status": "unknown",
                "support_status": "partial_or_uncertain",
                "color_label": "Yellow",
                "reason": lookup_error or "Public API lookup failed, so citation support is inconclusive.",
                "evidence_id": "",
                "title_similarity": 0.0,
                "author_match_score": 0.0,
                "year_match": False,
                "support_score": 0.0,
                "matched_evidence_text": "",
                "verification_method": lookup_source,
            }

        if not candidate:
            return {
                **base,
                "exists_status": "not_found",
                "metadata_match_status": "unknown",
                "support_status": "not_supported",
                "color_label": "Red",
                "reason": lookup_error or "No DOI/title match was found in public APIs.",
                "evidence_id": "",
                "title_similarity": 0.0,
                "author_match_score": 0.0,
                "year_match": False,
                "support_score": 0.0,
                "matched_evidence_text": "",
                "verification_method": lookup_source,
            }

        if not candidate.get("abstract") and cited.get("abstract"):
            candidate["abstract"] = cited.get("abstract")
        if not candidate.get("snippet") and cited.get("snippet"):
            candidate["snippet"] = cited.get("snippet")

        metadata = self._metadata_assessment(cited, candidate)
        support = self._support_assessment(claim.get("claim_text", ""), candidate, lookup_source)
        metadata_status = metadata["metadata_match_status"]
        support_status = support["support_status"]

        try:
            from agent.agent_memory import get_memory
            mem = get_memory()
        except ImportError:
            mem = None

        # 记录验证结果到 memory
        if mem:
            # 更新工作记忆
            mem.set_working("claim_count", mem.get_working("claim_count", 0) + 1)
            if candidate.get("doi"):
                mem.set_working("verified_dois", candidate["doi"])
            if lookup_source:
                mem.set_working("used_providers", lookup_source.split("_")[0])

        if metadata_status == "mismatch" or support_status == "not_supported":
            color = "Red"
            if mem:
                mem.set_working("red_count", mem.get_working("red_count", 0) + 1)
            if support_status == "not_supported":
                if mem:
                    mem.add_experience("verification_error", error_type="幻觉/引文无关",
                        claim_text=claim.get("claim_text", "")[:100],
                        doi=candidate.get("doi", "") or cited.get("doi", ""),
                        reason=f"引文 '{cited.get('title')}' 生成的结论与原意完全不符")
            else:
                if mem:
                    mem.add_experience("verification_error", error_type="元数据伪造",
                        claim_text=claim.get("claim_text", "")[:100],
                        doi=candidate.get("doi", "") or cited.get("doi", ""),
                        reason=f"元数据不匹配: DOI {cited.get('doi')} / 标题 '{cited.get('title')}'")
        elif metadata_status == "match" and support_status == "supports":
            color = "Green"
            if mem:
                mem.set_working("green_count", mem.get_working("green_count", 0) + 1)
                mem.add_success(
                    "引文验证",
                    f"DOI {candidate.get('doi', '')} 通过 {lookup_source} 找到且摘要直接支持结论",
                    context=f"claim={claim.get('claim_id')}, provider={lookup_source}"
                )
        else:
            color = "Yellow"
            if mem:
                mem.set_working("yellow_count", mem.get_working("yellow_count", 0) + 1)

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
        }

    def _metadata_assessment(self, cited: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
        title_score = similarity(cited.get("title", ""), candidate.get("title", ""))
        cited_year = cited.get("year")
        candidate_year = candidate.get("year")
        year_match = not cited_year or not candidate_year or str(cited_year) == str(candidate_year)
        cited_authors = author_last_names(cited.get("authors"))
        candidate_authors = author_last_names(candidate.get("authors"))
        author_score = author_match_score(cited.get("authors"), candidate.get("authors"))
        author_match = not cited_authors or not candidate_authors or author_score > 0
        cited_doi = clean_text(cited.get("doi")).lower()
        candidate_doi = clean_text(candidate.get("doi")).lower()
        doi_match = not cited_doi or not candidate_doi or cited_doi == candidate_doi

        status = "mismatch"
        if cited_doi and candidate_doi and cited_doi != candidate_doi:
            reason = "DOI resolves to a different record."
        elif not year_match:
            reason = f"Year mismatch: cited {cited_year}, public record {candidate_year}."
        elif not author_match:
            reason = "Author metadata does not overlap with the public record."
        elif title_score >= 0.86 and year_match and author_match and doi_match:
            status = "match"
            reason = f"Metadata matches public record (title similarity {title_score:.2f})."
        elif title_score >= 0.65 and doi_match:
            status = "partial_match"
            reason = f"Metadata partially matches; title similarity {title_score:.2f}."
        else:
            reason = f"Metadata mismatch; title similarity {title_score:.2f}."
        return {
            "metadata_match_status": status,
            "metadata_reason": reason,
            "title_similarity": round(title_score, 3),
            "author_match_score": round(author_score, 3),
            "year_match": bool(year_match),
        }

    def _fetch_abstract(self, doi: str) -> str | None:
        """从 Semantic Scholar 通过 DOI 获取摘要。"""
        if not doi:
            return None
        try:
            url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=title,abstract"
            payload = self._request_json(url)
            abstract = payload.get("abstract")
            return clean_text(abstract) if abstract else None
        except Exception:
            return None

    def _support_assessment(self, claim_text: str, candidate: dict[str, Any], lookup_source: str = "") -> dict[str, Any]:
        evidence_text = clean_text(
            f"{candidate.get('title','')}. {candidate.get('abstract') or candidate.get('snippet','')}"
        )
        has_metadata = bool(clean_text(candidate.get("abstract") or candidate.get("snippet")))
        matched_text = self._best_evidence_text(claim_text, candidate)
        paper_doi = candidate.get("doi", "")

        # 如果没有摘要，先用 fetch_abstract 获取
        if not has_metadata and paper_doi:
            abstract = self._fetch_abstract(paper_doi)
            if abstract:
                candidate["abstract"] = abstract
                evidence_text = clean_text(f"{candidate.get('title','')}. {abstract}")

        # 计算词汇重叠度（直接计算，不再通过 LLM tool）
        from agent.utils import overlap_score
        overlap_result = overlap_score(claim_text, evidence_text)

        # 调用多审稿人系统（4 reviewer 并行 + 1 AC 汇总）
        try:
            from agent.multi_agent_judge import judge as multi_judge
            result = multi_judge(claim_text, candidate, overlap_result=overlap_result)
            status = result["support_status"]
            reason = result["support_reason"]
            score = result["support_score"]
        except ImportError:
            # fallback: 直接用 LLM 判断
            if not has_metadata:
                status = "partial_or_uncertain"
                reason = "无可用的论文摘要，且多审稿人模块不可用，无法判断"
                score = 0.5
            else:
                from agent.llm_client import call_llm
                import re, json as _json
                simple_prompt = (
                    f"结论: {claim_text}\n\n证据: {evidence_text}\n\n"
                    "判断证据是否直接支持结论。"
                    '仅输出 JSON: {"status": "supports/partial_or_uncertain/not_supported", "reason": "..."}'
                )
                try:
                    resp = call_llm([{"role": "user", "content": simple_prompt}], temperature=0.0)
                    content = resp.get("content", "")
                    m = re.search(r'\{.*\}', content, re.DOTALL)
                    if m:
                        j = _json.loads(m.group())
                        status = j.get("status", "partial_or_uncertain")
                        reason = f"[fallback] {j.get('reason', '')}"
                    else:
                        status = "partial_or_uncertain"
                        reason = "[fallback] LLM返回格式异常"
                    score = 1.0 if status == "supports" else (0.5 if status == "partial_or_uncertain" else 0.0)
                except Exception as e:
                    status = "partial_or_uncertain"
                    reason = f"[fallback] {e}"
                    score = 0.5

        return {
            "support_status": status,
            "support_reason": reason,
            "support_score": score,
            "matched_evidence_text": matched_text,
        }

    def _best_evidence_text(self, claim_text: str, candidate: dict[str, Any]) -> str:
        text = clean_text(candidate.get("abstract") or candidate.get("snippet") or candidate.get("title"))
        if not text:
            return ""
        best_sentence = clean_text(candidate.get("title"))
        best_score = 0.0
        for sentence in split_sentences(text) or [text]:
            score, _shared = overlap_score(claim_text, sentence)
            if score > best_score:
                best_score = score
                best_sentence = sentence
        return clean_text(best_sentence)[:500]

    def _lookup_crossref_doi(self, doi: str) -> dict[str, Any] | None:
        encoded = urllib.parse.quote(doi, safe="")
        try:
            payload = self._request_json(f"https://api.crossref.org/works/{encoded}")
            return self._normalize_crossref_item(payload.get("message", {}))
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
        return candidate if similarity(title, candidate.get("title", "")) >= 0.55 else None

    def _lookup_openalex_title(self, title: str) -> dict[str, Any] | None:
        params = {"search": title, "per-page": "1"}
        payload = self._request_json("https://api.openalex.org/works?" + urllib.parse.urlencode(params))
        items = payload.get("results", [])
        if not items:
            return None
        item = items[0] if isinstance(items[0], dict) else {}
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
        candidate = {
            "title": clean_text(item.get("title") or item.get("display_name")),
            "authors": authors,
            "year": item.get("publication_year"),
            "doi": clean_text(item.get("doi")).replace("https://doi.org/", ""),
            "venue": clean_text(source.get("display_name")),
            "url": clean_text(primary_location.get("landing_page_url") or item.get("id")),
            "abstract": self._openalex_abstract(item.get("abstract_inverted_index")),
            "snippet": clean_text(item.get("type")),
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

    def _unexpected_error_row(self, claim: dict[str, Any], cited: dict[str, Any], exc: Exception) -> dict[str, Any]:
        return {
            "claim_id": claim.get("claim_id", ""),
            "claim_text": clean_text(claim.get("claim_text")),
            "cited_title": clean_text(cited.get("title")),
            "cited_authors": "; ".join(cited.get("authors") or []),
            "cited_year": cited.get("year") or "",
            "doi": clean_text(cited.get("doi")),
            "retrieval_source": clean_text(cited.get("retrieval_source") or "verification_error"),
            "exists_status": "unknown",
            "metadata_match_status": "unknown",
            "support_status": "partial_or_uncertain",
            "color_label": "Yellow",
            "reason": f"Citation verification failed unexpectedly and requires manual review: {exc}",
            "evidence_id": "",
            "url": clean_text(cited.get("url")),
            "title_similarity": 0.0,
            "author_match_score": 0.0,
            "year_match": False,
            "support_score": 0.0,
            "matched_evidence_text": "",
            "verification_method": "verification_error",
        }
