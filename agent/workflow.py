#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.citation_verifier import CitationVerifier
from agent.evidence_chain_tracer import EvidenceChainTracer
from agent.hypothesis_generator import HypothesisGenerator
from agent.literature_search import LiteratureSearcher
from agent.pdf_reader import PdfReaderTool
from agent.query_planner import QueryPlanner
from agent.report_writer import ReportWriter
from agent.research_memory import ResearchMemory
from agent.run_logging import EvidenceStore, ToolCallLogger
from agent.utils import configure_utf8_stdio, timestamp_id, write_json


def _has_api_key(env_name: str) -> bool:
    return bool(os.environ.get(env_name, "").strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PDF to hypothesis and citation verification workflow")
    parser.add_argument("--pdf", required=True, help="Input paper PDF path")
    parser.add_argument(
        "--task",
        default="Generate a new research hypothesis and verify citations",
        help="Free-form task description",
    )
    parser.add_argument("--max-pages", type=int, default=999, help="PDF pages to read (default: all pages)")
    parser.add_argument("--max-queries", type=int, default=5, help="Maximum literature search queries")
    parser.add_argument("--max-followup-queries", type=int, default=4, help="Maximum second-stage follow-up queries")
    parser.add_argument("--disable-followup", action="store_true", help="Disable second-stage follow-up query retrieval")
    parser.add_argument("--max-results-per-query", type=int, default=3, help="Results per provider/query")
    parser.add_argument(
        "--live-demo",
        action="store_true",
        help="Use time-bounded settings for a teacher-supplied live PDF.",
    )
    parser.add_argument(
        "--providers",
        default="crossref,openalex",
        help="Comma-separated providers: crossref, openalex, semantic_scholar, arxiv",
    )
    parser.add_argument("--output-root", default=str(ROOT / "outputs" / "runs"), help="Output run root")
    parser.add_argument("--run-dir", default=None, help="Explicit run directory")
    parser.add_argument("--max-hypotheses", type=int, default=3)
    parser.add_argument(
        "--inject-bad-citation",
        action="store_true",
        help="Add an explicitly invalid boundary-case citation to demonstrate Red labeling.",
    )
    parser.add_argument(
        "--require-llm-agent",
        action="store_true",
        help="Fail instead of falling back to the deterministic local generator when DEEPSEEK_API_KEY is missing.",
    )
    return parser.parse_args()


def main() -> int:
    configure_utf8_stdio()
    start_time = time.perf_counter()
    args = parse_args()
    if args.live_demo:
        args.max_pages = min(args.max_pages, 2)
        args.max_queries = min(args.max_queries, 1)
        args.max_followup_queries = min(args.max_followup_queries, 0)
        args.max_results_per_query = min(args.max_results_per_query, 1)
        args.max_hypotheses = min(args.max_hypotheses, 1)
    pdf_path = Path(args.pdf)
    if not pdf_path.is_absolute():
        pdf_path = (Path.cwd() / pdf_path).resolve()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    run_dir = Path(args.run_dir).resolve() if args.run_dir else Path(args.output_root) / timestamp_id()
    run_dir.mkdir(parents=True, exist_ok=True)

    logger = ToolCallLogger(run_dir)
    evidence = EvidenceStore(run_dir)

    print("=" * 72)
    print("LLM Hypothesis Citation Agent")
    print("=" * 72)
    print(f"PDF:      {pdf_path}")
    print(f"Task:     {args.task}")
    print(f"Run dir:  {run_dir}")
    if args.live_demo:
        print("Mode:     live-demo defaults (2 pages, 1 seed query, no follow-up, 1 result/provider/query)")
    print("=" * 72)

    timings = {}

    pdf_reader = PdfReaderTool(logger, evidence)
    query_planner = QueryPlanner(logger)
    searcher = LiteratureSearcher(logger, evidence)
    generator = HypothesisGenerator(logger, evidence, searcher=searcher)
    verifier = CitationVerifier(logger, evidence)
    evidence_tracer = EvidenceChainTracer(logger, evidence)
    writer = ReportWriter(logger, evidence)

    t0 = time.perf_counter()
    paper_summary = pdf_reader.read(pdf_path, max_pages=args.max_pages)
    timings["1_pdf_parse"] = round(time.perf_counter() - t0, 2)
    print(f"[1/7] PDF parsed: {paper_summary.get('title')} ({timings['1_pdf_parse']}s)")
    if args.live_demo and len(paper_summary.get("text_excerpt", "")) < 200:
        print("WARNING: live-demo PDF has very little extractable text. Explain this limitation if results are weak.")

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]

    # Prefer the LLM agent when configured. For classroom/local demos, keep a
    # deterministic path available so /local can run without paid API keys.
    t0 = time.perf_counter()
    if _has_api_key("DEEPSEEK_API_KEY"):
        generation_mode = "llm_agent"
        print("[2/7] LLM agent is thinking and searching literature based on the paper...")
        hypothesis_payload = generator.generate_with_agent(
            paper_summary,
            max_hypotheses=args.max_hypotheses,
            inject_bad_citation=args.inject_bad_citation,
            providers=providers,
        )
    else:
        if args.require_llm_agent:
            print(
                "ERROR: DEEPSEEK_API_KEY is required when --require-llm-agent is set. "
                "Unset --require-llm-agent or provide the environment variable.",
                file=sys.stderr,
            )
            return 1
        generation_mode = "deterministic_local"
        print("[2/7] DEEPSEEK_API_KEY not set; using deterministic local generator.")
        queries = query_planner.plan(paper_summary, max_queries=args.max_queries)
        literature = searcher.search(queries, providers, max_results_per_query=args.max_results_per_query)
        if not args.disable_followup and args.max_followup_queries > 0:
            followups = query_planner.plan_followup(
                paper_summary,
                queries,
                literature,
                max_queries=args.max_followup_queries,
            )
            if followups:
                followup_literature = searcher.search(
                    followups,
                    providers,
                    max_results_per_query=args.max_results_per_query,
                )
                literature = searcher.combine_records([literature, followup_literature])
                queries.extend(followups)
        hypothesis_payload = generator.generate(
            paper_summary,
            literature,
            max_hypotheses=args.max_hypotheses,
            inject_bad_citation=args.inject_bad_citation,
        )
        hypothesis_payload["literature"] = literature
        hypothesis_payload["queries"] = queries
    timings["2_3_search_generate"] = round(time.perf_counter() - t0, 2)
    literature = hypothesis_payload.get("literature", [])
    queries = hypothesis_payload.get("queries", [])
    print(f"[3/7] {generation_mode} retrieved {len(literature)} records and finalized ideas.")

    print(f"[4/7] Research idea cards generated: {len(hypothesis_payload.get('hypotheses', []))}")

    t0 = time.perf_counter()
    verification_rows = verifier.verify(hypothesis_payload.get("claims", []))
    timings["5_citation_verify"] = round(time.perf_counter() - t0, 2)
    print(f"[5/7] Citations verified: {len(verification_rows)} ({timings['5_citation_verify']}s)")

    t0 = time.perf_counter()
    evidence_tracer.trace_and_write(
        run_dir,
        hypothesis_payload=hypothesis_payload,
        literature=literature,
        verification_rows=verification_rows,
    )

    writer.write_all(
        run_dir,
        task=args.task,
        pdf_path=pdf_path,
        paper_summary=paper_summary,
        queries=queries,
        literature=literature,
        hypothesis_payload=hypothesis_payload,
        verification_rows=verification_rows,
    )
    timings["6_7_report"] = round(time.perf_counter() - t0, 2)
    total_time = round(time.perf_counter() - start_time, 2)
    timings["total"] = total_time

    write_json(run_dir / "workflow_timing.json", {"generation_mode": generation_mode, "timings_seconds": timings})
    try:
        memory_status = {
            "case_id": run_dir.name,
            "run_id": run_dir.name,
            "case_dir": str(run_dir),
            "pdf_path_or_url": str(pdf_path),
            "quest_root": "",
            "final_status": "success",
            "claims_source": "local_workflow",
        }
        memory_updates = ResearchMemory().update_from_artifacts(
            case_dir=run_dir,
            status=memory_status,
            citation_audit_dir=run_dir,
            multi_review_dir=None,
            updates_path=run_dir / "memory_updates.jsonl",
        )
        write_json(
            run_dir / "memory_update_summary.json",
            {
                "memory_dir": str(ROOT / "outputs" / "memory"),
                "updates": len(memory_updates),
                "case_id": memory_status["case_id"],
                "run_id": memory_status["run_id"],
            },
        )
    except Exception as exc:
        write_json(
            run_dir / "memory_update_summary.json",
            {
                "memory_status": "failed",
                "error": str(exc),
            },
        )

    print(f"[6/7] Reports written ({timings['6_7_report']}s)")
    print(f"[7/7] Workflow complete — total time: {total_time}s")
    print("")
    print("Outputs:")
    for name in [
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
        "workflow_timing.json",
    ]:
        print(f"  {run_dir / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
