#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.citation_claims_generator import CitationAuditClaimsGenerator
from agent.deepscientist_claims_normalizer import normalize_deepscientist_claims_payload
from agent.utils import clean_text, configure_utf8_stdio, safe_filename, timestamp_id, write_json


CLAIM_FILE_NAMES = (
    "citation_audit_claims.json",
    "generated_claims.json",
    "deepscientist_claims.json",
    "claims.json",
)
VOLATILE_QUEST_DIR_NAMES = {
    ".ds",
    ".git",
    ".claude",
    ".codex",
    ".kimi",
    ".opencode",
    "__pycache__",
    "node_modules",
    "tool-results",
}

AUDIT_ARTIFACTS = (
    "citation_verification.csv",
    "evidence_chain.csv",
    "evidence_chain.md",
    "deepscientist_audit_summary.md",
    "tool_calls.jsonl",
    "evidence_items.jsonl",
)
DEFAULT_HEARTBEAT_SECONDS = 60.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one official DeepScientist citation-audit case.")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--pdf-path-or-url", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", default=str(ROOT / "outputs" / "deepscientist_15x_campaigns"))
    parser.add_argument("--quest-id", default=None)
    parser.add_argument("--quest-root", default=None, help="Explicit quest root, mainly for tests or manual recovery.")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--ds-attempts", type=int, default=2)
    parser.add_argument(
        "--ds-skill",
        default="citation-hypothesis-claims",
        help=(
            "DeepScientist skill to run. Default generates hypothesis-linked citation claims; "
            "use 'citation-evidence-audit' or 'idea' only for comparison."
        ),
    )
    parser.add_argument("--reuse-quest", action="store_true", help="Reuse an existing quest directory if present.")
    parser.add_argument("--skip-ds-restart", action="store_true")
    parser.add_argument(
        "--disable-fallback-claims",
        action="store_true",
        help="Do not use the local auditable claims generator when official DeepScientist fails to write claims.",
    )
    parser.add_argument("--fallback-providers", default="crossref,openalex")
    parser.add_argument("--fallback-timeout-seconds", type=int, default=20)
    parser.add_argument("--fallback-max-pages", type=int, default=3)
    parser.add_argument("--fallback-max-hypotheses", type=int, default=3)
    parser.add_argument("--fallback-max-results-per-query", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    configure_utf8_stdio()
    args = parse_args()
    status = run_case(args)
    return 0 if status.get("final_status") == "success" else 1


def run_case(args: argparse.Namespace) -> dict[str, Any]:
    run_id = args.run_id or timestamp_id()
    case_id = safe_filename(args.case_id)
    campaign_dir = Path(args.output_root).resolve() / run_id
    case_dir = campaign_dir / "cases" / case_id
    logs_dir = case_dir / "logs"
    ds_dir = case_dir / "deepscientist"
    audit_dir = case_dir / "citation_audit"
    multi_review_dir = case_dir / "multi_review"
    case_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    ds_dir.mkdir(parents=True, exist_ok=True)

    quest_id = args.quest_id or f"ds-citation-{case_id}"
    ds_skill = clean_text(getattr(args, "ds_skill", "citation-hypothesis-claims")) or "citation-hypothesis-claims"
    quest_root = Path(args.quest_root).resolve() if args.quest_root else Path.home() / "DeepScientist" / "quests" / quest_id
    status: dict[str, Any] = {
        "case_id": case_id,
        "pdf_path_or_url": args.pdf_path_or_url,
        "run_id": run_id,
        "case_dir": str(case_dir),
        "quest_id": quest_id,
        "quest_root": str(quest_root),
        "ds_skill": ds_skill,
        "quest_status": "not_started",
        "claims_json_status": "not_started",
        "audit_status": "not_started",
        "multi_review_status": "not_started",
        "memory_status": "not_started",
        "claims_source": "not_started",
        "official_claims_file_status": "not_checked",
        "green": 0,
        "yellow": 0,
        "red": 0,
        "missing_artifacts": "",
        "failure_type": "",
        "failure_reason": "",
        "final_status": "running",
        "case_started_epoch": time.time(),
    }
    (ds_dir / "quest_root.txt").write_text(str(quest_root), encoding="utf-8")

    emit_progress(f"Command accepted: case={case_id}. Preparing official DeepScientist workflow.")
    emit_progress("Checking DeepScientist runtime status.")
    if not ensure_ds_ready(logs_dir, status, skip_restart=args.skip_ds_restart):
        return finish_case(case_dir, status)
    emit_progress("DeepScientist status check completed.")

    if not quest_root.exists():
        emit_progress("Creating DeepScientist quest.")
        created = run_logged(
            ["ds", "new", build_goal(case_id, args.pdf_path_or_url), "--quest-id", quest_id],
            logs_dir,
            "ds_new",
            timeout_seconds=min(args.timeout_seconds, 180),
        )
        if created["returncode"] == 0:
            status["quest_status"] = "created"
        elif is_existing_quest_error(created) and quest_root.exists():
            status["quest_status"] = "existing_reused_after_create_conflict"
        else:
            status["quest_status"] = "failed"
            status["failure_type"] = "quest_create_failed"
            status["failure_reason"] = created["stderr_tail"] or created["stdout_tail"]
            return finish_case(case_dir, status)
    else:
        status["quest_status"] = "reused" if args.reuse_quest else "existing_reused"
    emit_progress(f"Quest is ready: {quest_root}")

    if quest_root.exists():
        install_project_skill_for_quest(ds_skill=ds_skill, quest_root=quest_root, status=status)
        emit_progress(f"Skill installed in quest: {ds_skill}. Waiting for DeepScientist to read the skill and write claims.")
        write_runner_brief(
            quest_root=quest_root,
            case_id=case_id,
            pdf_path_or_url=args.pdf_path_or_url,
            run_id=run_id,
            ds_skill=ds_skill,
        )

    claims_path = None
    validation_error = "not_checked"
    for attempt in range(1, max(1, args.ds_attempts) + 1):
        emit_progress(f"DeepScientist is reading the paper, retrieving literature, and generating idea/claims. Attempt {attempt}.")
        prompt = build_claim_generation_prompt(
            case_id=case_id,
            pdf_path_or_url=args.pdf_path_or_url,
            quest_root=quest_root,
            run_id=run_id,
            ds_skill=ds_skill,
        )
        ds_run = run_logged_until_claims(
            ["ds", "run", ds_skill, "--quest-id", quest_id, "--runner", "claude", "--message", prompt],
            logs_dir,
            f"ds_run_{safe_filename(ds_skill)}_attempt_{attempt}",
            timeout_seconds=args.timeout_seconds,
            quest_root=quest_root,
        )
        claims_path = resolve_claims_path(quest_root)
        ok, validation_error = validate_claims_file(claims_path)
        if ok:
            status["claims_json_status"] = "valid_detected_while_running" if ds_run.get("claims_detected") else "valid"
            status["claims_source"] = "official_deepscientist"
            emit_progress("citation_audit_claims.json was generated and passed schema validation.")
            break
        if is_timeout_result(ds_run):
            emit_progress("DeepScientist did not write valid claims in time. Trying the local fallback claims generator.")
            claims_path = generate_fallback_claims(
                args=args,
                case_id=case_id,
                pdf_path_or_url=args.pdf_path_or_url,
                quest_root=quest_root,
                ds_dir=ds_dir,
                case_dir=case_dir,
                status=status,
                reason=ds_run["stderr_tail"] or ds_run["stdout_tail"] or "DeepScientist run timed out.",
            )
            if claims_path is None:
                status["claims_json_status"] = "timeout"
                status["failure_type"] = "deepscientist_run_timeout"
                status["failure_reason"] = ds_run["stderr_tail"] or ds_run["stdout_tail"]
                return finish_case(case_dir, status)
            break
        if attempt == 1:
            (ds_dir / "ds_stdout.txt").write_text(ds_run["stdout"], encoding="utf-8")
            (ds_dir / "ds_stderr.txt").write_text(ds_run["stderr"], encoding="utf-8")
        if ds_run["returncode"] == 0 and ok:
            status["claims_json_status"] = "valid"
            status["claims_source"] = "official_deepscientist"
            break
        status["claims_json_status"] = "missing" if claims_path is None else "invalid"
    else:
        original_claims_path = claims_path
        claims_path = generate_fallback_claims(
            args=args,
            case_id=case_id,
            pdf_path_or_url=args.pdf_path_or_url,
            quest_root=quest_root,
            ds_dir=ds_dir,
            case_dir=case_dir,
            status=status,
            reason=validation_error,
        )
        if claims_path is None:
            status["failure_type"] = "quest_claims_missing" if original_claims_path is None else "claims_schema_invalid"
            status["failure_reason"] = validation_error
            return finish_case(case_dir, status)

    if claims_path:
        canonical_claims_path = ds_dir / "citation_audit_claims.json"
        if Path(claims_path).resolve() != canonical_claims_path.resolve():
            shutil.copy2(claims_path, canonical_claims_path)
        status["claims_path"] = str(claims_path)

    claims_path = prefer_official_claims_if_available(
        quest_root=quest_root,
        ds_dir=ds_dir,
        current_claims_path=claims_path,
        status=status,
    )

    emit_progress("Running citation audit: querying providers and assigning Green/Yellow/Red labels.")
    audit = run_logged_with_progress(
        [
            sys.executable,
            str(ROOT / "scripts" / "audit_deepscientist_output.py"),
            "--claims",
            str(claims_path),
            "--quest-root",
            str(quest_root),
            "--run-dir",
            str(audit_dir),
        ],
        logs_dir,
        "citation_audit",
        timeout_seconds=args.timeout_seconds,
        stage="citation_audit",
    )
    status["audit_status"] = "success" if audit["returncode"] == 0 else "failed"
    if audit["returncode"] != 0:
        status["failure_type"] = "citation_lookup_error"
        status["failure_reason"] = audit["stderr_tail"] or audit["stdout_tail"]
        return finish_case(case_dir, status)
    emit_progress("Citation audit completed. Checking required artifacts.")

    missing = [name for name in AUDIT_ARTIFACTS if not (audit_dir / name).exists()]
    status["missing_artifacts"] = ";".join(missing)
    if missing:
        status["failure_type"] = "artifact_missing"
        status["failure_reason"] = f"Missing audit artifacts: {', '.join(missing)}"
        status["audit_status"] = "artifact_missing"
        return finish_case(case_dir, status)

    counts = count_citation_labels(audit_dir / "citation_verification.csv")
    status.update({"green": counts["Green"], "yellow": counts["Yellow"], "red": counts["Red"]})
    emit_progress(f"Citation label counts: Green={counts['Green']} Yellow={counts['Yellow']} Red={counts['Red']}.")

    emit_progress("Running multi-reviewer panel.")
    status["multi_review_status"] = run_optional_script(
        script=ROOT / "scripts" / "run_multi_reviewer.py",
        cmd=[
            sys.executable,
            str(ROOT / "scripts" / "run_multi_reviewer.py"),
            "--audit-run-dir",
            str(audit_dir),
            "--quest-root",
            str(quest_root),
            "--out-dir",
            str(multi_review_dir),
        ],
        logs_dir=logs_dir,
        label="multi_reviewer",
        timeout_seconds=args.timeout_seconds,
    )
    if status["multi_review_status"] == "success" and not valid_json_file(multi_review_dir / "meta_decision.json"):
        status["multi_review_status"] = "reviewer_json_invalid"
    elif status["multi_review_status"] == "success":
        meta = load_json_file(multi_review_dir / "meta_decision.json")
        status["multi_reviewer_score"] = meta.get("final_score_1_to_6", "")
        status["multi_reviewer_decision"] = meta.get("decision", "")
    emit_progress(f"Multi-reviewer finished: {status['multi_review_status']}.")

    status["final_status"] = "success"
    write_json(case_dir / "case_status.json", status)
    emit_progress("Writing research memory.")
    status["memory_status"] = run_optional_script(
        script=ROOT / "scripts" / "update_research_memory.py",
        cmd=[
            sys.executable,
            str(ROOT / "scripts" / "update_research_memory.py"),
            "--case-dir",
            str(case_dir),
            "--case-id",
            case_id,
            "--run-id",
            run_id,
            "--pdf-path-or-url",
            args.pdf_path_or_url,
            "--quest-root",
            str(quest_root),
            "--final-status",
            "success",
            "--claims-source",
            str(status.get("claims_source", "")),
            "--citation-audit-dir",
            str(audit_dir),
            "--multi-review-dir",
            str(multi_review_dir),
        ],
        logs_dir=logs_dir,
        label="memory_update",
        timeout_seconds=min(args.timeout_seconds, 180),
    )
    if status["memory_status"] == "success":
        memory_summary = load_json_file(case_dir / "memory_update_summary.json")
        status["memory_updates"] = memory_summary.get("updates", "")

    emit_progress("Memory update completed. Generating final_case_report.md.")
    return finish_case(case_dir, status)


def emit_progress(message: str) -> None:
    print(f"[progress] {message}", flush=True)


def generate_fallback_claims(
    *,
    args: argparse.Namespace,
    case_id: str,
    pdf_path_or_url: str,
    quest_root: Path,
    ds_dir: Path,
    case_dir: Path,
    status: dict[str, Any],
    reason: str,
) -> Path | None:
    if getattr(args, "disable_fallback_claims", False):
        return None

    fallback_dir = case_dir / "fallback_claim_generation"
    providers = [
        provider.strip()
        for provider in clean_text(getattr(args, "fallback_providers", "crossref,openalex")).split(",")
        if provider.strip()
    ] or ["crossref", "openalex"]
    try:
        generator = CitationAuditClaimsGenerator(
            fallback_dir,
            timeout_seconds=int(getattr(args, "fallback_timeout_seconds", 20)),
        )
        result = generator.generate(
            case_id=case_id,
            pdf_path_or_url=pdf_path_or_url,
            providers=providers,
            max_pages=int(getattr(args, "fallback_max_pages", 3)),
            max_hypotheses=int(getattr(args, "fallback_max_hypotheses", 3)),
            max_results_per_query=int(getattr(args, "fallback_max_results_per_query", 3)),
        )
        generated_path = Path(result["claims_path"])
        ok, validation_error = validate_claims_file(generated_path)
        if not ok:
            status["fallback_claims_status"] = "invalid"
            status["fallback_claims_reason"] = validation_error
            return None

        quest_root.mkdir(parents=True, exist_ok=True)
        ds_dir.mkdir(parents=True, exist_ok=True)
        quest_fallback_path = quest_root / "local_fallback_citation_audit_claims.json"
        case_fallback_path = ds_dir / "local_fallback_citation_audit_claims.json"
        case_canonical_path = ds_dir / "citation_audit_claims.json"
        shutil.copy2(generated_path, quest_fallback_path)
        shutil.copy2(generated_path, case_fallback_path)
        shutil.copy2(generated_path, case_canonical_path)

        status["claims_json_status"] = "fallback_valid"
        status["claims_source"] = "local_fallback_generator"
        status["claims_path"] = str(case_canonical_path)
        status["fallback_claims_path"] = str(case_fallback_path)
        status["quest_fallback_claims_path"] = str(quest_fallback_path)
        status["fallback_claims_status"] = "success"
        status["fallback_claims_reason"] = clean_text(reason)
        status["fallback_claims_dir"] = str(fallback_dir)
        status["fallback_claims_count"] = result.get("claims_count", 0)
        status["fallback_hypotheses_count"] = result.get("hypotheses_count", 0)
        status["fallback_claims_created_epoch"] = time.time()
        status["official_ds_generation_status"] = "recovered_by_local_fallback"
        status["failure_type"] = "official_ds_claims_recovered_by_fallback"
        status["failure_reason"] = (
            "Official DeepScientist did not produce a valid claims JSON; "
            "local auditable PDF/search/hypothesis fallback generated claims. "
            f"Original reason: {clean_text(reason)}"
        )
        return case_canonical_path
    except Exception as exc:
        status["fallback_claims_status"] = "failed"
        status["fallback_claims_reason"] = f"{clean_text(reason)}; fallback failed: {exc}"
        return None


def prefer_official_claims_if_available(
    *,
    quest_root: Path,
    ds_dir: Path,
    current_claims_path: Path | None,
    status: dict[str, Any],
) -> Path:
    official_path = quest_root / "citation_audit_claims.json"
    if not official_path.exists():
        status["official_claims_file_status"] = "missing"
        if current_claims_path is None:
            raise FileNotFoundError("No official or fallback claims file is available for audit.")
        return current_claims_path

    ok, reason = validate_claims_file(official_path)
    status["official_claims_file_status"] = "valid" if ok else "invalid"
    status["official_claims_file_reason"] = reason
    if not ok:
        if current_claims_path is None:
            raise ValueError(f"Official claims file is invalid and no fallback exists: {reason}")
        return current_claims_path

    ds_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(official_path, ds_dir / "official_citation_audit_claims.json")
    official_mtime = official_path.stat().st_mtime
    case_started = float(status.get("case_started_epoch") or 0.0)
    official_is_current_run = official_mtime >= case_started - 5
    if status.get("claims_source") != "local_fallback_generator" or official_is_current_run:
        status["claims_source"] = (
            "official_deepscientist_late" if status.get("claims_json_status") == "fallback_valid" else "official_deepscientist"
        )
        status["claims_json_status"] = "valid_official_available"
        status["claims_path"] = str(official_path)
        status["official_claims_mtime_epoch"] = official_mtime
        return official_path
    return current_claims_path or official_path


def ensure_ds_ready(logs_dir: Path, status: dict[str, Any], *, skip_restart: bool) -> bool:
    ds_status = run_logged(["ds", "--status"], logs_dir, "ds_status", timeout_seconds=60)
    healthy = False
    try:
        payload = json.loads(ds_status["stdout"])
        healthy = bool(payload.get("healthy"))
    except json.JSONDecodeError:
        healthy = ds_status["returncode"] == 0 and "healthy" in ds_status["stdout"].lower()
    if healthy:
        return True
    if skip_restart:
        status["failure_type"] = "deepscientist_startup_failure"
        status["failure_reason"] = "ds --status is unhealthy and restart was skipped."
        return False
    restart = run_logged(["ds", "--restart", "--runner", "claude", "--no-browser"], logs_dir, "ds_restart", timeout_seconds=180)
    if restart["returncode"] != 0:
        status["failure_type"] = "deepscientist_startup_failure"
        status["failure_reason"] = restart["stderr_tail"] or restart["stdout_tail"]
        return False
    return True


def install_project_skill_for_quest(*, ds_skill: str, quest_root: Path, status: dict[str, Any]) -> None:
    """Copy a project-owned DeepScientist skill into the current quest."""

    source = ROOT / "integrations" / "deepscientist" / ds_skill
    if not source.exists():
        status["project_skill_install_status"] = "skipped_no_project_skill"
        return
    targets = [
        quest_root / ".codex" / "skills" / ds_skill,
        quest_root / ".codex" / "skills" / f"deepscientist-{ds_skill}",
    ]
    try:
        installed_targets = []
        for target in targets:
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
            installed_targets.append(str(target))
        status["project_skill_install_status"] = "installed_for_quest"
        status["project_skill_source"] = str(source)
        status["project_skill_target"] = installed_targets[0]
        status["project_skill_targets"] = installed_targets
    except OSError as exc:
        status["project_skill_install_status"] = "failed"
        status["project_skill_install_error"] = str(exc)


def build_goal(case_id: str, pdf_path_or_url: str) -> str:
    return (
        f"Generate citation-backed research hypotheses for case {case_id}. "
        f"Input paper: {pdf_path_or_url}. This is a citation-audit artifact-generation task; "
        "the experimental baseline gate is explicitly waived. First generate research ideas, then write "
        "citation_audit_claims.json for downstream citation hallucination audit."
    )


def build_claim_generation_prompt(*, case_id: str, pdf_path_or_url: str, quest_root: Path, run_id: str, ds_skill: str) -> str:
    skill_file = quest_root / ".codex" / "skills" / ds_skill / "SKILL.md"
    compat_skill_file = quest_root / ".codex" / "skills" / f"deepscientist-{ds_skill}" / "SKILL.md"
    return f"""You are running inside an official DeepScientist quest for the LLM course Project A.

Repository root:
{ROOT}

Quest root:
{quest_root}

Input paper:
{pdf_path_or_url}

Case id:
{case_id}

Run id:
{run_id}

Custom local skill instructions:
{skill_file}

Compatibility skill path:
{compat_skill_file}

Complete this task automatically:
0. If you need the local skill instructions, call Skill("{ds_skill}") first. If that tool reports
   "Unknown skill", immediately Read `{skill_file}` or `{compat_skill_file}` directly and continue.
   Do not spend time inspecting the global quest state just because the Skill tool failed.
1. Treat the experimental baseline gate as explicitly waived for this quest. This is not a benchmark
   or code experiment; it is a citation-audit artifact-generation task.
2. Read the input paper or PDF URL.
3. Search related literature using available DeepScientist tools.
4. Generate 1-3 conservative research ideas or hypotheses. This step is required even if the
   active skill is citation-evidence-audit; do not only audit an empty or pre-existing report.
5. For each hypothesis, create 1-3 citation-backed claims tied to real retrieved papers.
6. Create this exact file inside the quest root:
   {quest_root / "citation_audit_claims.json"}

Important execution constraint:
- The first durable final artifact must be citation_audit_claims.json.
- Do not run the downstream audit script yourself.
- Do not start a baseline, experiment, long manuscript, or general DeepScientist idea loop.
- Do not send a progress milestone before the JSON file exists.
- Do not call broad quest-state inspection tools such as artifact.get_quest_state, unless direct
  file reads are impossible. Read the runner brief/status/plan and then work directly from the
  input PDF and related-paper tools.
- If search tools are slow or incomplete, use the papers already found and write a conservative JSON.
- Stop once the JSON file exists and is parseable.

The file must be valid JSON with this schema:
{{
  "case_id": "{case_id}",
  "paper": {{
    "title": "",
    "pdf_path_or_url": "{pdf_path_or_url}"
  }},
  "hypotheses": [
    {{
      "hypothesis_id": "H001",
      "research_gap": "",
      "new_hypothesis": "",
      "why_novel": "",
      "risk_or_limitation": "",
      "testable_prediction": ""
    }}
  ],
  "claims": [
    {{
      "claim_id": "C001",
      "hypothesis_id": "H001",
      "claim_text": "",
      "claim_role": "citation_backed_claim",
      "cited_work": {{
        "title": "",
        "authors": [],
        "year": "",
        "doi": "",
        "venue": "",
        "url": "",
        "retrieval_source": "official_deepscientist",
        "abstract": "",
        "snippet": ""
      }}
    }}
  ]
}}

Rules:
- Do not fabricate DOI. If DOI is unknown, leave it as an empty string.
- Every claim must have claim_id, claim_text, and cited_work.title.
- Prefer real papers found through tools.
- Keep claims conservative when evidence is weak.
- Do not decide Green, Yellow, or Red. The local verifier handles labels.
- After writing citation_audit_claims.json, validate that it is parseable JSON and repair it once if needed.
- If the normal DeepScientist idea-stage baseline workflow is not applicable, do not route into a full
  experiment/baseline process. This quest only needs the machine-checkable hypothesis/citation claim file.
"""


def write_runner_brief(*, quest_root: Path, case_id: str, pdf_path_or_url: str, run_id: str, ds_skill: str) -> None:
    brief = f"""# Citation Audit Runner Brief

Case ID: {case_id}
Run ID: {run_id}
Input paper: {pdf_path_or_url}
DeepScientist skill: {ds_skill}

This quest is being driven by `scripts/run_official_ds_case.py` for a course demonstration.
The goal is not to run an ML experiment or establish a reusable code baseline.
The baseline gate is explicitly waived for this citation-audit case.

Required artifact:

```text
citation_audit_claims.json
```

The file must contain conservative hypothesis-linked claims and cited works for the local
deterministic citation verifier. DeepScientist should generate claims and citation metadata only;
the local verifier will decide Green, Yellow, or Red.

Write the JSON file before any long progress message. Do not run the downstream audit script
inside DeepScientist; the runner will call it after the file is detected.
"""
    try:
        (quest_root / "citation_audit_runner_brief.md").write_text(brief, encoding="utf-8")
        (quest_root / "status.md").write_text(
            "# Status\n\n"
            "Citation-audit runner active. The experimental baseline gate is waived for this case.\n"
            "Current required action: generate research ideas and write `citation_audit_claims.json` in the quest root.\n",
            encoding="utf-8",
        )
        (quest_root / "plan.md").write_text(
            "# Plan\n\n"
            "- [x] Waive ML experiment baseline for this citation-audit artifact task\n"
            "- [ ] Read the input PDF or PDF URL\n"
            "- [ ] Search related literature with official DeepScientist tools\n"
            "- [ ] Generate 1-3 conservative research hypotheses or idea cards\n"
            "- [ ] Attach citation-backed claims to real retrieved papers\n"
            "- [ ] Write valid `citation_audit_claims.json` in the quest root\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def resolve_claims_path(quest_root: Path) -> Path | None:
    if not quest_root.exists():
        return None
    for name in CLAIM_FILE_NAMES:
        direct = quest_root / name
        if direct.exists():
            return direct
    for name in CLAIM_FILE_NAMES:
        matches = sorted(safe_find_files_by_name(quest_root, name), key=lambda item: len(item.parts))
        if matches:
            return matches[0]
    return None


def safe_find_files_by_name(root: Path, filename: str) -> list[Path]:
    """Find generated claim files without entering volatile DeepScientist runner caches.

    Official DeepScientist/Claude creates transient directories under `.ds/.../tool-results`.
    Those directories can disappear while the runner polls for `citation_audit_claims.json`.
    `Path.rglob()` raises FileNotFoundError in that race, so this walker prunes unstable
    directories and ignores late filesystem errors.
    """
    matches: list[Path] = []

    def onerror(_exc: OSError) -> None:
        return None

    try:
        walker = os.walk(root, topdown=True, onerror=onerror)
        for current, dirnames, filenames in walker:
            dirnames[:] = [
                name
                for name in dirnames
                if name not in VOLATILE_QUEST_DIR_NAMES and not name.startswith(".")
            ]
            if filename in filenames:
                matches.append(Path(current) / filename)
    except OSError:
        return matches
    return matches


def validate_claims_file(path: Path | None) -> tuple[bool, str]:
    if path is None:
        return False, "citation_audit_claims.json not found."
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return False, f"claims JSON is not parseable: {exc}"
    claims = normalize_deepscientist_claims_payload(payload)
    if not claims:
        return False, "claims JSON must contain at least one auditable citation-backed claim."
    for idx, claim in enumerate(claims, start=1):
        cited = claim.get("cited_work") if isinstance(claim, dict) else None
        if not clean_text((claim or {}).get("claim_id")):
            return False, f"claim #{idx} missing claim_id."
        if not clean_text((claim or {}).get("claim_text")):
            return False, f"claim #{idx} missing claim_text."
        if not isinstance(cited, dict) or not clean_text(cited.get("title")):
            return False, f"claim #{idx} missing cited_work.title."
    return True, ""


def run_optional_script(
    *,
    script: Path,
    cmd: list[str],
    logs_dir: Path,
    label: str,
    timeout_seconds: int,
) -> str:
    if not script.exists():
        return "skipped_missing_script"
    result = run_logged_with_progress(cmd, logs_dir, label, timeout_seconds=timeout_seconds, stage=label)
    return "success" if result["returncode"] == 0 else "failed"


def is_existing_quest_error(result: dict[str, Any]) -> bool:
    text = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
    return "quest already exists" in text


def is_timeout_result(result: dict[str, Any]) -> bool:
    stderr = clean_text(result.get("stderr")).lower()
    stderr_tail = clean_text(result.get("stderr_tail")).lower()
    return result.get("returncode") == -1 or "timed out after" in stderr or "timed out after" in stderr_tail


def run_logged(cmd: list[str], logs_dir: Path, label: str, *, timeout_seconds: int) -> dict[str, Any]:
    result = run_subprocess(cmd, timeout_seconds=timeout_seconds)
    logs_dir.mkdir(parents=True, exist_ok=True)
    safe_label = safe_filename(label)
    (logs_dir / f"{safe_label}_stdout.txt").write_text(result["stdout"], encoding="utf-8")
    (logs_dir / f"{safe_label}_stderr.txt").write_text(result["stderr"], encoding="utf-8")
    (logs_dir / f"{safe_label}_command.json").write_text(
        json.dumps({"cmd": cmd, "returncode": result["returncode"]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        **result,
        "stdout_tail": tail(result["stdout"]),
        "stderr_tail": tail(result["stderr"]),
    }


def run_logged_with_progress(
    cmd: list[str],
    logs_dir: Path,
    label: str,
    *,
    timeout_seconds: int,
    stage: str | None = None,
    heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
) -> dict[str, Any]:
    stage_name = clean_text(stage or label) or label
    logs_dir.mkdir(parents=True, exist_ok=True)
    safe_label = safe_filename(label)
    stdout_path = logs_dir / f"{safe_label}_stdout.txt"
    stderr_path = logs_dir / f"{safe_label}_stderr.txt"
    command_path = logs_dir / f"{safe_label}_command.json"
    resolved_cmd = resolve_windows_command(cmd)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8:replace", "PYTHONUTF8": "1"}
    process: subprocess.Popen[str] | None = None
    returncode = 127
    timeout = False
    start = time.monotonic()
    emit_progress(f"Starting {stage_name}.")
    try:
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_handle, stderr_path.open(
            "w",
            encoding="utf-8",
            errors="replace",
        ) as stderr_handle:
            process = subprocess.Popen(
                resolved_cmd,
                cwd=str(ROOT),
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            deadline = start + timeout_seconds
            next_progress = start + max(0.01, heartbeat_seconds)
            while True:
                now = time.monotonic()
                if process.poll() is not None:
                    returncode = process.returncode if process.returncode is not None else 0
                    break
                if now >= deadline:
                    timeout = True
                    returncode = -1
                    terminate_process_tree(process.pid)
                    break
                if now >= next_progress:
                    elapsed = int(now - start)
                    emit_progress(f"Still running {stage_name}. Elapsed: {elapsed}s.")
                    next_progress = now + max(0.01, heartbeat_seconds)
                time.sleep(min(2.0, max(0.1, next_progress - now), max(0.1, deadline - now)))

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass
    except OSError as exc:
        stderr_path.write_text(str(exc), encoding="utf-8")
        returncode = 127

    stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
    if timeout:
        stderr = f"{stderr}\nTimed out after {timeout_seconds}s".strip()
        stderr_path.write_text(stderr, encoding="utf-8")
        quest_id = extract_cmd_value(cmd, "--quest-id")
        if quest_id:
            terminate_deepscientist_quest_processes(quest_id)
    command_path.write_text(json.dumps({"cmd": cmd, "returncode": returncode}, indent=2, ensure_ascii=False), encoding="utf-8")
    status_text = "success" if returncode == 0 else "failed"
    emit_progress(f"Finished {stage_name}: {status_text}.")
    return {
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_tail": tail(stdout),
        "stderr_tail": tail(stderr),
    }


def run_logged_until_claims(
    cmd: list[str],
    logs_dir: Path,
    label: str,
    *,
    timeout_seconds: int,
    quest_root: Path,
    poll_seconds: int = 10,
    stage: str = "deepscientist_claim_generation",
) -> dict[str, Any]:
    logs_dir.mkdir(parents=True, exist_ok=True)
    safe_label = safe_filename(label)
    stdout_path = logs_dir / f"{safe_label}_stdout.txt"
    stderr_path = logs_dir / f"{safe_label}_stderr.txt"
    command_path = logs_dir / f"{safe_label}_command.json"
    resolved_cmd = resolve_windows_command(cmd)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8:replace"}
    process: subprocess.Popen[str] | None = None
    returncode = 127
    claims_detected = False
    timeout = False
    validation_error = ""
    start = time.monotonic()
    emit_progress(f"Starting {stage}.")
    try:
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_handle, stderr_path.open(
            "w",
            encoding="utf-8",
            errors="replace",
        ) as stderr_handle:
            process = subprocess.Popen(
                resolved_cmd,
                cwd=str(ROOT),
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            deadline = time.monotonic() + timeout_seconds
            next_poll = 0.0
            next_progress = time.monotonic() + 60.0
            while True:
                now = time.monotonic()
                if now >= next_poll:
                    claims_path = resolve_claims_path(quest_root)
                    ok, validation_error = validate_claims_file(claims_path)
                    if ok:
                        claims_detected = True
                        terminate_process_tree(process.pid)
                        break
                    next_poll = now + max(1, poll_seconds)
                if now >= next_progress:
                    elapsed = int(timeout_seconds - max(0.0, deadline - now))
                    emit_progress(f"Still waiting for DeepScientist to write citation_audit_claims.json. Elapsed: {elapsed}s.")
                    next_progress = now + 60.0

                if process.poll() is not None:
                    break
                if now >= deadline:
                    timeout = True
                    terminate_process_tree(process.pid)
                    break
                time.sleep(min(2.0, max(0.1, next_poll - now), max(0.1, deadline - now)))

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass
            if claims_detected:
                returncode = 0
            elif timeout:
                returncode = -1
            else:
                returncode = process.returncode if process.returncode is not None else -1
    except OSError as exc:
        stderr_path.write_text(str(exc), encoding="utf-8")
        returncode = 127

    stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
    if claims_detected:
        stderr = f"{stderr}\nClaims file detected and validated before DeepScientist process exit.".strip()
        stderr_path.write_text(stderr, encoding="utf-8")
    elif timeout:
        stderr = f"{stderr}\nTimed out after {timeout_seconds}s".strip()
        stderr_path.write_text(stderr, encoding="utf-8")

    result = {
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "claims_detected": claims_detected,
        "validation_error": validation_error,
    }
    command_path.write_text(json.dumps({"cmd": cmd, "returncode": returncode}, indent=2, ensure_ascii=False), encoding="utf-8")
    status_text = "success" if returncode == 0 and claims_detected else "failed"
    emit_progress(f"Finished {stage}: {status_text}. Elapsed: {int(time.monotonic() - start)}s.")
    return {
        **result,
        "stdout_tail": tail(stdout),
        "stderr_tail": tail(stderr),
    }


def run_subprocess(cmd: list[str], *, timeout_seconds: int) -> dict[str, Any]:
    resolved_cmd = resolve_windows_command(cmd)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8:replace"}
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            resolved_cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return {"returncode": process.returncode or 0, "stdout": stdout or "", "stderr": stderr or ""}
    except subprocess.TimeoutExpired as exc:
        stdout = clean_text(exc.output or "")
        stderr = clean_text(exc.stderr or "")
        if process is not None:
            terminate_process_tree(process.pid)
        quest_id = extract_cmd_value(cmd, "--quest-id")
        if quest_id:
            terminate_deepscientist_quest_processes(quest_id)
        if process is not None:
            try:
                more_stdout, more_stderr = process.communicate(timeout=5)
                stdout = clean_text(more_stdout or stdout)
                stderr = clean_text(more_stderr or stderr)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass
        timeout_message = f"Timed out after {timeout_seconds}s"
        stderr = f"{stderr}\n{timeout_message}".strip()
        return {
            "returncode": -1,
            "stdout": stdout,
            "stderr": stderr,
        }
    except OSError as exc:
        return {"returncode": 127, "stdout": "", "stderr": str(exc)}


def terminate_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, text=True, check=False)
        return
    try:
        os.kill(pid, 9)
    except OSError:
        pass


def terminate_deepscientist_quest_processes(quest_id: str) -> None:
    if os.name != "nt":
        return
    escaped = quest_id.replace("'", "''")
    runner_pid = os.getpid()
    script = f"""
$current = $PID
$runner = {runner_pid}
$targets = Get-CimInstance Win32_Process | Where-Object {{
    $_.ProcessId -ne $current -and
    $_.ProcessId -ne $runner -and
    $_.CommandLine -like '*{escaped}*' -and
    $_.CommandLine -notlike '*daemon*' -and
    $_.CommandLine -notlike '*run_official_ds_case.py*' -and
    $_.Name -notlike 'powershell*'
}}
foreach ($p in $targets) {{
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}}
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )


def extract_cmd_value(cmd: list[str], flag: str) -> str:
    for idx, part in enumerate(cmd):
        if part == flag and idx + 1 < len(cmd):
            return cmd[idx + 1]
    return ""


def resolve_windows_command(cmd: list[str]) -> list[str]:
    if os.name != "nt" or not cmd:
        return cmd
    executable = cmd[0]
    if Path(executable).suffix:
        return cmd
    for candidate in (f"{executable}.cmd", f"{executable}.exe", executable):
        resolved = shutil.which(candidate)
        if resolved:
            return [resolved, *cmd[1:]]
    return cmd


def count_citation_labels(path: Path) -> dict[str, int]:
    counts = {"Green": 0, "Yellow": 0, "Red": 0}
    if not path.exists():
        return counts
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            label = row.get("color_label", "")
            if label in counts:
                counts[label] += 1
    return counts


def valid_json_file(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        json.loads(path.read_text(encoding="utf-8-sig"))
        return True
    except Exception:
        return False


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def finish_case(case_dir: Path, status: dict[str, Any]) -> dict[str, Any]:
    if status["final_status"] == "running":
        status["final_status"] = "failed"
    status["missing_artifacts"] = compute_missing_core_artifacts(case_dir)
    write_json(case_dir / "case_status.json", status)
    (case_dir / "final_case_report.md").write_text(render_case_report(status), encoding="utf-8")
    return status


def compute_missing_core_artifacts(case_dir: Path) -> str:
    missing = []
    if not (case_dir / "deepscientist" / "citation_audit_claims.json").exists():
        missing.append("deepscientist/citation_audit_claims.json")
    audit_dir = case_dir / "citation_audit"
    for name in AUDIT_ARTIFACTS:
        if not (audit_dir / name).exists():
            missing.append(f"citation_audit/{name}")
    return ";".join(missing)


def render_case_report(status: dict[str, Any]) -> str:
    lines = [
        "# Official DeepScientist Case Report",
        "",
        f"- Case ID: {status.get('case_id')}",
        f"- Input paper: {status.get('pdf_path_or_url')}",
        f"- Quest root: `{status.get('quest_root')}`",
        f"- Case directory: `{status.get('case_dir')}`",
        f"- Final status: {status.get('final_status')}",
        "",
        "## Pipeline Status",
        "",
        f"- Quest: {status.get('quest_status')}",
        f"- Claims JSON: {status.get('claims_json_status')}",
        f"- Citation audit: {status.get('audit_status')}",
        f"- Multi-reviewer: {status.get('multi_review_status')}",
        f"- Memory update: {status.get('memory_status')}",
        f"- Multi-reviewer score: {status.get('multi_reviewer_score', '')}",
        f"- Multi-reviewer decision: {status.get('multi_reviewer_decision', '')}",
        f"- Memory updates: {status.get('memory_updates', '')}",
        "",
        "## Citation Labels",
        "",
        f"- Green: {status.get('green', 0)}",
        f"- Yellow: {status.get('yellow', 0)}",
        f"- Red: {status.get('red', 0)}",
        "",
        "## Failures",
        "",
        f"- Failure type: {status.get('failure_type') or 'none'}",
        f"- Failure reason: {status.get('failure_reason') or 'none'}",
        f"- Missing artifacts: {status.get('missing_artifacts') or 'none'}",
    ]
    return "\n".join(lines) + "\n"


def tail(text: str, limit: int = 3000) -> str:
    return (text or "")[-limit:]


if __name__ == "__main__":
    raise SystemExit(main())
