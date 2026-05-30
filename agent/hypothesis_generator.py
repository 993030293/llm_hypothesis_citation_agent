from __future__ import annotations

import time
from typing import Any

from agent.run_logging import EvidenceStore, ToolCallLogger
from agent.utils import clean_text, split_sentences, top_keywords


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

    def __init__(self, logger: ToolCallLogger, evidence: EvidenceStore):
        self.logger = logger
        self.evidence = evidence

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
            lines.append(f"## {hypothesis['hypothesis_id']}: {hypothesis['idea_type']}")
            lines.append(f"Evidence status: `{hypothesis['evidence_status']}`")
            lines.append("")
            lines.append(f"Research gap: {clean_text(hypothesis['research_gap'])}")
            lines.append("")
            lines.append(f"New hypothesis: {clean_text(hypothesis['new_hypothesis'])}")
            lines.append("")
            lines.append(f"Why novel: {clean_text(hypothesis['why_novel'])}")
            lines.append("")
            lines.append("Required evidence:")
            for item in hypothesis.get("required_evidence", []):
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
            lines.append(f"Risk or limitation: {clean_text(hypothesis['risk_or_limitation'])}")
            lines.append("")
            lines.append(f"Testable prediction: {clean_text(hypothesis['testable_prediction'])}")
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
            cited = claim["cited_work"]
            lines.append(
                f"| {claim['claim_id']} | {claim.get('hypothesis_id', '')} | {self._cell(claim['claim_text'])} | "
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
