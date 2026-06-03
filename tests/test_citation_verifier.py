from __future__ import annotations

from pathlib import Path

from agent.citation_verifier import CitationVerifier
from agent.run_logging import EvidenceStore, ToolCallLogger
from agent.utils import author_last_names


def make_verifier(tmp_path: Path) -> CitationVerifier:
    return CitationVerifier(ToolCallLogger(tmp_path), EvidenceStore(tmp_path))


def test_author_last_names_handles_last_comma_initial_format() -> None:
    assert author_last_names(["Mascioli, C.", "Gu, A.", "Wang, Y."]) == {"mascioli", "gu", "wang"}
    assert author_last_names(["Patrick Lewis", "Ethan Perez"]) == {"lewis", "perez"}


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


def test_yellow_when_year_mismatches_otherwise_matching_public_record(tmp_path: Path) -> None:
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
    assert row["color_label"] == "Yellow"
    assert row["metadata_match_status"] == "partial_match"
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


def test_yellow_when_public_api_lookup_fails(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C006",
        "claim_text": "Prior work reports that citation verification supports evidence-grounded writing.",
        "cited_work": {
            "title": "Citation Verification for Evidence Grounded Writing",
            "authors": ["A. Researcher"],
            "year": 2026,
            "doi": "10.0000/example",
        },
    }
    row = verifier._classify_claim_support(
        claim,
        claim["cited_work"],
        None,
        "lookup_error",
        "Crossref DOI lookup failed: HTTP Error 429: Too Many Requests",
    )
    assert row["color_label"] == "Yellow"
    assert row["exists_status"] == "unknown"
    assert row["support_status"] == "partial_or_uncertain"


def test_openalex_title_lookup_handles_null_source(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)

    def fake_request_json(_url: str) -> dict:
        return {
            "results": [
                {
                    "title": "Citation Verification for Scientific Writing",
                    "authorships": [{"author": {"display_name": "A. Researcher"}}],
                    "publication_year": 2024,
                    "doi": "https://doi.org/10.0000/example",
                    "primary_location": {"source": None, "landing_page_url": "https://example.test/paper"},
                    "abstract_inverted_index": {"Citation": [0], "verification": [1], "works": [2]},
                    "type": "article",
                }
            ]
        }

    verifier._request_json = fake_request_json  # type: ignore[method-assign]
    candidate = verifier._lookup_openalex_title("Citation Verification for Scientific Writing")
    assert candidate is not None
    assert candidate["venue"] == ""
    assert candidate["url"] == "https://example.test/paper"


def test_verifier_error_becomes_yellow_instead_of_crashing(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C007",
        "claim_text": "Boundary claim.",
        "cited_work": {"title": "Some Paper", "authors": ["A. Researcher"], "year": 2024},
    }

    def broken_lookup(_cited: dict):
        raise AttributeError("unexpected provider shape")

    verifier._lookup_citation = broken_lookup  # type: ignore[method-assign]
    row = verifier.verify_one(claim)
    assert row["color_label"] == "Yellow"
    assert row["verification_method"] == "verification_error"
    assert "manual review" in row["reason"]
