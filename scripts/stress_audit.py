#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.online_audit import AUDIT_FIELDS, OnlineCitationAuditor
from agent.pdf_preflight import preflight_pdf
from agent.utils import clean_text, now_iso, safe_filename, timestamp_id, write_json

CORE_ARTIFACTS = [
    "input_task.md",
    "paper_summary.json",
    "search_queries.json",
    "retrieved_literature.jsonl",
    "generated_hypothesis.md",
    "citation_verification.csv",
    "evidence_chain.csv",
    "evidence_chain.md",
    "final_report.md",
    "tool_calls.jsonl",
    "evidence_items.jsonl",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full-mode stress audit across PDF layout/source cases.")
    parser.add_argument("--case-dir", default=str(ROOT / "inputs" / "stress_cases"))
    parser.add_argument("--output-root", default=str(ROOT / "outputs" / "stress_audits"))
    parser.add_argument("--providers", default="crossref,openalex,semantic_scholar,arxiv")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--max-queries", type=int, default=5)
    parser.add_argument("--max-followup-queries", type=int, default=4)
    parser.add_argument("--max-results-per-query", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=420)
    parser.add_argument("--max-cases", type=int, default=0, help="Optional cap for smoke tests; 0 means all cases.")
    parser.add_argument("--case-id", action="append", default=[], help="Run only selected case_id values.")
    parser.add_argument("--skip-online", action="store_true", help="Skip independent online re-audit.")
    parser.add_argument("--no-copy-submission", action="store_true")
    parser.add_argument("--create-missing-cases", action="store_true", default=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    case_dir = Path(args.case_dir)
    if args.create_missing_cases and not list(case_dir.glob("*.json")):
        from scripts.create_stress_cases import build_cases

        build_cases(case_dir)

    audit_dir = Path(args.output_root) / timestamp_id()
    audit_dir.mkdir(parents=True, exist_ok=True)
    providers = [provider.strip() for provider in args.providers.split(",") if provider.strip()]
    cases = load_cases(case_dir, selected=set(args.case_id))
    if args.max_cases > 0:
        cases = cases[: args.max_cases]

    auditor = OnlineCitationAuditor()
    resolved_cases: list[dict[str, Any]] = []
    stress_rows: list[dict[str, Any]] = []
    extraction_rows: list[dict[str, Any]] = []
    query_rows: list[dict[str, Any]] = []
    retrieval_rows: list[dict[str, Any]] = []
    citation_rows: list[dict[str, Any]] = []
    online_rows: list[dict[str, Any]] = []
    failures: list[str] = []

    for idx, case in enumerate(cases, start=1):
        case_id = case["case_id"]
        pdf_path = resolve_path(case["pdf_path"])
        case_run_dir = audit_dir / "runs" / safe_filename(case_id)
        print(f"[{idx}/{len(cases)}] Stress case: {case_id}")
        resolved_case = {**case, "pdf_path_abs": str(pdf_path), "run_dir": str(case_run_dir)}
        resolved_cases.append(resolved_case)

        preflight: dict[str, Any]
        try:
            preflight = preflight_pdf(pdf_path, max_pages=min(2, args.max_pages))
        except Exception as exc:  # noqa: BLE001
            preflight = {"readiness": "risky", "risk_flags": ["preflight_failed"], "error": str(exc)}

        workflow = run_workflow(case, pdf_path, case_run_dir, args, providers)
        summary_row = {
            "case_id": case_id,
            "discipline": case.get("discipline", ""),
            "layout_type": case.get("layout_type", ""),
            "pdf_path": str(pdf_path),
            "run_dir": str(case_run_dir),
            "workflow_status": workflow["status"],
            "returncode": workflow["returncode"],
            "preflight_readiness": preflight.get("readiness", ""),
            "artifact_complete": False,
            "green": 0,
            "yellow": 0,
            "red": 0,
            "retrieved_literature_count": 0,
            "tool_error_count": 0,
        }

        if workflow["status"] != "success":
            failures.append(f"## {case_id}\n\nWorkflow failed.\n\n{workflow['stderr_tail']}\n")
            stress_rows.append(summary_row)
            extraction_rows.append(audit_extraction(case, preflight, None))
            continue

        artifact_status = artifact_complete(case_run_dir)
        summary_row["artifact_complete"] = artifact_status["complete"]
        paper_summary = read_json(case_run_dir / "paper_summary.json")
        queries_payload = read_json(case_run_dir / "search_queries.json")
        literature = read_jsonl(case_run_dir / "retrieved_literature.jsonl")
        tool_calls = read_jsonl(case_run_dir / "tool_calls.jsonl")
        verification = read_csv(case_run_dir / "citation_verification.csv")
        counts = Counter(row.get("color_label", "") for row in verification)
        summary_row.update(
            {
                "green": counts.get("Green", 0),
                "yellow": counts.get("Yellow", 0),
                "red": counts.get("Red", 0),
                "retrieved_literature_count": len(literature),
                "tool_error_count": sum(1 for row in tool_calls if row.get("status") == "error"),
            }
        )

        extraction = audit_extraction(case, preflight, paper_summary)
        extraction_rows.append(extraction)
        query_rows.append(audit_queries(case, queries_payload))
        retrieval_rows.extend(audit_retrieval(case, providers, literature, tool_calls))
        for row in verification:
            citation_rows.append({"case_id": case_id, **row})
            if not args.skip_online and case.get("online_audit", True):
                online_rows.append(auditor.audit_row(row, case_id=case_id))

        if not artifact_status["complete"]:
            failures.append(f"## {case_id}\n\nMissing artifacts: {', '.join(artifact_status['missing'])}\n")
        if extraction.get("failure_category"):
            failures.append(f"## {case_id}\n\nExtraction issue: {extraction['failure_category']}\n")
        stress_rows.append(summary_row)

    write_json(audit_dir / "case_manifest_resolved.json", {"generated_at": now_iso(), "cases": resolved_cases})
    write_csv(audit_dir / "stress_summary.csv", stress_rows)
    write_csv(audit_dir / "extraction_audit.csv", extraction_rows)
    write_csv(audit_dir / "query_audit.csv", query_rows)
    write_csv(audit_dir / "retrieval_audit.csv", retrieval_rows)
    write_csv(audit_dir / "citation_label_audit.csv", citation_rows)
    write_csv(audit_dir / "online_verification_audit.csv", online_rows, fieldnames=AUDIT_FIELDS)
    (audit_dir / "failure_cases.md").write_text(render_failures(failures), encoding="utf-8")
    (audit_dir / "stress_report.md").write_text(
        render_report(stress_rows, extraction_rows, retrieval_rows, citation_rows, online_rows, providers),
        encoding="utf-8",
    )

    if not args.no_copy_submission:
        target = ROOT / "submission" / "stress_audit"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(audit_dir, target)

    print(f"Stress audit complete: {audit_dir}")
    if not args.no_copy_submission:
        print(f"Copied classroom package to: {ROOT / 'submission' / 'stress_audit'}")
    return 0


def load_cases(case_dir: Path, selected: set[str]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted(case_dir.glob("*.json")):
        if path.name == "stress_cases_manifest.json":
            continue
        case = read_json(path)
        if selected and case.get("case_id") not in selected:
            continue
        case["_manifest_path"] = str(path)
        cases.append(case)
    return cases


def resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def run_workflow(case: dict[str, Any], pdf_path: Path, run_dir: Path, args: argparse.Namespace, providers: list[str]) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "agent" / "workflow.py"),
        "--pdf",
        str(pdf_path),
        "--task",
        f"Stress audit case {case['case_id']}: generate a research hypothesis and verify citations",
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
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=args.timeout_seconds,
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
            "stderr_tail": f"Timed out after {args.timeout_seconds}s",
        }


def artifact_complete(run_dir: Path) -> dict[str, Any]:
    missing = [name for name in CORE_ARTIFACTS if not (run_dir / name).exists()]
    return {"complete": not missing, "missing": missing}


def audit_extraction(case: dict[str, Any], preflight: dict[str, Any], paper_summary: dict[str, Any] | None) -> dict[str, Any]:
    expected_keywords = [clean_text(item).lower() for item in case.get("expected_keywords", [])]
    extracted_keywords = [clean_text(item).lower() for item in (paper_summary or {}).get("keywords", [])]
    overlap = expected_overlap(expected_keywords, extracted_keywords)
    keyword_source = "missing"
    if extracted_keywords:
        keyword_source = "declared" if case.get("expected_keyword_source") == "declared" and overlap >= 0.5 else "inferred"
    abstract = clean_text((paper_summary or {}).get("abstract"))
    abstract_boundary_ok = bool(abstract) and "keywords:" not in abstract.lower() and "index terms" not in abstract.lower()
    failure_category = ""
    if preflight.get("readiness") == "risky":
        failure_category = "scanned_pdf_unreadable"
    elif expected_keywords and overlap < 0.5:
        failure_category = "layout_order_failure"
    elif not extracted_keywords:
        failure_category = "missing_keywords_fallback"
    elif not abstract_boundary_ok:
        failure_category = "abstract_boundary_failure"
    return {
        "case_id": case.get("case_id", ""),
        "discipline": case.get("discipline", ""),
        "layout_type": case.get("layout_type", ""),
        "expected_keyword_source": case.get("expected_keyword_source", ""),
        "keyword_source": keyword_source,
        "expected_keywords": "; ".join(expected_keywords),
        "extracted_keywords": "; ".join(extracted_keywords),
        "expected_keywords_overlap": round(overlap, 3),
        "readiness": preflight.get("readiness", ""),
        "expected_readiness": case.get("expected_readiness", ""),
        "readiness_match": preflight.get("readiness") == case.get("expected_readiness"),
        "title_present": bool(clean_text((paper_summary or {}).get("title"))),
        "abstract_chars": len(abstract),
        "abstract_boundary_ok": abstract_boundary_ok,
        "risk_flags": "; ".join(preflight.get("risk_flags", [])),
        "failure_category": failure_category,
    }


def audit_queries(case: dict[str, Any], queries_payload: dict[str, Any]) -> dict[str, Any]:
    queries = queries_payload.get("queries", [])
    query_text = " ".join(query.get("query", "") for query in queries).lower()
    expected = [clean_text(item).lower() for item in case.get("expected_keywords", [])]
    used = [keyword for keyword in expected if keyword and keyword in query_text]
    return {
        "case_id": case.get("case_id", ""),
        "query_count": len(queries),
        "followup_query_count": sum(1 for query in queries if query.get("query_stage") == "followup"),
        "expected_keyword_hits": len(used),
        "expected_keyword_hit_terms": "; ".join(used),
        "query_text_preview": tail(" | ".join(query.get("query", "") for query in queries), 700),
    }


def audit_retrieval(
    case: dict[str, Any],
    providers: list[str],
    literature: list[dict[str, Any]],
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sources = set(providers) | {clean_text(item.get("retrieval_source")) for item in literature if item.get("retrieval_source")}
    for provider in sorted(source for source in sources if source):
        provider_lit = [item for item in literature if item.get("retrieval_source") == provider or provider in item.get("merged_sources", [])]
        provider_calls = [call for call in tool_calls if clean_text(call.get("tool_name")).endswith("." + provider)]
        rows.append(
            {
                "case_id": case.get("case_id", ""),
                "provider": provider,
                "records": len(provider_lit),
                "abstract_available": sum(1 for item in provider_lit if item.get("abstract_available")),
                "selected_for_hypothesis": sum(1 for item in provider_lit if item.get("selected_for_hypothesis")),
                "tool_successes": sum(1 for call in provider_calls if call.get("status") == "success"),
                "tool_errors": sum(1 for call in provider_calls if call.get("status") == "error"),
                "error_preview": tail(" | ".join(clean_text(call.get("error")) for call in provider_calls if call.get("error")), 400),
            }
        )
    return rows


def expected_overlap(expected: list[str], extracted: list[str]) -> float:
    if not expected:
        return 1.0 if extracted else 0.0
    hits = 0
    extracted_text = " | ".join(extracted)
    for keyword in expected:
        if keyword in extracted_text:
            hits += 1
    return hits / max(1, len(expected))


def render_failures(failures: list[str]) -> str:
    if not failures:
        return "# Failure Cases\n\nNo stress-audit failures were recorded.\n"
    return "# Failure Cases\n\n" + "\n".join(failures)


def render_report(
    stress_rows: list[dict[str, Any]],
    extraction_rows: list[dict[str, Any]],
    retrieval_rows: list[dict[str, Any]],
    citation_rows: list[dict[str, Any]],
    online_rows: list[dict[str, Any]],
    providers: list[str],
) -> str:
    label_counts = Counter(row.get("color_label", "") for row in citation_rows)
    audit_counts = Counter(row.get("agreement_status", "") for row in online_rows)
    provider_errors = defaultdict(int)
    provider_successes = defaultdict(int)
    for row in retrieval_rows:
        provider_errors[row.get("provider", "")] += int(row.get("tool_errors", 0) or 0)
        provider_successes[row.get("provider", "")] += int(row.get("tool_successes", 0) or 0)
    disciplines = Counter(row.get("discipline", "") for row in stress_rows)
    layouts = Counter(row.get("layout_type", "") for row in stress_rows)
    failures = [row for row in extraction_rows if row.get("failure_category")]

    lines = [
        "# Stress Audit Report",
        "",
        f"Generated: {now_iso()}",
        "",
        "## Scope",
        "",
        f"- Cases run: {len(stress_rows)}",
        f"- Providers requested: {', '.join(providers)}",
        f"- Complete artifact sets: {sum(1 for row in stress_rows if str(row.get('artifact_complete')).lower() == 'true')} / {len(stress_rows)}",
        "",
        "## Case Distribution",
        "",
        f"- Disciplines: {dict(disciplines)}",
        f"- Layouts: {dict(layouts)}",
        "",
        "## Extraction Quality",
        "",
        f"- Extraction issues recorded: {len(failures)}",
        f"- Average expected keyword overlap: {average([float(row.get('expected_keywords_overlap') or 0) for row in extraction_rows]):.3f}",
        "",
        "## Provider Reliability",
        "",
    ]
    for provider in providers:
        lines.append(f"- {provider}: successes={provider_successes[provider]}, errors={provider_errors[provider]}")
    lines.extend(
        [
            "",
            "## Citation Labels",
            "",
            f"- Green: {label_counts.get('Green', 0)}",
            f"- Yellow: {label_counts.get('Yellow', 0)}",
            f"- Red: {label_counts.get('Red', 0)}",
            "",
            "## Independent Online Audit",
            "",
            f"- Rows audited: {len(online_rows)}",
            f"- Agreement status: {dict(audit_counts)}",
            "",
            "## Interpretation",
            "",
            "- Green requires existence, metadata match, and support evidence.",
            "- Yellow is expected when metadata exists but public abstracts/snippets are weak.",
            "- Red indicates missing, malformed, mismatched, or unsupported citations.",
            "- PDF extraction failures are separated from retrieval and verifier failures.",
            "",
            "## Important Files",
            "",
            "- `stress_summary.csv`",
            "- `extraction_audit.csv`",
            "- `retrieval_audit.csv`",
            "- `citation_label_audit.csv`",
            "- `online_verification_audit.csv`",
            "- `failure_cases.md`",
        ]
    )
    return "\n".join(lines)


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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


def tail(text: Any, limit: int = 1200) -> str:
    value = clean_text(text)
    return value if len(value) <= limit else value[-limit:]


if __name__ == "__main__":
    raise SystemExit(main())
