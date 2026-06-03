#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.utils import clean_text, now_iso, safe_filename, timestamp_id, write_json


CORE_ARTIFACTS = [
    "tool_calls.jsonl",
    "retrieved_literature.jsonl",
    "citation_verification.csv",
    "evidence_chain.csv",
    "final_report.md",
]

DOWNLOAD_FIELDS = [
    "case_id",
    "field",
    "pdf_url",
    "resolved_url",
    "pdf_path",
    "status",
    "bytes",
    "reason",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run cross-domain real-PDF generalization audit.")
    parser.add_argument("--manifest", default=str(ROOT / "inputs" / "generalization_cases" / "manifest.json"))
    parser.add_argument("--output-root", default=str(ROOT / "outputs" / "generalization_audits"))
    parser.add_argument("--providers", default="crossref,openalex,semantic_scholar,arxiv")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--max-queries", type=int, default=4)
    parser.add_argument("--max-followup-queries", type=int, default=3)
    parser.add_argument("--max-results-per-query", type=int, default=2)
    parser.add_argument("--workflow-timeout-seconds", type=int, default=420)
    parser.add_argument("--adapter-timeout-seconds", type=int, default=180)
    parser.add_argument("--download-timeout-seconds", type=int, default=45)
    parser.add_argument("--case-id", action="append", default=[], help="Run only selected case_id values.")
    parser.add_argument("--max-cases", type=int, default=0, help="Optional cap for smoke tests; 0 means all cases.")
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-adapter", action="store_true")
    parser.add_argument("--no-copy-submission", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = (ROOT / manifest_path).resolve()
    manifest = load_manifest(manifest_path)
    cases = validate_manifest(manifest)
    if args.case_id:
        selected = set(args.case_id)
        cases = [case for case in cases if case["case_id"] in selected]
    if args.max_cases > 0:
        cases = cases[: args.max_cases]

    audit_dir = Path(args.output_root) / timestamp_id()
    audit_dir.mkdir(parents=True, exist_ok=True)
    providers = [provider.strip() for provider in args.providers.split(",") if provider.strip()]

    download_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    citation_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    adapter_rows: list[dict[str, Any]] = []
    failures: list[str] = []
    resolved_cases: list[dict[str, Any]] = []

    for idx, case in enumerate(cases, start=1):
        case_id = case["case_id"]
        print(f"[{idx}/{len(cases)}] Generalization case: {case_id}")
        download = ensure_case_pdf(
            case,
            force_download=args.force_download,
            skip_download=args.skip_download,
            timeout_seconds=args.download_timeout_seconds,
        )
        download_rows.append(download)
        resolved_case = {**case, "resolved_pdf_path": download.get("pdf_path"), "resolved_pdf_url": download.get("resolved_url")}
        resolved_cases.append(resolved_case)

        run_dir = audit_dir / "runs" / safe_filename(case_id)
        adapter_dir = audit_dir / "deepscientist_adapter" / safe_filename(case_id)
        summary = base_summary_row(case, download, run_dir, adapter_dir)

        if download["status"] not in {"downloaded", "skipped_existing", "local_existing"}:
            summary["workflow_status"] = "skipped_download_failed"
            failures.append(render_case_failure(case_id, "PDF download failed", download.get("reason", "")))
            summary_rows.append(summary)
            continue

        workflow = run_workflow(case, Path(download["pdf_path"]), run_dir, args, providers)
        summary["workflow_status"] = workflow["status"]
        summary["workflow_returncode"] = workflow["returncode"]
        if workflow["status"] != "success":
            failures.append(render_case_failure(case_id, "Workflow failed", workflow.get("stderr_tail", "")))
            summary_rows.append(summary)
            continue

        artifact_status = artifact_complete(run_dir)
        summary["artifact_complete"] = artifact_status["complete"]
        summary["missing_artifacts"] = ";".join(artifact_status["missing"])
        verification = read_csv(run_dir / "citation_verification.csv")
        chain = read_csv(run_dir / "evidence_chain.csv")
        tool_calls = read_jsonl(run_dir / "tool_calls.jsonl")
        literature = read_jsonl(run_dir / "retrieved_literature.jsonl")
        labels = count_labels(verification)
        categories = count_support_categories(chain)
        summary.update(
            {
                "green": labels["Green"],
                "yellow": labels["Yellow"],
                "red": labels["Red"],
                "directly_supported": categories["directly_supported"],
                "uncertain": categories["reasonable_inference_or_uncertain"],
                "unsupported": categories["insufficient_or_unsupported"],
                "retrieved_literature_count": len(literature),
                "tool_error_count": sum(1 for call in tool_calls if call.get("status") == "error"),
            }
        )
        citation_rows.extend({"case_id": case_id, "field": case.get("field", ""), **row} for row in verification)
        evidence_rows.extend({"case_id": case_id, "field": case.get("field", ""), **row} for row in chain)
        if not artifact_status["complete"]:
            failures.append(render_case_failure(case_id, "Missing artifacts", "; ".join(artifact_status["missing"])))

        if not args.skip_adapter:
            adapter = run_adapter(run_dir / "generated_claims.json", adapter_dir, args)
            adapter_summary = summarize_adapter_result({**case, "run_dir": str(run_dir)}, adapter_dir, adapter)
            adapter_rows.append(adapter_summary)
            summary["adapter_status"] = adapter_summary["adapter_status"]
            summary["adapter_green"] = adapter_summary["adapter_green"]
            summary["adapter_yellow"] = adapter_summary["adapter_yellow"]
            summary["adapter_red"] = adapter_summary["adapter_red"]
            summary["adapter_label_match"] = adapter_summary["adapter_label_match"]
            if adapter["status"] != "success":
                failures.append(render_case_failure(case_id, "DeepScientist adapter failed", adapter.get("stderr_tail", "")))
        else:
            summary["adapter_status"] = "skipped"
        summary_rows.append(summary)

    domain_rows = build_domain_coverage(summary_rows)
    write_json(audit_dir / "case_manifest_resolved.json", {"generated_at": now_iso(), "cases": resolved_cases})
    write_csv(audit_dir / "download_audit.csv", download_rows, DOWNLOAD_FIELDS)
    write_csv(audit_dir / "generalization_summary.csv", summary_rows)
    write_csv(audit_dir / "domain_coverage.csv", domain_rows)
    write_csv(audit_dir / "citation_label_summary.csv", citation_rows)
    write_csv(audit_dir / "evidence_chain_summary.csv", evidence_rows)
    write_csv(audit_dir / "deepscientist_adapter_summary.csv", adapter_rows)
    (audit_dir / "failure_cases.md").write_text(render_failures(failures), encoding="utf-8")
    (audit_dir / "generalization_report.md").write_text(
        render_generalization_report(summary_rows, domain_rows, adapter_rows, failures, providers),
        encoding="utf-8",
    )

    if not args.no_copy_submission:
        target = ROOT / "submission" / "generalization_audit"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(audit_dir, target)

    print(f"Generalization audit complete: {audit_dir}")
    if not args.no_copy_submission:
        print(f"Copied classroom package to: {ROOT / 'submission' / 'generalization_audit'}")
    return 0


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Manifest must contain a non-empty 'cases' list.")
    required = ("case_id", "field", "pdf_url", "pdf_path")
    seen: set[str] = set()
    for idx, case in enumerate(cases, start=1):
        missing = [field for field in required if not clean_text(case.get(field))]
        if missing:
            raise ValueError(f"Case #{idx} is missing required fields: {', '.join(missing)}")
        case_id = clean_text(case["case_id"])
        if case_id in seen:
            raise ValueError(f"Duplicate case_id: {case_id}")
        seen.add(case_id)
    return cases


def ensure_case_pdf(
    case: dict[str, Any],
    *,
    force_download: bool,
    skip_download: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    pdf_url = clean_text(case.get("pdf_url"))
    pdf_path = resolve_path(case["pdf_path"])
    resolved_url = resolve_pdf_url(pdf_url)
    if pdf_url.startswith("local:"):
        local_path = resolve_path(pdf_url.removeprefix("local:"))
        return {
            "case_id": case["case_id"],
            "field": case.get("field", ""),
            "pdf_url": pdf_url,
            "resolved_url": str(local_path),
            "pdf_path": str(local_path),
            "status": "local_existing" if local_path.exists() else "missing_local",
            "bytes": local_path.stat().st_size if local_path.exists() else 0,
            "reason": "" if local_path.exists() else f"Local PDF not found: {local_path}",
        }
    if pdf_path.exists() and not force_download:
        return {
            "case_id": case["case_id"],
            "field": case.get("field", ""),
            "pdf_url": pdf_url,
            "resolved_url": resolved_url,
            "pdf_path": str(pdf_path),
            "status": "skipped_existing",
            "bytes": pdf_path.stat().st_size,
            "reason": "PDF already exists.",
        }
    if skip_download:
        return {
            "case_id": case["case_id"],
            "field": case.get("field", ""),
            "pdf_url": pdf_url,
            "resolved_url": resolved_url,
            "pdf_path": str(pdf_path),
            "status": "skipped_missing",
            "bytes": 0,
            "reason": "Download skipped and PDF is missing.",
        }
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        request = urllib.request.Request(
            resolved_url,
            headers={"User-Agent": "llm-hypothesis-citation-agent/0.1 generalization-audit"},
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = response.read()
        if not data.startswith(b"%PDF"):
            return {
                "case_id": case["case_id"],
                "field": case.get("field", ""),
                "pdf_url": pdf_url,
                "resolved_url": resolved_url,
                "pdf_path": str(pdf_path),
                "status": "not_pdf",
                "bytes": len(data),
                "reason": "Downloaded payload did not start with %PDF.",
            }
        pdf_path.write_bytes(data)
        return {
            "case_id": case["case_id"],
            "field": case.get("field", ""),
            "pdf_url": pdf_url,
            "resolved_url": resolved_url,
            "pdf_path": str(pdf_path),
            "status": "downloaded",
            "bytes": len(data),
            "reason": "",
        }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "case_id": case["case_id"],
            "field": case.get("field", ""),
            "pdf_url": pdf_url,
            "resolved_url": resolved_url,
            "pdf_path": str(pdf_path),
            "status": "download_failed",
            "bytes": 0,
            "reason": str(exc),
        }


def resolve_pdf_url(url: str) -> str:
    if url.startswith("local:"):
        return url
    match = re.search(r"arxiv\.org/abs/([^?#]+)", url)
    if match:
        return f"https://arxiv.org/pdf/{match.group(1)}"
    return url


def resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def base_summary_row(case: dict[str, Any], download: dict[str, Any], run_dir: Path, adapter_dir: Path) -> dict[str, Any]:
    return {
        "case_id": case["case_id"],
        "field": case.get("field", ""),
        "pdf_path": download.get("pdf_path", ""),
        "run_dir": str(run_dir),
        "adapter_dir": str(adapter_dir),
        "download_status": download.get("status", ""),
        "workflow_status": "not_started",
        "workflow_returncode": "",
        "adapter_status": "not_started",
        "artifact_complete": False,
        "missing_artifacts": "",
        "green": 0,
        "yellow": 0,
        "red": 0,
        "directly_supported": 0,
        "uncertain": 0,
        "unsupported": 0,
        "retrieved_literature_count": 0,
        "tool_error_count": 0,
        "adapter_green": 0,
        "adapter_yellow": 0,
        "adapter_red": 0,
        "adapter_label_match": False,
        "expected_red": bool(case.get("expected_red", False)),
    }


def run_workflow(
    case: dict[str, Any],
    pdf_path: Path,
    run_dir: Path,
    args: argparse.Namespace,
    providers: list[str],
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "agent" / "workflow.py"),
        "--pdf",
        str(pdf_path),
        "--task",
        f"Generalization audit case {case['case_id']}: generate hypothesis and verify citations",
        "--providers",
        ",".join(providers),
        "--max-pages",
        str(args.max_pages),
        "--max-queries",
        str(args.max_queries),
        "--max-followup-queries",
        str(args.max_followup_queries),
        "--max-results-per-query",
        str(args.max_results_per_query),
        "--run-dir",
        str(run_dir),
    ]
    if case.get("inject_bad_citation"):
        cmd.append("--inject-bad-citation")
    return run_subprocess(cmd, timeout_seconds=args.workflow_timeout_seconds)


def run_adapter(claims_path: Path, adapter_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    if not claims_path.exists():
        return {"status": "missing_claims", "returncode": 2, "stdout_tail": "", "stderr_tail": f"Missing {claims_path}"}
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "audit_deepscientist_output.py"),
        "--claims",
        str(claims_path),
        "--run-dir",
        str(adapter_dir),
    ]
    return run_subprocess(cmd, timeout_seconds=args.adapter_timeout_seconds)


def run_subprocess(cmd: list[str], *, timeout_seconds: int) -> dict[str, Any]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8:replace"}
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "status": "success" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "stdout_tail": tail(completed.stdout),
            "stderr_tail": tail(completed.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "returncode": -1,
            "stdout_tail": tail(exc.stdout or ""),
            "stderr_tail": f"Timed out after {timeout_seconds}s",
        }


def artifact_complete(run_dir: Path) -> dict[str, Any]:
    missing = [name for name in CORE_ARTIFACTS if not (run_dir / name).exists()]
    return {"complete": not missing, "missing": missing}


def count_labels(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"Green": 0, "Yellow": 0, "Red": 0}
    for row in rows:
        label = row.get("color_label", "Red")
        counts[label] = counts.get(label, 0) + 1
    return counts


def count_support_categories(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "directly_supported": 0,
        "reasonable_inference_or_uncertain": 0,
        "insufficient_or_unsupported": 0,
    }
    for row in rows:
        category = row.get("support_category", "insufficient_or_unsupported")
        counts[category] = counts.get(category, 0) + 1
    return counts


def summarize_adapter_result(case: dict[str, Any], adapter_dir: Path, adapter_result: dict[str, Any]) -> dict[str, Any]:
    labels = count_labels(read_csv(adapter_dir / "citation_verification.csv"))
    local_labels = count_labels(read_csv(Path(case.get("run_dir", "")) / "citation_verification.csv")) if case.get("run_dir") else None
    if local_labels is None:
        local_labels = labels
    return {
        "case_id": case["case_id"],
        "field": case.get("field", ""),
        "adapter_status": adapter_result["status"],
        "adapter_returncode": adapter_result["returncode"],
        "adapter_green": labels["Green"],
        "adapter_yellow": labels["Yellow"],
        "adapter_red": labels["Red"],
        "adapter_label_match": labels == local_labels,
        "stderr_tail": adapter_result.get("stderr_tail", ""),
    }


def build_domain_coverage(summary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in summary_rows:
        grouped[row.get("field", "")].append(row)
    rows: list[dict[str, Any]] = []
    for field, items in sorted(grouped.items()):
        rows.append(
            {
                "field": field,
                "case_count": len(items),
                "completed_cases": sum(1 for item in items if item.get("workflow_status") == "success"),
                "green": sum(int(item.get("green", 0) or 0) for item in items),
                "yellow": sum(int(item.get("yellow", 0) or 0) for item in items),
                "red": sum(int(item.get("red", 0) or 0) for item in items),
                "artifact_complete": sum(1 for item in items if str(item.get("artifact_complete")).lower() == "true"),
            }
        )
    return rows


def render_failures(failures: list[str]) -> str:
    if not failures:
        return "# Failure Cases\n\nNo generalization-audit failures were recorded.\n"
    return "# Failure Cases\n\n" + "\n".join(failures)


def render_case_failure(case_id: str, title: str, detail: str) -> str:
    return f"## {case_id}\n\n{title}\n\n```text\n{tail(detail, 1200)}\n```\n"


def render_generalization_report(
    summary_rows: list[dict[str, Any]],
    domain_rows: list[dict[str, Any]],
    adapter_rows: list[dict[str, Any]],
    failures: list[str],
    providers: list[str],
) -> str:
    labels = {
        "Green": sum(int(row.get("green", 0) or 0) for row in summary_rows),
        "Yellow": sum(int(row.get("yellow", 0) or 0) for row in summary_rows),
        "Red": sum(int(row.get("red", 0) or 0) for row in summary_rows),
    }
    completed = sum(1 for row in summary_rows if row.get("workflow_status") == "success")
    distinct_fields = len({row.get("field", "") for row in summary_rows if row.get("field")})
    adapter_completed = sum(1 for row in adapter_rows if row.get("adapter_status") == "success")
    lines = [
        "# Cross-Domain Generalization Audit Report",
        "",
        f"Generated: {now_iso()}",
        "",
        "## Scope",
        "",
        f"- Cases configured: {len(summary_rows)}",
        f"- Completed workflow cases: {completed}",
        f"- Distinct fields: {distinct_fields}",
        f"- Providers requested: {', '.join(providers)}",
        f"- DeepScientist adapter completed: {adapter_completed}",
        "",
        "## Label Distribution",
        "",
        f"- Green: {labels['Green']}",
        f"- Yellow: {labels['Yellow']}",
        f"- Red: {labels['Red']}",
        "",
        "## Domain Coverage",
        "",
        "| Field | Cases | Completed | Green | Yellow | Red |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in domain_rows:
        lines.append(
            f"| {row.get('field')} | {row.get('case_count')} | {row.get('completed_cases')} | "
            f"{row.get('green')} | {row.get('yellow')} | {row.get('red')} |"
        )
    lines.extend(
        [
            "",
            "## Acceptance Check",
            "",
            f"- At least 12 of 15 cases complete: {'PASS' if completed >= 12 else 'FAIL'} ({completed}/15)",
            f"- At least 8 distinct fields: {'PASS' if distinct_fields >= 8 else 'FAIL'} ({distinct_fields})",
            f"- At least one Green: {'PASS' if labels['Green'] >= 1 else 'FAIL'}",
            f"- At least one Red: {'PASS' if labels['Red'] >= 1 else 'FAIL'}",
            "",
            "## Limitations",
            "",
            "- Public APIs may rate-limit requests; those rows should remain Yellow/inconclusive rather than fabricated.",
            "- Public metadata often lacks abstracts, so Yellow labels are expected for some real citations.",
            "- This audit proves cross-domain behavior of the evidence-chain module, not scientific truth of each generated hypothesis.",
            "",
            "## Failure Summary",
            "",
            f"- Failure entries recorded: {len(failures)}",
        ]
    )
    return "\n".join(lines)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def tail(text: Any, limit: int = 800) -> str:
    value = clean_text(text)
    return value[-limit:] if len(value) > limit else value


if __name__ == "__main__":
    raise SystemExit(main())
