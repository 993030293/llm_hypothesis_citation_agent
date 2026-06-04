from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from scripts import run_multi_reviewer as reviewer


def write_audit_artifacts(audit_dir: Path) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    with (audit_dir / "citation_verification.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "claim_id",
                "hypothesis_id",
                "claim_text",
                "cited_title",
                "doi",
                "color_label",
                "error_type",
                "support_status",
                "supporting_sentence",
                "reason",
                "evidence_id",
                "verification_method",
                "green_gate_passed",
                "manual_review_required",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "claim_id": "C001",
                "hypothesis_id": "H001",
                "claim_text": "RAG can improve factual grounding for knowledge-intensive tasks.",
                "cited_title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
                "doi": "",
                "color_label": "Green",
                "error_type": "none",
                "support_status": "direct",
                "supporting_sentence": "RAG obtains state-of-the-art results on knowledge-intensive NLP tasks.",
                "reason": "Metadata and support sentence match.",
                "evidence_id": "E001",
                "verification_method": "crossref+openalex",
                "green_gate_passed": "true",
                "manual_review_required": "false",
            }
        )
    (audit_dir / "evidence_chain.csv").write_text(
        "claim_id,support_category,verification_evidence_id,tool_call_ids,manual_review_required\n"
        "C001,directly_supported,E001,T001,false\n",
        encoding="utf-8",
    )
    (audit_dir / "tool_calls.jsonl").write_text(
        json.dumps({"tool_call_id": "T001", "tool_name": "crossref_lookup", "status": "success"}) + "\n",
        encoding="utf-8",
    )
    (audit_dir / "provider_verification.jsonl").write_text(
        json.dumps({"provider": "openalex", "status": "exists"}) + "\n",
        encoding="utf-8",
    )
    (audit_dir / "input_claims.json").write_text(
        json.dumps({"hypotheses": [{"hypothesis_id": "H001"}]}),
        encoding="utf-8",
    )


