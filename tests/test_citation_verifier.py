from __future__ import annotations

from pathlib import Path

from agent.citation_verifier import CitationVerifier
from agent.run_logging import EvidenceStore, ToolCallLogger


def make_verifier(tmp_path: Path) -> CitationVerifier:
    return CitationVerifier(ToolCallLogger(tmp_path), EvidenceStore(tmp_path))


def test_green_when_metadata_and_abstract_support(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C001",
        "claim_text": "Prior work reports that retrieval augmented generation improves factual grounding for language model answers.",
        "cited_work": {
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "authors": ["Patrick Lewis"],
            "year": 2020,
            "doi": "10.0000/example",
        },
    }
    cited = claim["cited_work"]
    candidate = {
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "authors": ["Patrick Lewis"],
        "year": 2020,
        "doi": "10.0000/example",
        "url": "https://example.test",
        "abstract": (
            "Retrieval augmented generation combines parametric language models with retrieved passages. "
            "The method improves factual grounding for knowledge intensive natural language processing tasks."
        ),
    }
    row = verifier._classify_claim_support(claim, cited, candidate, "fixture", "")
    assert row["color_label"] == "Green"
    assert row["metadata_match_status"] == "match"
    assert row["support_status"] == "supports"
    assert row["title_similarity"] >= 0.99
    assert row["support_score"] > 0
    assert row["matched_evidence_text"]


def test_yellow_when_existing_paper_only_partially_supports(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C002",
        "claim_text": "Prior work reports that citation verification fully solves hallucination in scientific writing.",
        "cited_work": {
            "title": "Citation Verification for Scientific Writing",
            "authors": ["A. Researcher"],
            "year": 2024,
        },
    }
    cited = claim["cited_work"]
    candidate = {
        "title": "Citation Verification for Scientific Writing",
        "authors": ["A. Researcher"],
        "year": 2024,
        "doi": "",
        "url": "https://example.test",
        "abstract": "This paper studies citation verification and scientific writing workflows.",
    }
    row = verifier._classify_claim_support(claim, cited, candidate, "fixture", "")
    assert row["color_label"] == "Yellow"
    assert row["exists_status"] == "exists"


def test_yellow_when_existing_paper_has_no_abstract(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C004",
        "claim_text": "Prior work reports that citation verification is useful for scientific writing.",
        "cited_work": {
            "title": "Citation Verification for Scientific Writing",
            "authors": ["A. Researcher"],
            "year": 2024,
        },
    }
    candidate = {
        "title": "Citation Verification for Scientific Writing",
        "authors": ["A. Researcher"],
        "year": 2024,
        "doi": "",
        "url": "https://example.test",
        "abstract": "",
        "snippet": "",
    }
    row = verifier._classify_claim_support(claim, claim["cited_work"], candidate, "fixture", "")
    assert row["color_label"] == "Yellow"
    assert row["support_status"] == "partial_or_uncertain"


def test_red_when_year_mismatches_public_record(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C005",
        "claim_text": "Prior work reports that retrieval augmented generation improves factual grounding.",
        "cited_work": {
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "authors": ["Patrick Lewis"],
            "year": 2099,
            "doi": "10.0000/example",
        },
    }
    candidate = {
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "authors": ["Patrick Lewis"],
        "year": 2020,
        "doi": "10.0000/example",
        "url": "https://example.test",
        "abstract": "Retrieval augmented generation improves factual grounding for knowledge intensive tasks.",
    }
    row = verifier._classify_claim_support(claim, claim["cited_work"], candidate, "fixture", "")
    assert row["color_label"] == "Red"
    assert row["metadata_match_status"] == "mismatch"
    assert row["year_match"] is False


def test_red_when_citation_not_found(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C003",
        "claim_text": "Boundary claim.",
        "cited_work": {"title": "No Such Paper", "authors": ["Nobody"], "year": 2099},
    }
    row = verifier._classify_claim_support(
        claim,
        claim["cited_work"],
        None,
        "fixture",
        "No matching citation found.",
    )
    assert row["color_label"] == "Red"
    assert row["exists_status"] == "not_found"
    assert row["verification_method"] == "fixture"
