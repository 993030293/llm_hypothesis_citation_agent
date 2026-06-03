from __future__ import annotations

from agent.evidence_chain_tracer import build_evidence_chain_rows, support_category_from_color


def test_support_category_mapping() -> None:
    assert support_category_from_color("Green") == "directly_supported"
    assert support_category_from_color("Yellow") == "reasonable_inference_or_uncertain"
    assert support_category_from_color("Red") == "insufficient_or_unsupported"


def test_build_evidence_chain_links_claim_to_evidence_and_tools() -> None:
    hypothesis_payload = {
        "claims": [
            {
                "claim_id": "C001",
                "hypothesis_id": "H001",
                "claim_text": "Prior work reports that citation audits reduce unsupported claims.",
                "cited_work": {
                    "title": "Citation Audits for Scientific Agents",
                    "literature_id": "L001",
                    "evidence_id": "E002",
                },
            }
        ]
    }
    literature = [{"literature_id": "L001", "evidence_id": "E002"}]
    verification_rows = [
        {
            "claim_id": "C001",
            "color_label": "Green",
            "evidence_id": "E003",
            "reason": "Metadata and abstract support the claim.",
        }
    ]
    evidence_items = [
        {
            "evidence_id": "E002",
            "source": "openalex",
            "locator": "https://example.test/paper",
            "url": "https://example.test/paper",
            "tool_call_id": "T004",
        },
        {
            "evidence_id": "E003",
            "source": "crossref_title",
            "locator": "Citation Audits for Scientific Agents",
            "url": "https://doi.org/10.0000/example",
            "tool_call_id": "T006",
        },
    ]
    tool_calls = [{"tool_call_id": "T004"}, {"tool_call_id": "T006"}]

    rows = build_evidence_chain_rows(
        hypothesis_payload=hypothesis_payload,
        literature=literature,
        verification_rows=verification_rows,
        evidence_items=evidence_items,
        tool_calls=tool_calls,
    )

    assert len(rows) == 1
    assert rows[0]["source_evidence_ids"] == "E002"
    assert rows[0]["verification_evidence_id"] == "E003"
    assert rows[0]["tool_call_ids"] == "T004;T006"
    assert rows[0]["support_category"] == "directly_supported"
    assert rows[0]["manual_review_required"] is False
