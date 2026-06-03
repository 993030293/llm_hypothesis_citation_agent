from __future__ import annotations

import time
from typing import Any

from agent.run_logging import ToolCallLogger
from agent.utils import clean_text, top_keywords


class QueryPlanner:
    """Build search queries from the parsed PDF summary."""

    def __init__(self, logger: ToolCallLogger):
        self.logger = logger

    def plan(self, paper_summary: dict[str, Any], max_queries: int = 5) -> list[dict[str, Any]]:
        call_id = self.logger.next_id()
        started = time.perf_counter()
        title = clean_text(paper_summary.get("title"))
        abstract = clean_text(paper_summary.get("abstract"))
        problem = clean_text(paper_summary.get("research_problem"))
        keywords = paper_summary.get("keywords") or top_keywords(f"{title} {abstract} {problem}", 12)

        candidates = [
            {
                "query": " ".join([title, *keywords[:3]]),
                "purpose": "Find papers directly related to the input paper topic.",
                "required_terms": keywords[:3],
            },
            {
                "query": " ".join(keywords[:6]),
                "purpose": "Find thematically related literature from extracted keywords.",
                "required_terms": keywords[:4],
            },
            {
                "query": " ".join(top_keywords(problem, 7) or keywords[:7]),
                "purpose": "Find papers around the research problem or gap.",
                "required_terms": top_keywords(problem, 4) or keywords[:4],
            },
            {
                "query": " ".join([*keywords[:4], "survey", "review"]),
                "purpose": "Find broader review literature for citation grounding.",
                "required_terms": keywords[:3],
            },
            {
                "query": " ".join([*keywords[:3], "application", "cross-disciplinary"]),
                "purpose": "Find cross-disciplinary transfer opportunities.",
                "required_terms": keywords[:3],
            },
        ]

        queries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in candidates:
            query_text = clean_text(candidate["query"])
            if len(query_text) < 8:
                continue
            norm = query_text.lower()
            if norm in seen:
                continue
            seen.add(norm)
            queries.append(
                self._make_query(
                    query_id=f"Q{len(queries) + 1:03d}",
                    query=query_text,
                    purpose=candidate["purpose"],
                    required_terms=candidate["required_terms"],
                    source_keywords=keywords,
                    query_stage="initial",
                    query_type="seed",
                )
            )
            if len(queries) >= max_queries:
                break

        self.logger.log(
            tool_call_id=call_id,
            tool_name="query_planner.generate_queries",
            inputs={"title": title, "keywords": keywords, "max_queries": max_queries},
            status="success",
            output_summary=f"Generated {len(queries)} literature search queries.",
            started_at=started,
            outputs={"query_ids": [q["query_id"] for q in queries]},
        )
        return queries

    def plan_followup(
        self,
        paper_summary: dict[str, Any],
        initial_queries: list[dict[str, Any]],
        literature: list[dict[str, Any]],
        max_queries: int = 4,
    ) -> list[dict[str, Any]]:
        call_id = self.logger.next_id()
        started = time.perf_counter()
        title = clean_text(paper_summary.get("title"))
        abstract = clean_text(paper_summary.get("abstract"))
        problem = clean_text(paper_summary.get("research_problem"))
        base_keywords = paper_summary.get("keywords") or top_keywords(f"{title} {abstract} {problem}", 12)
        literature_text = " ".join(
            clean_text(f"{item.get('title', '')} {item.get('abstract', '')}") for item in literature[:8]
        )
        literature_terms = [term for term in top_keywords(literature_text, 12) if term not in base_keywords]
        seed_terms = base_keywords[:5] + literature_terms[:4]

        candidates = [
            {
                "query": " ".join([*seed_terms[:5], "method", "framework"]),
                "purpose": "Follow-up method query from initial retrieval results.",
                "query_type": "method-oriented",
                "required_terms": seed_terms[:4],
            },
            {
                "query": " ".join([*seed_terms[:4], "application", "cross disciplinary"]),
                "purpose": "Follow-up application query for cross-disciplinary hypothesis transfer.",
                "query_type": "application-oriented",
                "required_terms": seed_terms[:4],
            },
            {
                "query": " ".join([*seed_terms[:4], "limitations", "challenge"]),
                "purpose": "Follow-up limitation query to surface uncertainty or contradiction.",
                "query_type": "limitation-oriented",
                "required_terms": seed_terms[:4],
            },
            {
                "query": " ".join([*seed_terms[:4], "survey", "review"]),
                "purpose": "Follow-up review query for broader grounding literature.",
                "query_type": "review-oriented",
                "required_terms": seed_terms[:4],
            },
        ]

        seen = {clean_text(query.get("query")).lower() for query in initial_queries}
        followups: list[dict[str, Any]] = []
        start_idx = len(initial_queries) + 1
        for candidate in candidates:
            query_text = clean_text(candidate["query"])
            if len(query_text) < 8:
                continue
            norm = query_text.lower()
            if norm in seen:
                continue
            seen.add(norm)
            followups.append(
                self._make_query(
                    query_id=f"Q{start_idx + len(followups):03d}",
                    query=query_text,
                    purpose=candidate["purpose"],
                    required_terms=candidate["required_terms"],
                    source_keywords=base_keywords,
                    query_stage="followup",
                    query_type=candidate["query_type"],
                )
            )
            if len(followups) >= max_queries:
                break

        self.logger.log(
            tool_call_id=call_id,
            tool_name="query_planner.generate_followup_queries",
            inputs={
                "title": title,
                "initial_query_count": len(initial_queries),
                "literature_count": len(literature),
                "max_queries": max_queries,
            },
            status="success",
            output_summary=f"Generated {len(followups)} follow-up literature search queries.",
            started_at=started,
            outputs={"query_ids": [q["query_id"] for q in followups]},
        )
        return followups

    def _make_query(
        self,
        *,
        query_id: str,
        query: str,
        purpose: str,
        required_terms: list[str],
        source_keywords: list[str],
        query_stage: str,
        query_type: str,
    ) -> dict[str, Any]:
        return {
            "query_id": query_id,
            "query": clean_text(query)[:300],
            "purpose": purpose,
            "required_terms": required_terms,
            "source_keywords": source_keywords,
            "query_stage": query_stage,
            "query_type": query_type,
        }
