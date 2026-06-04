from __future__ import annotations

import json
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
            "Retrieval augmented generation improves factual grounding for language model answers. "
            "The method improves factual grounding for knowledge intensive natural language processing tasks."
        ),
        "source_agreement_count": 2,
        "source_agreement_summary": "crossref, semantic_scholar",
    }
    row = verifier._classify_claim_support(claim, cited, candidate, "fixture", "")
    assert row["color_label"] == "Green"
    assert row["green_gate_passed"] is True
    assert row["metadata_match_status"] == "match"
    assert row["support_status"] == "supports"
    assert row["error_type"] == ""
    assert row["title_similarity"] >= 0.99
    assert row["support_score"] > 0
    assert row["matched_evidence_text"]
    assert row["supporting_sentence"]


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
    assert row["error_type"] == "supporting_sentence_missing"


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
    assert row["error_type"] == "year_mismatch_requires_review"


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
    assert row["error_type"] == "not_found"
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
    assert row["error_type"] == "api_inconclusive"


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


def test_invalid_doi_is_red_with_error_type(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    row = verifier.verify_one(
        {
            "claim_id": "C008",
            "claim_text": "Boundary claim.",
            "cited_work": {"title": "A Paper", "authors": ["A. Researcher"], "year": 2024, "doi": "bad-doi"},
        }
    )
    assert row["color_label"] == "Red"
    assert row["error_type"] == "invalid_doi"


def test_fulltext_sentence_can_supply_supporting_sentence(tmp_path: Path) -> None:
    verifier = CitationVerifier(
        ToolCallLogger(tmp_path),
        EvidenceStore(tmp_path),
        fulltext_evidence=[
            {
                "text": "Retrieval augmented generation improves factual grounding for knowledge intensive natural language processing tasks.",
                "source_location": "input_pdf page 2, paragraph 3",
            }
        ],
    )
    claim = {
        "claim_id": "C009",
        "claim_text": "Prior work reports that retrieval augmented generation improves factual grounding.",
        "cited_work": {
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "authors": ["Patrick Lewis"],
            "year": 2020,
            "doi": "10.0000/example",
        },
    }
    candidate = {
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "authors": ["Patrick Lewis"],
        "year": 2020,
        "doi": "10.0000/example",
        "url": "https://example.test",
        "abstract": "",
        "snippet": "",
        "source_agreement_count": 2,
        "source_agreement_summary": "crossref, openalex",
    }
    row = verifier._classify_claim_support(claim, claim["cited_work"], candidate, "crossref_doi", "")
    assert row["color_label"] == "Yellow"
    assert row["error_type"] == "supporting_sentence_missing"
    assert row["supporting_sentence"]
    assert row["supporting_location"] == "input_pdf page 2, paragraph 3"
    assert row["support_source_type"] == "input_pdf_fulltext"


def test_version_year_mismatch_is_yellow(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C010",
        "claim_text": "Prior work reports that retrieval augmented generation improves factual grounding.",
        "cited_work": {
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "authors": ["Patrick Lewis"],
            "year": 2021,
            "doi": "10.0000/example",
        },
    }
    candidate = {
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "authors": ["Patrick Lewis"],
        "year": 2020,
        "doi": "10.0000/example",
        "url": "https://arxiv.org/abs/2005.11401",
        "abstract": "Retrieval augmented generation improves factual grounding for knowledge intensive tasks.",
        "source_agreement_count": 2,
        "version_match_status": "version_year_mismatch",
    }
    row = verifier._classify_claim_support(claim, claim["cited_work"], candidate, "crossref_doi", "")
    assert row["color_label"] == "Yellow"
    assert row["error_type"] == "version_year_mismatch"


def test_claim_too_strong_stays_yellow(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C011",
        "claim_text": "Prior work reports that citation verification fully solves hallucination in scientific writing.",
        "cited_work": {"title": "Citation Verification for Scientific Writing", "authors": ["A. Researcher"], "year": 2024},
    }
    candidate = {
        "title": "Citation Verification for Scientific Writing",
        "authors": ["A. Researcher"],
        "year": 2024,
        "abstract": "This paper studies citation verification and scientific writing workflows.",
        "source_agreement_count": 2,
    }
    row = verifier._classify_claim_support(claim, claim["cited_work"], candidate, "crossref_title", "")
    assert row["color_label"] == "Yellow"
    assert row["error_type"] == "claim_too_strong"
    assert row["missing_critical_terms"]
    assert int(row["risk_penalty"]) > 0


def test_exact_arxiv_id_can_be_authoritative_green_with_support_sentence(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C011A",
        "claim_text": "Prior work reports that CLIP learns transferable visual models from natural language supervision.",
        "cited_work": {
            "title": "Learning Transferable Visual Models From Natural Language Supervision",
            "authors": ["Alec Radford"],
            "year": 2021,
            "url": "https://arxiv.org/abs/2103.00020",
        },
    }
    candidate = {
        "title": "Learning Transferable Visual Models From Natural Language Supervision",
        "authors": ["Alec Radford"],
        "year": 2021,
        "doi": "",
        "url": "https://arxiv.org/abs/2103.00020",
        "abstract": (
            "CLIP learns transferable visual models from natural language supervision. "
            "The method transfers to downstream visual recognition tasks in zero-shot settings."
        ),
        "source_agreement_count": 1,
        "source_agreement_summary": "arxiv",
        "version_match_status": "preprint_or_journal_version",
    }
    row = verifier._classify_claim_support(claim, claim["cited_work"], candidate, "arxiv_id", "")
    assert row["color_label"] == "Green"
    assert row["green_gate_passed"] is True
    assert row["error_type"] == ""


def test_exact_arxiv_id_does_not_override_weak_support(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C011B",
        "claim_text": "Prior work proves that CLIP fully solves multimodal reasoning.",
        "cited_work": {
            "title": "Learning Transferable Visual Models From Natural Language Supervision",
            "authors": ["Alec Radford"],
            "year": 2021,
            "url": "https://arxiv.org/abs/2103.00020",
        },
    }
    candidate = {
        "title": "Learning Transferable Visual Models From Natural Language Supervision",
        "authors": ["Alec Radford"],
        "year": 2021,
        "url": "https://arxiv.org/abs/2103.00020",
        "abstract": "CLIP studies transferable visual models from natural language supervision.",
        "source_agreement_count": 1,
    }
    row = verifier._classify_claim_support(claim, claim["cited_work"], candidate, "arxiv_id", "")
    assert row["color_label"] == "Yellow"
    assert row["error_type"] == "claim_too_strong"


def test_support_check_uses_richest_provider_abstract_for_same_work(tmp_path: Path) -> None:
    verifier = CitationVerifier(
        ToolCallLogger(tmp_path),
        EvidenceStore(tmp_path),
        providers=["crossref", "semantic_scholar"],
    )

    def fake_lookup_provider(provider: str, query_type: str, query: str, claim_id: str):
        abstract = ""
        if provider == "semantic_scholar":
            abstract = (
                "FinRL is a deep reinforcement learning library for automated stock trading in quantitative finance. "
                "The library provides reproducible tutorials, trading environments, and benchmark agents."
            )
        return verifier._provider_row(
            claim_id=claim_id,
            provider=provider,
            query_type=query_type,
            query=query,
            status="success",
            error="",
            lookup_source=f"{provider}_{query_type}",
            candidate={
                "title": "FinRL: A Deep Reinforcement Learning Library for Automated Stock Trading in Quantitative Finance",
                "authors": ["Xiao-Yang Liu"],
                "year": 2020,
                "doi": "10.2139/ssrn.3737257",
                "url": "https://doi.org/10.2139/ssrn.3737257",
                "abstract": abstract,
                "source_provider": provider,
                "lookup_source": f"{provider}_{query_type}",
            },
        )

    verifier._lookup_provider = fake_lookup_provider  # type: ignore[method-assign]
    rows = verifier.verify(
        [
            {
                "claim_id": "C011C",
                "claim_text": "Prior work reports that FinRL is a deep reinforcement learning library for automated stock trading.",
                "cited_work": {
                    "title": "FinRL: A Deep Reinforcement Learning Library for Automated Stock Trading in Quantitative Finance",
                    "authors": ["Xiao-Yang Liu"],
                    "year": 2020,
                    "doi": "10.2139/ssrn.3737257",
                },
            }
        ]
    )
    assert rows[0]["color_label"] == "Green"
    assert rows[0]["supporting_sentence"]
    assert "semantic_scholar" in rows[0]["supporting_location"]


def test_keyword_overlap_without_minimum_similarity_stays_yellow(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C011D",
        "claim_text": "Prior work reports radiologist-level pneumonia detection on chest X-rays.",
        "cited_work": {
            "title": "Pneumonia Detection from Chest X-Rays",
            "authors": ["A. Researcher"],
            "year": 2024,
        },
    }
    candidate = {
        "title": "Pneumonia Detection from Chest X-Rays",
        "authors": ["A. Researcher"],
        "year": 2024,
        "abstract": (
            "In a long survey of hospital information systems, data collection protocols, annotation policies, "
            "image storage pipelines, acquisition devices, clinical workflow integration, privacy constraints, "
            "preprocessing choices, benchmark construction, sampling bias, and reporting practices, the authors "
            "briefly mention chest X-rays, pneumonia, machine learning, and x-rays as example keywords without "
            "evaluating radiologist-level detection."
        ),
        "source_agreement_count": 2,
    }
    row = verifier._classify_claim_support(claim, claim["cited_work"], candidate, "fixture", "")
    assert row["color_label"] == "Yellow"
    assert row["support_status"] == "partial_or_uncertain"


def test_beyond_pl_extrapolation_is_yellow(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C013",
        "claim_text": "This result suggests MEHA can extend bilevel optimization beyond PL conditions.",
        "cited_work": {"title": "Bilevel Optimization Under PL Conditions", "authors": ["A. Researcher"], "year": 2024},
    }
    candidate = {
        "title": "Bilevel Optimization Under PL Conditions",
        "authors": ["A. Researcher"],
        "year": 2024,
        "abstract": "We study bilevel optimization under the Polyak-Lojasiewicz PL condition and prove convergence.",
        "source_agreement_count": 2,
    }
    row = verifier._classify_claim_support(claim, claim["cited_work"], candidate, "fixture", "")
    assert row["color_label"] == "Yellow"
    assert row["error_type"] == "critical_terms_missing"
    assert "beyond PL" in row["missing_critical_terms"]
    assert row["green_gate_passed"] is False


def test_multilevel_extension_from_bilevel_source_is_yellow(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C014",
        "claim_text": "The cited bilevel method can be used as a recursive multi-level optimization algorithm.",
        "cited_work": {"title": "A Bilevel Optimization Method", "authors": ["A. Researcher"], "year": 2024},
    }
    candidate = {
        "title": "A Bilevel Optimization Method",
        "authors": ["A. Researcher"],
        "year": 2024,
        "abstract": "This paper proposes an algorithm for bilevel optimization and proves convergence for the bilevel problem.",
        "source_agreement_count": 2,
    }
    row = verifier._classify_claim_support(claim, claim["cited_work"], candidate, "fixture", "")
    assert row["color_label"] == "Yellow"
    assert row["error_type"] == "critical_terms_missing"
    assert "multi-level" in row["missing_critical_terms"]


def test_constrained_complexity_mismatch_is_red(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C015",
        "claim_text": "The cited work gives O(epsilon^-4) complexity for constrained bilevel optimization.",
        "cited_work": {"title": "Bilevel Optimization Complexity", "authors": ["A. Researcher"], "year": 2024},
    }
    candidate = {
        "title": "Bilevel Optimization Complexity",
        "authors": ["A. Researcher"],
        "year": 2024,
        "abstract": (
            "The method achieves O(epsilon^-4) sample complexity for unconstrained bilevel problems. "
            "For constrained bilevel problems, the complexity is O(epsilon^-7)."
        ),
        "source_agreement_count": 2,
    }
    row = verifier._classify_claim_support(claim, claim["cited_work"], candidate, "fixture", "")
    assert row["color_label"] == "Red"
    assert row["error_type"] == "numeric_or_condition_contradiction"
    assert row["contradiction_type"] == "numeric_or_condition_contradiction"
    assert int(row["risk_penalty"]) >= 4


def test_unicode_epsilon_complexity_is_normalized_for_red_line(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    epsilon = chr(0x03B5)
    minus = chr(0x2212)
    claim = {
        "claim_id": "C015B",
        "claim_text": f"The cited work gives O({epsilon}^{minus}4) complexity for constrained bilevel optimization.",
        "cited_work": {"title": "Bilevel Optimization Complexity", "authors": ["A. Researcher"], "year": 2024},
    }
    candidate = {
        "title": "Bilevel Optimization Complexity",
        "authors": ["A. Researcher"],
        "year": 2024,
        "abstract": (
            "The method achieves O(epsilon^-4) sample complexity for unconstrained bilevel problems. "
            "For constrained bilevel problems, the complexity is O(epsilon^-7)."
        ),
        "source_agreement_count": 2,
    }
    row = verifier._classify_claim_support(claim, claim["cited_work"], candidate, "fixture", "")
    assert row["color_label"] == "Red"
    assert row["error_type"] == "numeric_or_condition_contradiction"


def test_new_risk_fields_present_on_green(tmp_path: Path) -> None:
    verifier = make_verifier(tmp_path)
    claim = {
        "claim_id": "C016",
        "claim_text": "Prior work reports that retrieval augmented generation improves factual grounding.",
        "cited_work": {
            "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            "authors": ["Patrick Lewis"],
            "year": 2020,
            "doi": "10.0000/example",
        },
    }
    candidate = {
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "authors": ["Patrick Lewis"],
        "year": 2020,
        "doi": "10.0000/example",
        "abstract": "Retrieval augmented generation improves factual grounding for knowledge intensive tasks.",
        "source_agreement_count": 2,
    }
    row = verifier._classify_claim_support(claim, claim["cited_work"], candidate, "fixture", "")
    for field in [
        "claim_strength_level",
        "critical_terms",
        "covered_critical_terms",
        "missing_critical_terms",
        "contradiction_type",
        "risk_penalty",
        "score_cap_reason",
    ]:
        assert field in row
    assert row["color_label"] == "Green"


def test_verifier_writes_provider_version_and_paragraph_artifacts(tmp_path: Path) -> None:
    verifier = CitationVerifier(ToolCallLogger(tmp_path), EvidenceStore(tmp_path), run_dir=tmp_path)

    def fake_lookup_provider(provider: str, query_type: str, query: str, claim_id: str):
        return verifier._provider_row(
            claim_id=claim_id,
            provider=provider,
            query_type=query_type,
            query=query,
            status="success",
            error="",
            lookup_source=f"{provider}_{query_type}",
            candidate={
                "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
                "authors": ["Patrick Lewis"],
                "year": 2020,
                "doi": "10.0000/example" if provider != "arxiv" else "",
                "url": "https://example.test",
                "abstract": "Retrieval augmented generation improves factual grounding for knowledge intensive tasks.",
                "source_provider": provider,
                "lookup_source": f"{provider}_{query_type}",
            },
        )

    verifier._lookup_provider = fake_lookup_provider  # type: ignore[method-assign]
    rows = verifier.verify(
        [
            {
                "claim_id": "C012",
                "claim_text": "Prior work reports that retrieval augmented generation improves factual grounding.",
                "cited_work": {
                    "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
                    "authors": ["Patrick Lewis"],
                    "year": 2020,
                    "doi": "10.0000/example",
                },
            }
        ]
    )
    assert rows[0]["color_label"] == "Green"
    assert (tmp_path / "provider_verification.jsonl").exists()
    assert (tmp_path / "version_resolution.jsonl").exists()
    assert (tmp_path / "paragraph_support_matches.jsonl").exists()
    provider_rows = [
        json.loads(line)
        for line in (tmp_path / "provider_verification.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert {row["provider"] for row in provider_rows} >= {"crossref", "openalex", "semantic_scholar", "arxiv"}
