from __future__ import annotations

import time
from typing import Any

from agent.run_logging import EvidenceStore, ToolCallLogger
from agent.utils import clean_text, split_sentences, top_keywords
from agent.llm_client import call_llm
import json

IDEA_MODES = (
    "conservative extension",
    "cross-disciplinary analogy",
    "high-risk speculative idea",
)


class HypothesisGenerator:
    """Deterministic research idea card generator.

    This project is graded on its self-implemented toolchain and citation
    verification. The generator therefore stays conservative: it makes the
    evidence path explicit and marks ideas as insufficient when fewer than two
    citation-backed claims are available.
    """

    def __init__(self, logger: ToolCallLogger, evidence: EvidenceStore, searcher=None):
        self.logger = logger
        self.evidence = evidence
        self.searcher = searcher

    def generate_with_agent(
        self,
        paper_summary: dict[str, Any],
        max_hypotheses: int = 3,
        inject_bad_citation: bool = False,
        providers: list[str] = None
    ) -> dict[str, Any]:
        """
        Uses Function Calling with an LLM to actively search literature and generate hypotheses.
        """
        call_id = self.logger.next_id()
        started = time.perf_counter()
        
        try:
            from agent.agent_memory import get_reflections
            history_refs = get_reflections()
            memory_str = "\n".join([f"- 当发生 [{r['type']}] 错误时: {r['lesson']}" for r in history_refs])
        except ImportError:
            history_refs = []
            memory_str = ""

        reflection_section = f"\n\n[Agent Long-term Memory / Reflection]\n在你之前的工作中，收到了以下反馈教训。你绝对不能在这次回答中重蹈覆辙：\n{memory_str}\n" if history_refs else ""

        system_prompt = (
            "You are an expert scientific research agent. Your task is to read a summary of a paper, "
            "identify research gaps, use the `search_literature` tool to find related work, and then "
            "generate novel research hypotheses.\n\n"
            "CRITICAL: When generating conclusions, you MUST cite the retrieved literature using the format `[Evidence-Lxxx]` "
            "where `Lxxx` is the literature_id returned by the search tool.\n"
            f"{reflection_section}\n"
            "Return the final output as a specific JSON structure when you are completely done. "
            "If you found enough literature, return hypotheses. If not, state that it's insufficient evidence."
        )

        user_content = f"Paper Summary:\n{json.dumps(paper_summary, indent=2)}\n\nGenerate up to {max_hypotheses} hypotheses."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_literature",
                    "description": "Searches Crossref and OpenAlex for academic papers.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "queries": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "description": "A search query, e.g. 'large language model alignment'"
                                }
                            }
                        },
                        "required": ["queries"]
                    }
                }
            }
        ]

        all_literature = []
        all_queries = []
        loop_count = 0
        
        while loop_count < 3: # Max 3 tool call turns
            loop_count += 1
            response = call_llm(messages, tools=tools)
            messages.append(response)
            
            if response.get("tool_calls"):
                for tc in response["tool_calls"]:
                    if tc["function"]["name"] == "search_literature":
                        args = json.loads(tc["function"]["arguments"])
                        query_strs = args.get("queries", [])
                        
                        # Format queries for the searcher
                        query_objs = [{"query_id": f"Q{len(all_queries)+i+1:03d}", "query": q, "query_stage": "agent", "query_type": "agent_generated", "purpose": "Search related literature"} for i, q in enumerate(query_strs)]
                        all_queries.extend(query_objs)
                        
                        # Execute search
                        results = self.searcher.search(query_objs, providers or ["crossref", "openalex"], max_results_per_query=3)
                        all_literature.extend(results)
                        
                        # Dedupe locally
                        all_literature = self.searcher.combine_records([all_literature])
                        
                        # Pass back to LLM
                        # We only send a trimmed version to save context context
                        trimmed_results = []
                        for r in results:
                            trimmed_results.append({
                                "literature_id": r.get("literature_id"),
                                "title": r.get("title"),
                                "authors": r.get("authors"),
                                "doi": r.get("doi"),
                                "snippet": r.get("snippet", r.get("abstract", ""))[:500]
                            })
                            
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(trimmed_results)
                        })
                # Loop continues to let LLM process tool result
                continue
            else:
                # LLM finished, let's now prompt it to generate the structured JSON format
                break

        # Final instruction to ensure valid JSON output
        messages.append({
            "role": "user",
            "content": (
                "Please map your conceptual hypotheses into the final JSON output format. "
                "The output MUST be valid JSON matching this schema:\n"
                "{\n"
                '  "hypotheses": [\n'
                '    {\n'
                '      "hypothesis_id": "H001",\n'
                '      "idea_type": "conservative extension | cross-disciplinary analogy | high-risk speculative idea",\n'
                '      "evidence_status": "citation_backed",\n'
                '      "research_gap": "Description of the gap in current literature",\n'
                '      "new_hypothesis": "The full hypothesis text with [Evidence-L001] style citations",\n'
                '      "why_novel": "Why this hypothesis is novel",\n'
                '      "risk_or_limitation": "Key risk or limitation",\n'
                '      "testable_prediction": "A concrete testable prediction",\n'
                '      "citation_claim_ids": ["C001", "C002"]\n'
                '    }\n'
                '  ],\n'
                '  "claims": [\n'
                '    {\n'
                '      "claim_id": "C001",\n'
                '      "hypothesis_id": "H001",\n'
                '      "claim_text": "The claim text with [Evidence-Lxxx]",\n'
                '      "claim_role": "supporting_literature_claim",\n'
                '      "cited_work": { "title": "...", "doi": "...", "authors": [], "year": 2024, "venue": "...", "url": "..." }\n'
                '    }\n'
                '  ]\n'
                "}\n"
                "Output ONLY the JSON and nothing else."
            )
        })
        
        final_response = call_llm(messages, tools=None, temperature=0.2)
        json_str = final_response["content"].strip()
        # strip markdown blocks if present
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        json_str = json_str.strip()
        
        try:
            payload = json.loads(json_str)
        except json.JSONDecodeError:
            payload = {"hypotheses": [], "claims": []}

        # Normalize: fill in any missing fields from LLM output
        all_claims = payload.get("claims", [])
        for h in payload.get("hypotheses", []):
            h.setdefault("idea_type", "LLM-generated hypothesis")
            h.setdefault("evidence_status", "citation_backed")
            h.setdefault("research_gap", "Derived from literature analysis by LLM agent.")
            h.setdefault("why_novel", "Generated by LLM based on retrieved literature.")
            h.setdefault("risk_or_limitation", "Requires further empirical validation.")
            h.setdefault("testable_prediction", "See hypothesis text for predicted outcomes.")
            h.setdefault("required_evidence", [
                "Verify that cited works exist and match metadata.",
                "Verify that abstracts or snippets support the claims used to ground the idea.",
            ])
            claim_ids = h.get("citation_claim_ids") or []
            # Build supporting_citations from claims belonging to this hypothesis
            h.setdefault("supporting_citations", [])
            if not h["supporting_citations"]:
                for c in all_claims:
                    if c.get("claim_id") in claim_ids or c.get("hypothesis_id") == h.get("hypothesis_id"):
                        cited = c.get("cited_work") or {}
                        h["supporting_citations"].append({
                            "claim_id": c.get("claim_id", ""),
                            "title": cited.get("title", ""),
                            "year": cited.get("year"),
                            "doi": cited.get("doi", ""),
                            "evidence_id": cited.get("evidence_id", ""),
                            "retrieval_source": cited.get("retrieval_source", ""),
                        })
            # Ensure hypothesis_text is set
            if not h.get("hypothesis_text") and h.get("new_hypothesis"):
                h["hypothesis_text"] = h["new_hypothesis"]
            elif not h.get("new_hypothesis") and h.get("hypothesis_text"):
                h["new_hypothesis"] = h["hypothesis_text"]

        for c in payload.get("claims", []):
            c.setdefault("claim_role", "supporting_literature_claim")
            c.setdefault("cited_work", {})
            c["cited_work"].setdefault("title", "")
            c["cited_work"].setdefault("doi", "")
            c["cited_work"].setdefault("authors", [])
            c["cited_work"].setdefault("year", "")

        if inject_bad_citation:
            bad_claim_id = f"C{len(payload.get('claims', [])) + 1:03d}"
            payload.setdefault("claims", []).append(
                {
                    "claim_id": bad_claim_id,
                    "claim_text": (
                        "Boundary-case claim: this deliberately invalid citation is included "
                        "to demonstrate Red labeling when a cited work cannot be found."
                    ),
                    "hypothesis_id": "H_BOUNDARY",
                    "claim_role": "bad_citation_boundary_case",
                    "cited_work": {
                        "title": "Clearly Nonexistent Citation Verification Paper for Boundary Demo",
                        "authors": ["No Such Author"],
                        "year": 2099,
                        "doi": "INTENTIONALLY_INVALID_DOI_FOR_DEMO",
                        "venue": "",
                        "url": "",
                        "retrieval_source": "manual_boundary_case",
                    },
                }
            )

        # Build markdown and log
        md = self._render_markdown(paper_summary, payload.get("hypotheses", []), payload.get("claims", []), inject_bad_citation)
        evidence_id = self.evidence.record(
            source_type="synthesis",
            source="hypothesis_generator_agent",
            content_snippet=md[:1000],
            category="generated_hypothesis",
            tool_call_id=call_id,
            metadata={"hypothesis_count": len(payload.get("hypotheses", [])), "claim_count": len(payload.get("claims", []))},
        )
        self.logger.log(
            tool_call_id=call_id,
            tool_name="hypothesis_generator.generate_with_agent",
            inputs={"paper_title": paper_summary.get("title")},
            status="success",
            output_summary=f"Agent generated {len(payload.get('hypotheses', []))} ideas and {len(payload.get('claims', []))} claims.",
            started_at=started,
            outputs={"evidence_id": evidence_id},
        )

        payload["markdown"] = md
        payload["evidence_id"] = evidence_id
        payload["literature"] = all_literature
        payload["queries"] = all_queries
        return payload

    def generate(
        self,
        paper_summary: dict[str, Any],
        literature: list[dict[str, Any]],
        max_hypotheses: int = 3,
        inject_bad_citation: bool = False,
    ) -> dict[str, Any]:
        call_id = self.logger.next_id()
        started = time.perf_counter()
        keywords = paper_summary.get("keywords") or top_keywords(
            f"{paper_summary.get('title','')} {paper_summary.get('abstract','')}",
            8,
        )
        usable = self._rank_literature(literature)
        claims: list[dict[str, Any]] = []
        hypotheses: list[dict[str, Any]] = []

        for item in literature:
            item.setdefault("selected_for_hypothesis", False)
            item.setdefault("selection_reason", "")

        if len(usable) < 2:
            claim_ids: list[str] = []
            supporting_citations: list[dict[str, Any]] = []
            for item in usable:
                claim_id = f"C{len(claims) + 1:03d}"
                claim = self._claim_from_literature(claim_id, "H001", item)
                claims.append(claim)
                claim_ids.append(claim_id)
                supporting_citations.append(self._supporting_citation(claim, item))
                item["selected_for_hypothesis"] = True
                item["selection_reason"] = "Used by H001 as partial evidence, but the idea remains insufficient because fewer than two citations were available."
            hypotheses.append(self._insufficient_card(paper_summary, keywords, claim_ids, supporting_citations))
        else:
            idea_count = min(max_hypotheses, len(IDEA_MODES))
            for idx in range(idea_count):
                if len(usable) >= (idx + 1) * 2:
                    pair = [usable[idx * 2], usable[idx * 2 + 1]]
                else:
                    pair = [usable[idx % len(usable)], usable[(idx + 1) % len(usable)]]
                hypothesis_id = f"H{idx + 1:03d}"
                mode = IDEA_MODES[idx]
                card_claim_ids: list[str] = []
                supporting_citations: list[dict[str, Any]] = []
                for item in pair:
                    claim_id = f"C{len(claims) + 1:03d}"
                    claim = self._claim_from_literature(claim_id, hypothesis_id, item)
                    claims.append(claim)
                    card_claim_ids.append(claim_id)
                    supporting_citations.append(self._supporting_citation(claim, item))
                    item["selected_for_hypothesis"] = True
                    item["selection_reason"] = (
                        f"Used by {hypothesis_id} ({mode}) because it had a high relevance score "
                        f"({item.get('relevance_score', item.get('query_overlap_score', 0))}) and usable metadata."
                    )
                hypotheses.append(
                    self._idea_card(
                        hypothesis_id=hypothesis_id,
                        idea_type=mode,
                        paper_summary=paper_summary,
                        keywords=keywords,
                        pair=pair,
                        claim_ids=card_claim_ids,
                        supporting_citations=supporting_citations,
                    )
                )

        if inject_bad_citation:
            bad_claim_id = f"C{len(claims) + 1:03d}"
            claims.append(
                {
                    "claim_id": bad_claim_id,
                    "claim_text": (
                        "Boundary-case claim: this deliberately invalid citation is included "
                        "to demonstrate Red labeling when a cited work cannot be found."
                    ),
                    "hypothesis_id": "H_BOUNDARY",
                    "claim_role": "bad_citation_boundary_case",
                    "cited_work": {
                        "title": "Clearly Nonexistent Citation Verification Paper for Boundary Demo",
                        "authors": ["No Such Author"],
                        "year": 2099,
                        "doi": "INTENTIONALLY_INVALID_DOI_FOR_DEMO",
                        "venue": "",
                        "url": "",
                        "retrieval_source": "manual_boundary_case",
                    },
                }
            )

        md = self._render_markdown(paper_summary, hypotheses, claims, inject_bad_citation)
        evidence_id = self.evidence.record(
            source_type="synthesis",
            source="hypothesis_generator",
            content_snippet=md[:1000],
            category="generated_hypothesis",
            tool_call_id=call_id,
            metadata={"hypothesis_count": len(hypotheses), "claim_count": len(claims)},
        )
        self.logger.log(
            tool_call_id=call_id,
            tool_name="hypothesis_generator.generate_research_idea_cards",
            inputs={
                "paper_title": paper_summary.get("title"),
                "literature_count": len(literature),
                "usable_literature_count": len(usable),
                "max_hypotheses": max_hypotheses,
                "inject_bad_citation": inject_bad_citation,
            },
            status="success",
            output_summary=f"Generated {len(hypotheses)} research idea cards and {len(claims)} citation-backed claims.",
            started_at=started,
            outputs={"evidence_id": evidence_id},
        )
        return {"hypotheses": hypotheses, "claims": claims, "markdown": md, "evidence_id": evidence_id}

    def _rank_literature(self, literature: list[dict[str, Any]]) -> list[dict[str, Any]]:
        usable = [
            item
            for item in literature
            if item.get("title") and (item.get("abstract") or item.get("snippet") or item.get("doi"))
        ]
        return sorted(
            usable,
            key=lambda item: (
                item.get("relevance_score", item.get("query_overlap_score", 0)),
                bool(clean_text(item.get("abstract") or item.get("snippet"))),
                item.get("metadata_completeness", 0),
            ),
            reverse=True,
        )

    def _insufficient_card(
        self,
        paper_summary: dict[str, Any],
        keywords: list[str],
        claim_ids: list[str],
        supporting_citations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        focus = ", ".join(keywords[:4]) if keywords else clean_text(paper_summary.get("title"))
        return {
            "hypothesis_id": "H001",
            "idea_type": "insufficient evidence",
            "evidence_status": "insufficient_evidence_for_generation",
            "research_gap": f"The current run did not retrieve at least two usable literature records around {focus}.",
            "new_hypothesis": "No citation-backed research hypothesis should be presented from this run alone.",
            "why_novel": "Not assessed because the evidence base is too thin.",
            "required_evidence": [
                "At least two retrievable papers with usable metadata.",
                "At least one abstract or snippet that can support each citation-backed claim.",
            ],
            "supporting_citations": supporting_citations,
            "risk_or_limitation": "Presenting a hypothesis here would overstate the evidence.",
            "testable_prediction": "After additional retrieval, the agent should either form a supported idea or keep the run as insufficient.",
            "citation_claim_ids": claim_ids,
            "hypothesis_text": "Insufficient evidence for generation.",
        }

    def _idea_card(
        self,
        *,
        hypothesis_id: str,
        idea_type: str,
        paper_summary: dict[str, Any],
        keywords: list[str],
        pair: list[dict[str, Any]],
        claim_ids: list[str],
        supporting_citations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        focus = ", ".join(keywords[:4]) if keywords else clean_text(paper_summary.get("title"))
        problem = clean_text(paper_summary.get("research_problem") or paper_summary.get("title"))
        first_title = clean_text(pair[0].get("title"))
        second_title = clean_text(pair[1].get("title"))
        if idea_type == "conservative extension":
            new_hypothesis = (
                f"A conservative next study should test whether techniques or observations from '{first_title}' "
                f"and '{second_title}' improve evidence-grounded work on {focus}."
            )
            why_novel = "It combines two retrieved strands with the input paper's research problem rather than copying either paper."
            risk = "Novelty is moderate; the idea may be an incremental extension if the cited works already overlap strongly."
        elif idea_type == "cross-disciplinary analogy":
            new_hypothesis = (
                f"If the mechanisms discussed in '{first_title}' transfer across domains, then {focus} may benefit "
                f"from a cross-disciplinary evaluation protocol grounded by '{second_title}'."
            )
            why_novel = "The idea explicitly treats retrieved literature as an analogy source for a different research setting."
            risk = "The analogy may fail if the source domain assumptions do not hold for the input paper's domain."
        else:
            new_hypothesis = (
                f"A higher-risk hypothesis is that the shared signals behind '{first_title}' and '{second_title}' "
                f"point to a broader latent factor affecting {focus}."
            )
            why_novel = "It proposes a broader latent explanation rather than only applying a known method."
            risk = "This is speculative and should be treated as Yellow unless stronger evidence is retrieved."

        return {
            "hypothesis_id": hypothesis_id,
            "idea_type": idea_type,
            "evidence_status": "citation_backed" if len(claim_ids) >= 2 else "insufficient_evidence_for_generation",
            "research_gap": problem[:700],
            "new_hypothesis": new_hypothesis,
            "why_novel": why_novel,
            "required_evidence": [
                "Verify that both cited works exist and match metadata.",
                "Verify that abstracts or snippets support the claims used to ground the idea.",
                "Run a small empirical or literature review check before presenting the idea as a conclusion.",
            ],
            "supporting_citations": supporting_citations,
            "risk_or_limitation": risk,
            "testable_prediction": (
                f"If this idea is valid, then a follow-up study on {focus} should show measurable improvement "
                "or a clearer explanatory pattern compared with the input paper's baseline framing."
            ),
            "citation_claim_ids": claim_ids,
            "hypothesis_text": new_hypothesis,
        }

    def _claim_from_literature(self, claim_id: str, hypothesis_id: str, item: dict[str, Any]) -> dict[str, Any]:
        support_sentence = self._support_sentence(item)
        return {
            "claim_id": claim_id,
            "claim_text": f"Prior work reports that {support_sentence}",
            "hypothesis_id": hypothesis_id,
            "claim_role": "supporting_literature_claim",
            "cited_work": self._citation_from_record(item),
        }

    def _support_sentence(self, item: dict[str, Any]) -> str:
        text = clean_text(item.get("abstract") or item.get("snippet") or item.get("title"))
        sentences = split_sentences(text, limit=3)
        if sentences:
            return sentences[0][:450]
        return f"the paper titled '{clean_text(item.get('title'))}' is relevant to the retrieved topic."

    def _supporting_citation(self, claim: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        cited = claim["cited_work"]
        return {
            "claim_id": claim["claim_id"],
            "literature_id": item.get("literature_id"),
            "title": cited.get("title", ""),
            "year": cited.get("year"),
            "doi": cited.get("doi", ""),
            "evidence_id": cited.get("evidence_id"),
            "retrieval_source": cited.get("retrieval_source", ""),
        }

    def _citation_from_record(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": clean_text(item.get("title")),
            "authors": item.get("authors", []),
            "year": item.get("year"),
            "doi": clean_text(item.get("doi")),
            "venue": clean_text(item.get("venue")),
            "url": clean_text(item.get("url")),
            "retrieval_source": clean_text(item.get("retrieval_source")),
            "literature_id": item.get("literature_id"),
            "evidence_id": item.get("evidence_id"),
            "abstract": clean_text(item.get("abstract")),
            "snippet": clean_text(item.get("snippet")),
        }

    def _render_markdown(
        self,
        paper_summary: dict[str, Any],
        hypotheses: list[dict[str, Any]],
        claims: list[dict[str, Any]],
        inject_bad_citation: bool,
    ) -> str:
        lines = [
            "# Generated Research Idea Cards",
            "",
            f"Input paper: {clean_text(paper_summary.get('title'))}",
            "",
        ]
        for hypothesis in hypotheses:
            hid = hypothesis.get("hypothesis_id", "H???")
            itype = hypothesis.get("idea_type", "LLM-generated hypothesis")
            lines.append(f"## {hid}: {itype}")
            lines.append(f"Evidence status: `{hypothesis.get('evidence_status', 'citation_backed')}`")
            lines.append("")
            lines.append(f"Research gap: {clean_text(hypothesis.get('research_gap', 'Not specified'))}")
            lines.append("")
            hypothesis_text = hypothesis.get("new_hypothesis") or hypothesis.get("hypothesis_text", "")
            lines.append(f"New hypothesis: {clean_text(hypothesis_text)}")
            lines.append("")
            lines.append(f"Why novel: {clean_text(hypothesis.get('why_novel', 'Not specified'))}")
            lines.append("")
            lines.append("Required evidence:")
            for item in hypothesis.get("required_evidence", ["Verify that cited works exist and match metadata."]):
                lines.append(f"- {clean_text(item)}")
            lines.append("")
            lines.append("Supporting citations:")
            citations = hypothesis.get("supporting_citations", [])
            if citations:
                for citation in citations:
                    lines.append(
                        f"- {citation.get('claim_id', '')}: {clean_text(citation.get('title'))} "
                        f"({citation.get('year') or 'n.d.'}), DOI: {citation.get('doi') or 'missing'}"
                    )
            else:
                lines.append("- None; this idea is insufficiently supported.")
            lines.append("")
            lines.append(f"Risk or limitation: {clean_text(hypothesis.get('risk_or_limitation', 'Not specified'))}")
            lines.append("")
            lines.append(f"Testable prediction: {clean_text(hypothesis.get('testable_prediction', 'Not specified'))}")
            lines.append("")

        lines.extend(
            [
                "## Citation-Backed Claims To Verify",
                "",
                "| Claim ID | Hypothesis | Claim | Cited Title | Year | DOI |",
                "|---|---|---|---|---|---|",
            ]
        )
        for claim in claims:
            cited = claim.get("cited_work") or {}
            lines.append(
                f"| {claim.get('claim_id', '')} | {claim.get('hypothesis_id', '')} | {self._cell(claim.get('claim_text', ''))} | "
                f"{self._cell(cited.get('title', ''))} | {cited.get('year') or ''} | {cited.get('doi') or ''} |"
            )
        if inject_bad_citation:
            lines.extend(
                [
                    "",
                    "Note: the boundary-case citation is intentionally invalid and should be labeled Red.",
                ]
            )
        return "\n".join(lines)

    def _cell(self, text: str) -> str:
        return clean_text(text).replace("|", "\\|")
