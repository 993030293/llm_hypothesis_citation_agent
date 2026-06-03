from __future__ import annotations

from agent.verifier_params import load_verifier_params
from scripts.evaluate_verifier_params import evaluate, predict_color


def test_predict_year_mismatch_as_yellow() -> None:
    params = load_verifier_params()
    color, reason = predict_color(
        {
            "exists_status": "exists",
            "metadata_match_status": "partial_match",
            "support_status": "supports",
            "error_type": "year_mismatch_requires_review",
            "year_match": "False",
            "support_score": "1.0",
            "source_agreement_count": "2",
            "support_source_type": "retrieved_abstract",
            "supporting_sentence_present": "True",
            "verification_method": "crossref_doi",
            "doi": "10.0000/example",
            "version_match_status": "same_record",
            "input_extraction_risk": "ready",
        },
        params,
    )
    assert color == "Yellow"
    assert reason == "year_mismatch_requires_review"


def test_predict_risky_input_caps_green_to_yellow() -> None:
    params = load_verifier_params()
    color, reason = predict_color(
        {
            "exists_status": "exists",
            "metadata_match_status": "match",
            "support_status": "supports",
            "error_type": "",
            "year_match": "True",
            "support_score": "1.0",
            "source_agreement_count": "2",
            "support_source_type": "retrieved_abstract",
            "supporting_sentence_present": "True",
            "verification_method": "crossref_doi",
            "doi": "10.0000/example",
            "version_match_status": "same_record",
            "input_extraction_risk": "risky",
        },
        params,
    )
    assert color == "Yellow"
    assert reason == "insufficient_green_gate"


def test_manual_seed_labels_evaluate_without_false_green() -> None:
    params = load_verifier_params()
    rows = [
        {
            "human_color": "Green",
            "exists_status": "exists",
            "metadata_match_status": "match",
            "support_status": "supports",
            "error_type": "",
            "year_match": "True",
            "support_score": "1.0",
            "source_agreement_count": "2",
            "support_source_type": "retrieved_abstract",
            "supporting_sentence_present": "True",
            "verification_method": "crossref_doi",
            "doi": "10.0000/example",
            "version_match_status": "same_record",
            "input_extraction_risk": "ready",
        },
        {
            "human_color": "Red",
            "exists_status": "not_found",
            "metadata_match_status": "unknown",
            "support_status": "not_supported",
            "error_type": "invalid_doi",
            "year_match": "False",
            "support_score": "0.0",
            "source_agreement_count": "0",
            "support_source_type": "",
            "supporting_sentence_present": "False",
            "verification_method": "doi_format_check",
            "doi": "bad-doi",
            "version_match_status": "unknown",
            "input_extraction_risk": "ready",
        },
    ]
    result = evaluate(rows, params)
    assert result["accuracy"] == 1.0
    assert result["false_green_count"] == 0
