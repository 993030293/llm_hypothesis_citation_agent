#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.utils import clean_text, safe_filename, timestamp_id, write_json


SUMMARY_FIELDS = [
    "case_id",
    "field",
    "pdf_path_or_url",
    "final_status",
    "quest_status",
    "claims_json_status",
    "audit_status",
    "multi_review_status",
    "memory_status",
    "green",
    "yellow",
    "red",
    "multi_reviewer_score",
    "memory_updates",
    "failure_type",
    "failure_reason",
    "case_dir",
    "quest_root",
]

EXTRA_20_CASES = [
{
    "case_id": "ai_clip_transfer",
    "field": "Vision / Multimodal AI",
    "pdf_url": "https://arxiv.org/pdf/2103.00020",
    "pdf_path": "inputs/deepscientist_20_cases/papers/ai_clip_transfer.pdf",
    "source_note": "Real public arXiv PDF: Learning Transferable Visual Models From Natural Language Supervision.",
    "expected_risk": "normal_real_pdf",
},
{
    "case_id": "cv_segment_anything",
    "field": "Computer Vision / Segmentation",
    "pdf_url": "https://arxiv.org/pdf/2304.02643",
    "pdf_path": "inputs/deepscientist_20_cases/papers/cv_segment_anything.pdf",
    "source_note": "Real public arXiv PDF: Segment Anything.",
    "expected_risk": "normal_real_pdf",
},
{
    "case_id": "ml_lora_adaptation",
    "field": "LLM Adaptation",
    "pdf_url": "https://arxiv.org/pdf/2106.09685",
    "pdf_path": "inputs/deepscientist_20_cases/papers/ml_lora_adaptation.pdf",
    "source_note": "Real public arXiv PDF: LoRA: Low-Rank Adaptation of Large Language Models.",
    "expected_risk": "normal_real_pdf",
},
{
    "case_id": "genai_diffusion_ddpm",
    "field": "Generative Models",
    "pdf_url": "https://arxiv.org/pdf/2006.11239",
    "pdf_path": "inputs/deepscientist_20_cases/papers/genai_diffusion_ddpm.pdf",
    "source_note": "Real public arXiv PDF: Denoising Diffusion Probabilistic Models.",
    "expected_risk": "normal_real_pdf",
},
{
    "case_id": "biomed_medpalm",
    "field": "Medical LLM",
    "pdf_url": "https://arxiv.org/pdf/2212.13138",
    "pdf_path": "inputs/deepscientist_20_cases/papers/biomed_medpalm.pdf",
    "source_note": "Real public arXiv PDF: Large Language Models Encode Clinical Knowledge.",
    "expected_risk": "normal_real_pdf",
},
{
    "case_id": "bio_esmfold_protein",
    "field": "Computational Biology",
    "pdf_url": "https://arxiv.org/pdf/2212.03533",
    "pdf_path": "inputs/deepscientist_20_cases/papers/bio_esmfold_protein.pdf",
    "source_note": "Real public arXiv PDF: Evolutionary-scale prediction of atomic-level protein structure with a language model.",
    "expected_risk": "normal_real_pdf",
},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the official DeepScientist 20-paper citation-audit campaign.")
    parser.add_argument("--manifest", default=str(ROOT / "inputs" / "deepscientist_20_cases" / "manifest.json"))
    parser.add_argument("--output-root", default=str(ROOT / "outputs" / "deepscientist_20x_campaigns"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--ds-skill", default="citation-hypothesis-claims")
    parser.add_argument("--reuse-quests", action="store_true")
    parser.add_argument("--no-copy-submission", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return main_with_args(args)


def main_with_args(args: argparse.Namespace) -> int:
    run_id = args.run_id or timestamp_id()
    campaign_dir = Path(args.output_root).resolve() / run_id
    campaign_dir.mkdir(parents=True, exist_ok=True)

    cases = load_real_cases(Path(args.manifest))
    if args.case_id:
        selected = set(args.case_id)
        cases = [case for case in cases if case["case_id"] in selected]
    if args.max_cases > 0:
        cases = cases[: args.max_cases]

    write_json(campaign_dir / "campaign_manifest_resolved.json", {"run_id": run_id, "cases": cases})
    rows: list[dict[str, Any]] = []
    deficiencies: list[str] = []

    for idx, case in enumerate(cases, start=1):
        print(f"[{idx}/{len(cases)}] Official DeepScientist case: {case['case_id']}")
        result = run_case_subprocess(case, run_id, campaign_dir, args)
        status = load_case_status(campaign_dir, case, result)
        rows.append(status)
        if status.get("failure_type"):
            deficiencies.append(render_deficiency(status))
        write_csv(campaign_dir / "case_status.csv", rows)
        write_csv(campaign_dir / "campaign_summary.csv", rows)
        (campaign_dir / "deficiency_log.md").write_text(render_deficiency_log(deficiencies), encoding="utf-8")
        (campaign_dir / "campaign_report.md").write_text(render_campaign_report(rows, deficiencies), encoding="utf-8")

    if not args.no_copy_submission:
        target = ROOT / "submission" / "deepscientist_20x_campaign"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(campaign_dir, target)
    print(f"Campaign complete: {campaign_dir}")
    return 0


def load_real_cases(manifest_path: Path) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = []
    seen: set[str] = set()
    for case in manifest.get("cases", []):
        case_id = clean_text(case.get("case_id"))
        if not case_id or case_id == "boundary_bad_citation" or case.get("expected_red"):
            continue
        cases.append(case)
        seen.add(case_id)
    for extra_case in EXTRA_20_CASES:
        if extra_case["case_id"] not in seen:
            cases.append(extra_case)
            seen.add(extra_case["case_id"])
    return cases[:20]


def run_case_subprocess(case: dict[str, Any], run_id: str, campaign_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    case_id = safe_filename(case["case_id"])
    case_dir = campaign_dir / "cases" / case_id
    logs_dir = case_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    pdf_path_or_url = resolve_case_pdf_path_or_url(case)
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_official_ds_case.py"),
        "--case-id",
        case_id,
        "--pdf-path-or-url",
        str(pdf_path_or_url),
        "--run-id",
        run_id,
        "--output-root",
        str(campaign_dir.parent),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--ds-skill",
        str(getattr(args, "ds_skill", "citation-hypothesis-claims")),
    ]
    if args.reuse_quests:
        cmd.append("--reuse-quest")
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=max(args.timeout_seconds * 3, 600),
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        returncode = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = str(exc.stdout or "")
        stderr = f"Timed out after {max(args.timeout_seconds * 3, 600)}s"
        returncode = -1
    except OSError as exc:
        stdout = ""
        stderr = str(exc)
        returncode = 127
    (logs_dir / "run_official_ds_case_stdout.txt").write_text(stdout, encoding="utf-8")
    (logs_dir / "run_official_ds_case_stderr.txt").write_text(stderr, encoding="utf-8")
    return {"returncode": returncode, "stdout": stdout, "stderr": stderr}


def load_case_status(campaign_dir: Path, case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    case_id = safe_filename(case["case_id"])
    path = campaign_dir / "cases" / case_id / "case_status.json"
    if path.exists():
        status = json.loads(path.read_text(encoding="utf-8"))
    else:
        status = {
            "case_id": case_id,
            "pdf_path_or_url": resolve_case_pdf_path_or_url(case),
            "final_status": "failed",
            "quest_status": "unknown",
            "claims_json_status": "unknown",
            "audit_status": "unknown",
            "multi_review_status": "unknown",
            "memory_status": "unknown",
            "green": 0,
            "yellow": 0,
            "red": 0,
            "failure_type": "case_runner_failed",
            "failure_reason": result.get("stderr") or result.get("stdout") or "case runner did not produce case_status.json",
            "case_dir": str(campaign_dir / "cases" / case_id),
            "quest_root": "",
        }
    status["field"] = case.get("field", "")
    status["pdf_path_or_url"] = resolve_case_pdf_path_or_url(case)
    case_dir = Path(status.get("case_dir") or campaign_dir / "cases" / case_id)
    status["multi_reviewer_score"] = read_meta_reviewer_score(case_dir)
    status["memory_updates"] = count_memory_updates(case_dir)
    return {field: status.get(field, "") for field in SUMMARY_FIELDS}


def resolve_case_pdf_path_or_url(case: dict[str, Any]) -> str:
    pdf_path = clean_text(case.get("pdf_path"))
    if pdf_path:
        path = Path(pdf_path)
        if not path.is_absolute():
            path = ROOT / path
        if path.exists():
            return str(path)
    pdf_url = clean_text(case.get("pdf_url"))
    if pdf_url.startswith("local:"):
        path = ROOT / pdf_url[len("local:") :]
        if path.exists():
            return str(path)
    return pdf_url or pdf_path


def read_meta_reviewer_score(case_dir: Path) -> str:
    path = case_dir / "multi_review" / "meta_decision.json"
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return ""
    value = payload.get("final_score_1_to_6")
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return ""


def count_memory_updates(case_dir: Path) -> int:
    total = 0
    for path in [case_dir / "memory_updates.jsonl", case_dir / "memory" / "memory_updates.jsonl"]:
        if path.exists():
            total += sum(1 for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())
    return total


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in SUMMARY_FIELDS})


def render_deficiency(status: dict[str, Any]) -> str:
    return (
        f"## {status.get('case_id')}\n\n"
        f"- Failure type: {status.get('failure_type')}\n"
        f"- Reason: {status.get('failure_reason')}\n"
        f"- Case dir: `{status.get('case_dir')}`\n"
    )


def render_deficiency_log(items: list[str]) -> str:
    if not items:
        return "# Deficiency Log\n\nNo deficiencies recorded.\n"
    return "# Deficiency Log\n\n" + "\n".join(items)


def render_campaign_report(rows: list[dict[str, Any]], deficiencies: list[str]) -> str:
    completed = sum(1 for row in rows if row.get("final_status") == "success")
    green = sum(int(row.get("green") or 0) for row in rows)
    yellow = sum(int(row.get("yellow") or 0) for row in rows)
    red = sum(int(row.get("red") or 0) for row in rows)
    reviewer_scores = []
    for row in rows:
        try:
            reviewer_scores.append(float(row.get("multi_reviewer_score") or ""))
        except ValueError:
            pass
    reviewer_average = f"{sum(reviewer_scores) / len(reviewer_scores):.2f}" if reviewer_scores else "N/A"
    memory_updates = sum(int(row.get("memory_updates") or 0) for row in rows)
    lines = [
        "# Official DeepScientist 20x Campaign Report",
        "",
        f"- Cases attempted: {len(rows)}",
        f"- Cases completed: {completed}",
        f"- Cases failed or partial: {len(rows) - completed}",
        f"- Green: {green}",
        f"- Yellow: {yellow}",
        f"- Red: {red}",
        f"- Multi-reviewer average score: {reviewer_average}",
        f"- Memory updates written: {memory_updates}",
        f"- Deficiencies: {len(deficiencies)}",
        "",
        "## Case Table",
        "",
        "| Case | Status | Green | Yellow | Red | Failure |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('case_id')} | {row.get('final_status')} | {row.get('green')} | "
            f"{row.get('yellow')} | {row.get('red')} | {row.get('failure_type')} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