def write_custom_audit_artifacts(audit_dir: Path, rows: list[dict[str, str]]) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row} | {"claim_id", "color_label", "error_type"})
    with (audit_dir / "citation_verification.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    chain_lines = ["claim_id,support_category,verification_evidence_id,tool_call_ids,manual_review_required"]
    for row in rows:
        chain_lines.append(f"{row.get('claim_id')},reasonable_inference_or_uncertain,{row.get('evidence_id','E001')},T001,true")
    (audit_dir / "evidence_chain.csv").write_text("\n".join(chain_lines) + "\n", encoding="utf-8")
    (audit_dir / "tool_calls.jsonl").write_text(
        json.dumps({"tool_call_id": "T001", "tool_name": "fixture_lookup", "status": "success"}) + "\n",
        encoding="utf-8",
    )
    (audit_dir / "provider_verification.jsonl").write_text(
        json.dumps({"provider": "fixture", "status": "exists"}) + "\n",
        encoding="utf-8",
    )
    (audit_dir / "input_claims.json").write_text(
        json.dumps({"hypotheses": [{"hypothesis_id": "H001"}]}),
        encoding="utf-8",
    )


def make_args(tmp_path: Path, audit_dir: Path, mode: str = "auto") -> argparse.Namespace:
    return argparse.Namespace(
        audit_run_dir=str(audit_dir),
        quest_root=str(tmp_path / "quest"),
        out_dir=str(tmp_path / "multi_review"),
        review_mode=mode,
        deepseek_base_url="https://api.deepseek.com/v1",
        temperature=0.2,
        reviewer_timeout_seconds=3,
    )


def test_model_map_uses_deepseek_v4_pro() -> None:
    models = {config.reviewer_id: config.model for config in reviewer.REVIEWERS}
    assert "deepseek-v4-pro" in models.values()
    assert models["R2"] == "deepseek-v4-pro"
    assert reviewer.META_MODEL == "deepseek-v4-pro"


def test_auto_mode_without_keys_uses_deterministic_fallback(tmp_path: Path, monkeypatch) -> None:
    audit_dir = tmp_path / "audit"
    write_audit_artifacts(audit_dir)
    for config in reviewer.REVIEWERS:
        monkeypatch.delenv(config.env_var, raising=False)
    monkeypatch.delenv(reviewer.META_ENV_VAR, raising=False)

    status = reviewer.run_multi_review(make_args(tmp_path, audit_dir, mode="auto"))

    assert [item["review_source"] for item in status["reviews"]] == ["deterministic"] * 4
    assert status["meta"]["review_source"] == "deterministic"
    assert (tmp_path / "multi_review" / "reviewer_scores.jsonl").exists()
    log_text = (tmp_path / "multi_review" / "multi_reviewer_tool_calls.jsonl").read_text(encoding="utf-8")
    assert "key_configured" in log_text
    assert "sk-" not in log_text


def test_deepseek_mode_uses_model_json_when_client_succeeds(tmp_path: Path, monkeypatch) -> None:
    audit_dir = tmp_path / "audit"
    write_audit_artifacts(audit_dir)
    for index, config in enumerate(reviewer.REVIEWERS, start=1):
        monkeypatch.setenv(config.env_var, "s" + f"k-test-secret-{index}")
    monkeypatch.setenv(reviewer.META_ENV_VAR, "s" + "k-test-secret-meta")

    def fake_call_deepseek_json(**kwargs):  # noqa: ANN003
        model = kwargs["model"]
        if model == reviewer.META_MODEL:
            return {
                "final_score_1_to_6": 5,
                "decision": "accept_for_demo",
                "main_reason": "Panel agrees that the case is demo-ready.",
                "must_fix_before_demo": [],
                "citation_risk_summary": {"green": 1, "yellow": 0, "red": 0},
                "reviewer_agreement": "high",
            }
        return {
            "reviewer_id": "R1",
            "role": "novelty_reviewer",
            "score_1_to_6": 5,
            "strengths": ["Good evidence-aware idea."],
            "weaknesses": ["Needs a concrete experiment."],
            "required_revision": ["Add experiment design."],
            "evidence_ids_used": ["E001"],
            "tool_calls_used": ["crossref+openalex"],
            "confidence": "high",
        }

    monkeypatch.setattr(reviewer, "call_deepseek_json", fake_call_deepseek_json)

    status = reviewer.run_multi_review(make_args(tmp_path, audit_dir, mode="deepseek"))

    assert [item["review_source"] for item in status["reviews"]] == ["deepseek"] * 4
    assert status["reviews"][1]["model"] == "deepseek-v4-pro"
    assert status["meta"]["review_source"] == "deepseek"
    assert status["meta"]["model"] == "deepseek-v4-pro"
    log_text = (tmp_path / "multi_review" / "multi_reviewer_tool_calls.jsonl").read_text(encoding="utf-8")
    assert "sk-test-secret" not in log_text


def test_red_claim_caps_meta_score_and_rejects(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit_red"
    write_custom_audit_artifacts(
        audit_dir,
        [
            {
                "claim_id": "C001",
                "color_label": "Red",
                "error_type": "numeric_or_condition_contradiction",
                "contradiction_type": "numeric_or_condition_contradiction",
                "risk_penalty": "4",
                "evidence_id": "E001",
                "verification_method": "fixture",
            }
        ],
    )
    status = reviewer.run_multi_review(make_args(tmp_path, audit_dir, mode="deterministic"))
    assert status["meta"]["deterministic_score_cap"] == 2
    assert status["meta"]["final_score_1_to_6"] <= 2
    assert status["meta"]["decision"] == "reject_or_boundary_case"
    assert status["meta"]["red_line_triggered"] is True


def test_yellow_majority_caps_meta_score(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit_yellow"
    write_custom_audit_artifacts(
        audit_dir,
        [
            {"claim_id": "C001", "color_label": "Green", "error_type": "", "risk_penalty": "0", "evidence_id": "E001"},
            {
                "claim_id": "C002",
                "color_label": "Yellow",
                "error_type": "critical_terms_missing",
                "missing_critical_terms": "beyond PL",
                "risk_penalty": "1",
                "evidence_id": "E002",
            },
            {
                "claim_id": "C003",
                "color_label": "Yellow",
                "error_type": "supporting_sentence_missing",
                "risk_penalty": "1",
                "evidence_id": "E003",
            },
        ],
    )
    status = reviewer.run_multi_review(make_args(tmp_path, audit_dir, mode="deterministic"))
    assert status["meta"]["deterministic_score_cap"] == 3
    assert status["meta"]["final_score_1_to_6"] <= 3
    assert status["meta"]["decision"] == "revise_before_demo"


def test_deepseek_meta_cannot_exceed_deterministic_cap(tmp_path: Path, monkeypatch) -> None:
    audit_dir = tmp_path / "audit_cap"
    write_custom_audit_artifacts(
        audit_dir,
        [
            {"claim_id": "C001", "color_label": "Green", "error_type": "", "risk_penalty": "0", "evidence_id": "E001"},
            {
                "claim_id": "C002",
                "color_label": "Yellow",
                "error_type": "critical_terms_missing",
                "missing_critical_terms": "multi-level",
                "risk_penalty": "1",
                "evidence_id": "E002",
            },
            {
                "claim_id": "C003",
                "color_label": "Yellow",
                "error_type": "claim_too_strong",
                "missing_critical_terms": "fully solves",
                "risk_penalty": "1",
                "evidence_id": "E003",
            },
        ],
    )
    for index, config in enumerate(reviewer.REVIEWERS, start=1):
        monkeypatch.setenv(config.env_var, "s" + f"k-test-secret-{index}")
    monkeypatch.setenv(reviewer.META_ENV_VAR, "s" + "k-test-secret-meta")

    def fake_call_deepseek_json(**kwargs):  # noqa: ANN003
        if kwargs["model"] == reviewer.META_MODEL:
            return {
                "final_score_1_to_6": 5,
                "decision": "accept_for_demo",
                "main_reason": "Model wants to accept.",
                "must_fix_before_demo": [],
                "citation_risk_summary": {"green": 1, "yellow": 2, "red": 0},
                "reviewer_agreement": "high",
            }
        return {
            "reviewer_id": "R1",
            "role": "novelty_reviewer",
            "score_1_to_6": 5,
            "strengths": ["Good idea."],
            "weaknesses": ["Needs checks."],
            "required_revision": ["Fix citations."],
            "evidence_ids_used": ["E001"],
            "tool_calls_used": ["fixture"],
            "confidence": "high",
        }

    monkeypatch.setattr(reviewer, "call_deepseek_json", fake_call_deepseek_json)
    status = reviewer.run_multi_review(make_args(tmp_path, audit_dir, mode="deepseek"))
    assert status["meta"]["review_source"] == "deepseek"
    assert status["meta"]["deterministic_score_cap"] == 3
    assert status["meta"]["final_score_1_to_6"] == 3
    assert status["meta"]["decision"] == "revise_before_demo"


def test_secret_redaction_handles_raw_key_text() -> None:
    fake_key = "s" + "k-" + "abcdefghijklmnopqrstuvwxyz123456"
    redacted = reviewer.safe_for_logs({"value": f"prefix {fake_key} suffix"})
    assert redacted["value"] == "prefix sk-***REDACTED*** suffix"
