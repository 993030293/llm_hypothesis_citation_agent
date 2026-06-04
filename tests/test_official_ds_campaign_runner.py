from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from scripts import deepscientist_15x_campaign as campaign
from scripts import run_official_ds_case as ds_case


def test_deepscientist_hypothesis_citation_schema_validates(tmp_path: Path) -> None:
    claims_path = tmp_path / "citation_audit_claims.json"
    claims_path.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "H1",
                        "title": "LLM engagement hypothesis",
                        "hypothesis": "Offering LLM access can change student engagement.",
                        "supporting_evidence": [{"detail": "The input paper reports engagement changes."}],
                        "citations": [{"id": "rag2020", "arxiv_id": "2005.11401", "role": "related_work"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    ok, reason = ds_case.validate_claims_file(claims_path)
    assert ok, reason


def test_project_skill_installs_short_and_compat_names(tmp_path: Path) -> None:
    quest_root = tmp_path / "quest"
    status: dict[str, object] = {}

    ds_case.install_project_skill_for_quest(
        ds_skill="citation-hypothesis-claims",
        quest_root=quest_root,
        status=status,
    )

    short_path = quest_root / ".codex" / "skills" / "citation-hypothesis-claims" / "SKILL.md"
    compat_path = quest_root / ".codex" / "skills" / "deepscientist-citation-hypothesis-claims" / "SKILL.md"
    assert short_path.exists()
    assert compat_path.exists()
    assert status["project_skill_install_status"] == "installed_for_quest"
    assert str(short_path.parent) in status["project_skill_targets"]
    assert str(compat_path.parent) in status["project_skill_targets"]


def test_claim_generation_prompt_points_to_skill_file_and_fallback_read(tmp_path: Path) -> None:
    quest_root = tmp_path / "quest"

    prompt = ds_case.build_claim_generation_prompt(
        case_id="case001",
        pdf_path_or_url="https://example.test/paper.pdf",
        quest_root=quest_root,
        run_id="run001",
        ds_skill="citation-hypothesis-claims",
    )

    assert 'Skill("citation-hypothesis-claims")' in prompt
    assert ".codex" in prompt
    assert "skills" in prompt
    assert "citation-hypothesis-claims" in prompt
    assert "Unknown skill" in prompt
    assert "Read" in prompt
    assert "citation_audit_claims.json" in prompt


def test_resolve_claims_path_skips_deepscientist_runtime_cache(tmp_path: Path) -> None:
    quest_root = tmp_path / "quest"
    volatile = quest_root / ".ds" / "claude-home" / "projects" / "case" / "tool-results" / "pdf-temp"
    volatile.mkdir(parents=True)
    (volatile / "citation_audit_claims.json").write_text("{bad json", encoding="utf-8")
    stable = quest_root / "artifacts"
    stable.mkdir(parents=True)
    stable_claims = stable / "citation_audit_claims.json"
    stable_claims.write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "claim_id": "C001",
                        "claim_text": "A stable claim.",
                        "cited_work": {"title": "A stable paper", "authors": [], "year": 2024},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert ds_case.resolve_claims_path(quest_root) == stable_claims


def test_resolve_claims_path_ignores_disappearing_directories(tmp_path: Path, monkeypatch) -> None:
    quest_root = tmp_path / "quest"
    quest_root.mkdir()

    def broken_walk(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise FileNotFoundError("transient DeepScientist tool result disappeared")

    monkeypatch.setattr(ds_case.os, "walk", broken_walk)

    assert ds_case.resolve_claims_path(quest_root) is None


def test_official_ds_case_success_writes_report_and_avoids_secret_logs(tmp_path: Path, monkeypatch) -> None:
    quest_root = tmp_path / "quest"
    output_root = tmp_path / "outputs"

    def fake_run_subprocess(cmd: list[str], *, timeout_seconds: int):  # noqa: ANN001
        if cmd[:2] == ["ds", "--status"]:
            return {"returncode": 0, "stdout": json.dumps({"healthy": True}), "stderr": ""}
        if cmd[:2] == ["ds", "new"]:
            quest_root.mkdir(parents=True, exist_ok=True)
            return {"returncode": 0, "stdout": "created", "stderr": ""}
        if "audit_deepscientist_output.py" in " ".join(cmd):
            run_dir = Path(cmd[cmd.index("--run-dir") + 1])
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "citation_verification.csv").write_text("claim_id,color_label\nC001,Green\n", encoding="utf-8")
            for name in (
                "evidence_chain.csv",
                "evidence_chain.md",
                "deepscientist_audit_summary.md",
                "tool_calls.jsonl",
                "evidence_items.jsonl",
            ):
                (run_dir / name).write_text("", encoding="utf-8")
            return {"returncode": 0, "stdout": "audit ok", "stderr": ""}
        return {"returncode": 0, "stdout": "", "stderr": ""}

    def fake_run_logged_until_claims(*args, **kwargs):  # noqa: ANN002, ANN003
        quest_root.mkdir(parents=True, exist_ok=True)
        (quest_root / "citation_audit_claims.json").write_text(
            json.dumps(
                {
                    "claims": [
                        {
                            "claim_id": "C001",
                            "claim_text": "Prior work reports that RAG improves factual grounding.",
                            "cited_work": {
                                "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
                                "authors": ["Patrick Lewis"],
                                "year": 2020,
                                "doi": "",
                            },
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return {"returncode": 0, "stdout": "claims written", "stderr": "", "stdout_tail": "claims written", "stderr_tail": ""}

    def fake_run_logged_with_progress(cmd: list[str], logs_dir: Path, label: str, *, timeout_seconds: int, **kwargs):  # noqa: ANN001
        result = fake_run_subprocess(cmd, timeout_seconds=timeout_seconds)
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / f"{label}_stdout.txt").write_text(result["stdout"], encoding="utf-8")
        (logs_dir / f"{label}_stderr.txt").write_text(result["stderr"], encoding="utf-8")
        return {**result, "stdout_tail": result["stdout"], "stderr_tail": result["stderr"]}

    monkeypatch.setattr(ds_case, "run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(ds_case, "run_logged_until_claims", fake_run_logged_until_claims)
    monkeypatch.setattr(ds_case, "run_logged_with_progress", fake_run_logged_with_progress)
    monkeypatch.setenv("DEEPSEEK_REVIEWER_1_API_KEY", "s" + "k-test-secret-that-must-not-be-logged")
    status = ds_case.run_case(
        argparse.Namespace(
            case_id="ai_rag_knowledge_nlp",
            pdf_path_or_url="https://arxiv.org/pdf/2005.11401",
            run_id="testrun",
            output_root=str(output_root),
            quest_id="test-quest",
            quest_root=str(quest_root),
            timeout_seconds=30,
            ds_attempts=2,
            ds_skill="citation-hypothesis-claims",
            reuse_quest=False,
            skip_ds_restart=False,
            disable_fallback_claims=True,
        )
    )

    case_dir = output_root / "testrun" / "cases" / "ai_rag_knowledge_nlp"
    assert status["final_status"] == "success"
    assert status["green"] == 1
    assert (case_dir / "final_case_report.md").exists()
    log_text = "\n".join(path.read_text(encoding="utf-8") for path in (case_dir / "logs").glob("*.txt"))
    assert "sk-test-secret" not in log_text


def test_run_logged_with_progress_emits_start_heartbeat_and_finish(tmp_path: Path, monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(ds_case, "emit_progress", messages.append)

    result = ds_case.run_logged_with_progress(
        [sys.executable, "-c", "import time; time.sleep(0.28)"],
        tmp_path,
        "slow_stage",
        timeout_seconds=2,
        stage="multi_reviewer",
        heartbeat_seconds=0.05,
    )

    assert result["returncode"] == 0
    assert messages[0] == "Starting multi_reviewer."
    assert sum(message.startswith("Still running multi_reviewer.") for message in messages) >= 2
    assert messages[-1] == "Finished multi_reviewer: success."


def test_run_logged_with_progress_reports_failed_finish(tmp_path: Path, monkeypatch) -> None:
    messages: list[str] = []
    monkeypatch.setattr(ds_case, "emit_progress", messages.append)

    result = ds_case.run_logged_with_progress(
        [sys.executable, "-c", "import sys; sys.exit(3)"],
        tmp_path,
        "failed_stage",
        timeout_seconds=2,
        stage="citation_audit",
        heartbeat_seconds=0.05,
    )

    assert result["returncode"] == 3
    assert messages[0] == "Starting citation_audit."
    assert messages[-1] == "Finished citation_audit: failed."


def test_official_ds_case_missing_claims_is_recorded(tmp_path: Path, monkeypatch) -> None:
    quest_root = tmp_path / "quest_missing"
    output_root = tmp_path / "outputs"

    def fake_run_subprocess(cmd: list[str], *, timeout_seconds: int):  # noqa: ANN001
        if cmd[:2] == ["ds", "--status"]:
            return {"returncode": 0, "stdout": json.dumps({"healthy": True}), "stderr": ""}
        if cmd[:2] == ["ds", "new"]:
            quest_root.mkdir(parents=True, exist_ok=True)
            return {"returncode": 0, "stdout": "created", "stderr": ""}
        return {"returncode": 0, "stdout": "", "stderr": ""}

    def fake_run_logged_until_claims(*args, **kwargs):  # noqa: ANN002, ANN003
        quest_root.mkdir(parents=True, exist_ok=True)
        return {"returncode": 0, "stdout": "no claims", "stderr": "", "stdout_tail": "no claims", "stderr_tail": ""}

    monkeypatch.setattr(ds_case, "run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(ds_case, "run_logged_until_claims", fake_run_logged_until_claims)
    status = ds_case.run_case(
        argparse.Namespace(
            case_id="missing_claims_case",
            pdf_path_or_url="https://example.test/paper.pdf",
            run_id="testrun",
            output_root=str(output_root),
            quest_id="missing-quest",
            quest_root=str(quest_root),
            timeout_seconds=30,
            ds_attempts=2,
            ds_skill="citation-hypothesis-claims",
            reuse_quest=False,
            skip_ds_restart=False,
        )
    )

    case_dir = output_root / "testrun" / "cases" / "missing_claims_case"
    assert status["final_status"] == "failed"
    assert status["failure_type"] == "quest_claims_missing"
    assert (case_dir / "final_case_report.md").exists()
    assert "quest_claims_missing" in (case_dir / "case_status.json").read_text(encoding="utf-8")


def test_official_ds_case_timeout_uses_fallback_claims(tmp_path: Path, monkeypatch) -> None:
    quest_root = tmp_path / "quest_timeout"
    output_root = tmp_path / "outputs"

    def fake_run_subprocess(cmd: list[str], *, timeout_seconds: int):  # noqa: ANN001
        if cmd[:2] == ["ds", "--status"]:
            return {"returncode": 0, "stdout": json.dumps({"healthy": True}), "stderr": ""}
        if cmd[:2] == ["ds", "new"]:
            quest_root.mkdir(parents=True, exist_ok=True)
            return {"returncode": 0, "stdout": "created", "stderr": ""}
        if "audit_deepscientist_output.py" in " ".join(cmd):
            run_dir = Path(cmd[cmd.index("--run-dir") + 1])
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "citation_verification.csv").write_text("claim_id,color_label\nC001,Yellow\n", encoding="utf-8")
            for name in (
                "evidence_chain.csv",
                "evidence_chain.md",
                "deepscientist_audit_summary.md",
                "tool_calls.jsonl",
                "evidence_items.jsonl",
            ):
                (run_dir / name).write_text("", encoding="utf-8")
            return {"returncode": 0, "stdout": "audit ok", "stderr": ""}
        return {"returncode": 0, "stdout": "", "stderr": ""}

    def fake_run_logged_until_claims(*args, **kwargs):  # noqa: ANN002, ANN003
        quest_root.mkdir(parents=True, exist_ok=True)
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": "Timed out after 30s",
            "stdout_tail": "",
            "stderr_tail": "Timed out after 30s",
        }

    def fake_generate_fallback_claims(**kwargs):  # noqa: ANN003
        root = kwargs["quest_root"]
        ds_dir = kwargs["ds_dir"]
        root.mkdir(parents=True, exist_ok=True)
        ds_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "claims": [
                {
                    "claim_id": "C001",
                    "claim_text": "Fallback claim generated from local tools.",
                    "cited_work": {"title": "A real fallback paper", "authors": [], "year": 2020, "doi": ""},
                }
            ]
        }
        path = ds_dir / "citation_audit_claims.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        kwargs["status"]["claims_json_status"] = "fallback_valid"
        kwargs["status"]["claims_source"] = "local_fallback_generator"
        kwargs["status"]["failure_type"] = "official_ds_claims_recovered_by_fallback"
        kwargs["status"]["failure_reason"] = "Recovered by test fallback."
        return path

    def fake_run_logged_with_progress(cmd: list[str], logs_dir: Path, label: str, *, timeout_seconds: int, **kwargs):  # noqa: ANN001
        result = fake_run_subprocess(cmd, timeout_seconds=timeout_seconds)
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / f"{label}_stdout.txt").write_text(result["stdout"], encoding="utf-8")
        (logs_dir / f"{label}_stderr.txt").write_text(result["stderr"], encoding="utf-8")
        return {**result, "stdout_tail": result["stdout"], "stderr_tail": result["stderr"]}

    monkeypatch.setattr(ds_case, "run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(ds_case, "run_logged_until_claims", fake_run_logged_until_claims)
    monkeypatch.setattr(ds_case, "generate_fallback_claims", fake_generate_fallback_claims)
    monkeypatch.setattr(ds_case, "run_logged_with_progress", fake_run_logged_with_progress)
    status = ds_case.run_case(
        argparse.Namespace(
            case_id="timeout_case",
            pdf_path_or_url="https://example.test/paper.pdf",
            run_id="testrun",
            output_root=str(output_root),
            quest_id="timeout-quest",
            quest_root=str(quest_root),
            timeout_seconds=30,
            ds_attempts=2,
            ds_skill="citation-hypothesis-claims",
            reuse_quest=False,
            skip_ds_restart=False,
            disable_fallback_claims=False,
        )
    )

    case_dir = output_root / "testrun" / "cases" / "timeout_case"
    assert status["final_status"] == "success"
    assert status["claims_json_status"] == "fallback_valid"
    assert status["yellow"] == 1
    assert (case_dir / "deepscientist" / "citation_audit_claims.json").exists()


def test_campaign_continues_after_case_failure(tmp_path: Path, monkeypatch) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {"case_id": "case_ok", "field": "AI", "pdf_url": "https://example.test/ok.pdf", "pdf_path": "ok.pdf"},
                    {
                        "case_id": "case_fail",
                        "field": "Finance",
                        "pdf_url": "https://example.test/fail.pdf",
                        "pdf_path": "fail.pdf",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    output_root = tmp_path / "campaigns"

    def fake_run_case_subprocess(case: dict, run_id: str, campaign_dir: Path, args):  # noqa: ANN001
        case_dir = campaign_dir / "cases" / case["case_id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        failed = case["case_id"] == "case_fail"
        status = {
            "case_id": case["case_id"],
            "pdf_path_or_url": case["pdf_url"],
            "final_status": "failed" if failed else "success",
            "quest_status": "created",
            "claims_json_status": "missing" if failed else "valid",
            "audit_status": "not_started" if failed else "success",
            "multi_review_status": "skipped_missing_script",
            "memory_status": "skipped_missing_script",
            "green": 0 if failed else 1,
            "yellow": 0,
            "red": 0,
            "failure_type": "quest_claims_missing" if failed else "",
            "failure_reason": "missing claims" if failed else "",
            "case_dir": str(case_dir),
            "quest_root": str(tmp_path / "quests" / case["case_id"]),
        }
        (case_dir / "case_status.json").write_text(json.dumps(status), encoding="utf-8")
        return {"returncode": 1 if failed else 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(campaign, "run_case_subprocess", fake_run_case_subprocess)
    monkeypatch.setattr(
        campaign,
        "CLIP_CASE",
        {"case_id": "clip_extra", "field": "AI", "pdf_url": "https://example.test/clip.pdf", "pdf_path": "clip.pdf"},
    )
    rc = campaign.main_with_args(
        argparse.Namespace(
            manifest=str(manifest),
            output_root=str(output_root),
            run_id="testrun",
            case_id=[],
            max_cases=2,
            timeout_seconds=30,
            ds_skill="citation-hypothesis-claims",
            reuse_quests=False,
            no_copy_submission=True,
        )
    )

    assert rc == 0
    campaign_dir = output_root / "testrun"
    rows = list(csv.DictReader((campaign_dir / "case_status.csv").open(encoding="utf-8")))
    assert [row["case_id"] for row in rows] == ["case_ok", "case_fail"]
    assert "quest_claims_missing" in (campaign_dir / "deficiency_log.md").read_text(encoding="utf-8")
