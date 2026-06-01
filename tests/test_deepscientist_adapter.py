from __future__ import annotations

import json
from pathlib import Path

from agent.citation_verifier import CitationVerifier
from agent.deepscientist_adapter import DeepScientistCitationAuditModule


def test_deepscientist_adapter_writes_standalone_audit_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_verify(self, claims):  # noqa: ANN001
        return [
            {
                "claim_id": claims[0]["claim_id"],
                "claim_text": claims[0]["claim_text"],
                "cited_title": claims[0]["cited_work"]["title"],
                "cited_authors": "; ".join(claims[0]["cited_work"]["authors"]),
                "cited_year": claims[0]["cited_work"]["year"],
                "doi": claims[0]["cited_work"]["doi"],
                "retrieval_source": "fixture",
                "exists_status": "exists",
                "metadata_match_status": "match",
                "support_status": "supports",
                "color_label": "Green",
                "reason": "Fixture row for adapter contract.",
                "evidence_id": "E001",
                "url": "https://example.test",
                "title_similarity": 1.0,
                "author_match_score": 1.0,
                "year_match": True,
                "support_score": 0.8,
                "matched_evidence_text": "Fixture evidence.",
                "verification_method": "fixture",
            }
        ]

    monkeypatch.setattr(CitationVerifier, "verify", fake_verify)

    module = DeepScientistCitationAuditModule(output_root=tmp_path)
    result = module.audit_claims(
        [
            {
                "claim_id": "C001",
                "hypothesis_id": "H001",
                "claim_text": "Prior work reports that citation audits reduce unsupported claims.",
                "cited_work": {
                    "title": "Citation Audits for Scientific Agents",
                    "authors": ["A. Researcher"],
                    "year": 2026,
                    "doi": "10.0000/example",
                },
            }
        ],
        run_dir=tmp_path / "audit",
    )

    run_dir = Path(result["run_dir"])
    assert result["label_counts"] == {"Green": 1, "Yellow": 0, "Red": 0}
    assert (run_dir / "deepscientist_module_manifest.json").exists()
    assert (run_dir / "input_claims.json").exists()
    assert (run_dir / "citation_verification.csv").exists()
    assert (run_dir / "evidence_chain.csv").exists()
    assert (run_dir / "evidence_chain.md").exists()
    assert (run_dir / "deepscientist_audit_summary.md").exists()
    assert (run_dir / "tool_calls.jsonl").exists()
    assert (run_dir / "evidence_items.jsonl").exists()

    manifest = json.loads((run_dir / "deepscientist_module_manifest.json").read_text(encoding="utf-8"))
    assert manifest["agent_style"] == "DeepScientist"
    assert manifest["insertion_point"] == "after_hypothesis_generation_before_final_report"


def test_deepscientist_adapter_loads_generated_claims_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(CitationVerifier, "verify", lambda self, claims: [])
    claims_path = tmp_path / "generated_claims.json"
    claims_path.write_text(
        json.dumps(
            {
                "hypotheses": [{"hypothesis_id": "H001"}],
                "claims": [
                    {
                        "claim_id": "C001",
                        "claim_text": "A claim to audit.",
                        "cited_work": {"title": "A Paper", "authors": [], "year": 2025, "doi": ""},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    module = DeepScientistCitationAuditModule(output_root=tmp_path)
    result = module.audit_claims_file(claims_path, run_dir=tmp_path / "file_audit")

    assert Path(result["run_dir"], "source_hypothesis_payload.json").exists()
    assert Path(result["run_dir"], "citation_verification.csv").exists()
    assert Path(result["run_dir"], "evidence_chain.csv").exists()
