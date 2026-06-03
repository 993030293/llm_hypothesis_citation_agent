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
        support = self._support_assessment(claim.get("claim_text", ""), candidate)
        metadata_status = metadata["metadata_match_status"]
        support_status = support["support_status"]
        
        try:
            from agent.agent_memory import add_reflection
        except ImportError:
            add_reflection = lambda t, l: None

        if metadata_status == "mismatch" or support_status == "not_supported":
            color = "Red"
            if support_status == "not_supported":
                add_reflection("幻觉/引文无关", f"我之前针对引文 '{cited.get('title')}' 生成的结论与原意完全不符！下次提出 Claim 前必须精读检索返回的文献上下文，切忌自由发挥。")
            else:
                add_reflection("元数据伪造", f"我错误地伪造了 {cited.get('doi')} 对应的论文元数据，这构成了学术不端。下一次必须100%参照 search_literature 工具的真实返回使用！")
        elif metadata_status == "match" and support_status == "supports":
            color = "Green"
        else:
            color = "Yellow"
            if support_status == "partial_or_uncertain":
                add_reflection("过度推断", f"我在得出关于 '{claim.get('claim_text')[:30]}...' 的结论时，跨学科联想过大，导致文献原文并没有直接字句支撑。下次在做类似推断时，应在文本中加上'可能有联系'的限定词。")

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

    def _support_assessment(self, claim_text: str, candidate: dict[str, Any]) -> dict[str, Any]:
        evidence_text = clean_text(
            f"{candidate.get('title','')}. {candidate.get('abstract') or candidate.get('snippet','')}"
        )
        has_metadata = bool(clean_text(candidate.get("abstract") or candidate.get("snippet")))
        matched_text = self._best_evidence_text(claim_text, candidate)
        paper_doi = candidate.get("doi", "")

        paper_doi_str = f"论文 DOI: {paper_doi}\n" if paper_doi else ""

        if has_metadata:
            intro = (
                f"结论 (Claim): {claim_text}\n"
                f"证据文本 (Evidence): {evidence_text}\n\n"
            )
        else:
            intro = (
                f"结论 (Claim): {claim_text}\n"
                f"{paper_doi_str}"
                "注意：当前 API 未返回该文献的摘要，你需要先用 `fetch_abstract` 工具获取摘要，再进行判断。\n\n"
            )

        prompt = (
            "你是一个严厉的学术事实核查大模型。请判断提供的'证据文本'是否直接且明确地支持了'结论'。\n\n"
            f"{intro}"
            "判断规则：\n"
            "1. 若证据明确具有对应的逻辑或数据支持结论，状态为 'supports'。\n"
            "2. 若证据在主题上相关，但仅仅是模型的发散推断，没有直接证据覆盖，状态为 'partial_or_uncertain'。\n"
            "3. 若证据与结论完全不相关、出现自相矛盾、或者属于捏造，状态定为 'not_supported'。\n"
            "4. 如果你尝试 fetch_abstract 后仍然没有摘要，才返回 partial_or_uncertain。\n\n"
            "你有以下工具可用：\n"
            "  - fetch_abstract：通过 DOI 从 Semantic Scholar 获取论文摘要\n"
            "  - calculate_overlap：计算 claim 与 evidence 的词汇重叠度\n"
            "建议先尝试 fetch_abstract（如果没有可用摘要），再用 calculate_overlap 辅助判断。\n"
            "请注意：你必须调用工具（fetch_abstract / calculate_overlap）来辅助判断，或者直接返回 JSON。\n"
            "严禁输出解释性文字——如果不用工具，就直接输出下面格式的 JSON，不要输出其他任何内容：\n"
            '{"status": "supports或partial_or_uncertain或not_supported", "reason": "你的中文详细打分理由"}'
        )

        messages = [{"role": "user", "content": prompt}]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "fetch_abstract",
                    "description": "通过 DOI 从 Semantic Scholar 获取论文摘要。当 API 未返回摘要时调用此工具。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "doi": {"type": "string", "description": "论文 DOI，例如 10.1234/abc567"}
                        },
                        "required": ["doi"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_overlap",
                    "description": "计算学术结论（Claim）与原文证据（Evidence）之间的词汇重合度和字符串相似度。辅助判断它们是否存在直接包含关系。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text1": {"type": "string", "description": "要比较的文本段落1"},
                            "text2": {"type": "string", "description": "要比较的文本段落2"}
                        },
                        "required": ["text1", "text2"]
                    }
                }
            }
        ]

        try:
            from agent.llm_client import call_llm
            from agent.utils import overlap_score, similarity

            # 最大允许三次交互（fetch_abstract → calculate_overlap → 最终判断）
            for _ in range(3):
                resp = call_llm(messages, tools=tools, temperature=0.0)
                messages.append(resp)

                if resp.get("tool_calls"):
                    for tc in resp["tool_calls"]:
                        if tc["function"]["name"] == "fetch_abstract":
                            args = json.loads(tc["function"]["arguments"])
                            doi = args.get("doi", paper_doi)
                            abstract = self._fetch_abstract(doi)
                            if abstract:
                                tool_result = json.dumps({"abstract": abstract}, ensure_ascii=False)
                            else:
                                tool_result = json.dumps({"abstract": None, "error": "Semantic Scholar 也未找到该文献的摘要"}, ensure_ascii=False)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": tool_result
                            })
                        elif tc["function"]["name"] == "calculate_overlap":
                            args = json.loads(tc["function"]["arguments"])
                            t1 = args.get("text1", "")
                            t2 = args.get("text2", "")
                            score, shared = overlap_score(t1, t2)
                            sim = similarity(t1, t2)
                            tool_result = json.dumps({
                                "overlap_score": round(score, 3),
                                "shared_keywords": shared[:10],
                                "string_similarity": round(sim, 3)
                            }, ensure_ascii=False)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": tool_result
                            })
                    continue  # 工具调用完成，继续向大模型请求下一步

                # 如果没有工具调用且是普通文本
                content_text = resp.get("content", "").strip()
                # 检查是否已经有 JSON 了
                if re.search(r'\{.*\}', content_text, re.DOTALL):
                    break  # 包含 JSON，跳出循环去解析
                # 没有 JSON 且没有工具调用：强制提醒调用工具
                messages.append({
                    "role": "user",
                    "content": "请直接调用 fetch_abstract 工具获取摘要，或直接输出 JSON 结果。不要输出解释性文字。"
                })
                continue

            # 找到最后一个有实际内容的 assistant 回复
            content = ""
            for msg in reversed(messages):
                if msg.get("role") == "assistant" and msg.get("content", "").strip():
                    content = msg["content"].strip()
                    break
            if not content:
                content = '{"status": "partial_or_uncertain", "reason": "LLM未能返回有效判决内容，回退为不确定"}'
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            if not content:
                content = '{"status": "partial_or_uncertain", "reason": "LLM未能返回有效判决内容，回退为不确定"}'
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group()
            res = json.loads(content)
            status = res.get("status", "partial_or_uncertain")
            reason = f"[模型判决] {res.get('reason', '经交叉复核判断')}"
        except Exception as e:
            import logging
            logger = logging.getLogger("hypothesis_qqbot.verifier")
            logger.warning("LLM judge failed, raw content[:200]=%s, error=%s", content[:200] if content else "(empty)", e)
            status = "partial_or_uncertain"
            reason = f"大模型裁判调用失败回退: {e}"

        return {
            "support_status": status,
            "support_reason": reason,
            "support_score": 1.0 if status == "supports" else (0.5 if status == "partial_or_uncertain" else 0.0),
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
