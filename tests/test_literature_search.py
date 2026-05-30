from __future__ import annotations

import json
from pathlib import Path

from agent.literature_search import LiteratureSearcher
from agent.run_logging import EvidenceStore, ToolCallLogger


def test_literature_records_get_research_fields(tmp_path: Path) -> None:
    searcher = LiteratureSearcher(ToolCallLogger(tmp_path), EvidenceStore(tmp_path))
    rows = searcher._dedupe_and_record(
        [
            {
                "title": "Citation Verification for Scientific Writing",
                "authors": ["A. Researcher"],
                "year": 2024,
                "doi": "10.0000/example",
                "venue": "Demo Journal",
                "url": "https://example.test",
                "abstract": "This paper studies citation verification for scientific writing.",
                "snippet": "",
                "query_id": "Q001",
                "query": "citation verification scientific writing",
                "query_stage": "initial",
                "query_type": "seed",
                "retrieval_source": "fixture",
                "retrieved_at": "2026-01-01T00:00:00+00:00",
                "query_overlap_score": 0.5,
                "query_overlap_terms": ["citation", "verification"],
            }
        ]
    )
    assert rows[0]["relevance_score"] > 0
    assert rows[0]["metadata_completeness"] > 0
    assert rows[0]["abstract_available"] is True
    assert rows[0]["dedupe_key"] == "doi:10.0000/example"
    assert rows[0]["selected_for_hypothesis"] is False
    assert rows[0]["selection_reason"] == ""


def test_provider_failure_is_logged(tmp_path: Path) -> None:
    searcher = LiteratureSearcher(ToolCallLogger(tmp_path), EvidenceStore(tmp_path))

    def fail(_query: str, _max_results: int):
        raise RuntimeError("forced API failure")

    searcher._query_crossref = fail  # type: ignore[method-assign]
    rows = searcher.search(
        [{"query_id": "Q001", "query": "citation verification", "query_stage": "initial", "query_type": "seed"}],
        ["crossref"],
        max_results_per_query=1,
    )
    assert rows == []
    log_rows = [
        json.loads(line)
        for line in (tmp_path / "tool_calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert log_rows[0]["status"] == "error"
    assert "forced API failure" in log_rows[0]["error"]

