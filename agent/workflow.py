#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
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
from agent.run_logging import EvidenceStore, ToolCallLogger
from agent.utils import configure_utf8_stdio, timestamp_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PDF to hypothesis and citation verification workflow")
    parser.add_argument("--pdf", required=True, help="Input paper PDF path")
    parser.add_argument(
        "--task",
        default="Generate a new research hypothesis and verify citations",
        help="Free-form task description",
    )
    parser.add_argument("--max-pages", type=int, default=3, help="PDF pages to read")
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
    return parser.parse_args()


def main() -> int:
    configure_utf8_stdio()
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

    pdf_reader = PdfReaderTool(logger, evidence)
    query_planner = QueryPlanner(logger)
    searcher = LiteratureSearcher(logger, evidence)
    generator = HypothesisGenerator(logger, evidence)
    verifier = CitationVerifier(logger, evidence)
    evidence_tracer = EvidenceChainTracer(logger, evidence)
    writer = ReportWriter(logger, evidence)

    paper_summary = pdf_reader.read(pdf_path, max_pages=args.max_pages)
    print(f"[1/7] PDF parsed: {paper_summary.get('title')}")
    if args.live_demo and len(paper_summary.get("text_excerpt", "")) < 200:
        print("WARNING: live-demo PDF has very little extractable text. Explain this limitation if results are weak.")

    queries = query_planner.plan(paper_summary, max_queries=args.max_queries)
    print(f"[2/7] Initial search queries generated: {len(queries)}")

    providers = [provider.strip() for provider in args.providers.split(",") if provider.strip()]
    initial_literature = searcher.search(queries, providers, max_results_per_query=args.max_results_per_query)
    literature = initial_literature
    followup_queries = []
    if not args.disable_followup and args.max_followup_queries > 0:
        followup_queries = query_planner.plan_followup(
            paper_summary,
            queries,
            initial_literature,
            max_queries=args.max_followup_queries,
        )
        if followup_queries:
            followup_literature = searcher.search(
                followup_queries,
                providers,
                max_results_per_query=args.max_results_per_query,
            )
            literature = searcher.combine_records([initial_literature, followup_literature])
    queries = queries + followup_queries
    print(f"[3/7] Literature records retrieved: {len(literature)}")

    hypothesis_payload = generator.generate(
        paper_summary,
        literature,
        max_hypotheses=args.max_hypotheses,
        inject_bad_citation=args.inject_bad_citation,
    )
    print(f"[4/7] Research idea cards generated: {len(hypothesis_payload.get('hypotheses', []))}")

    verification_rows = verifier.verify(hypothesis_payload.get("claims", []))
    print(f"[5/7] Citations verified: {len(verification_rows)}")

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
    print("[6/7] Reports written")
    print("[7/7] Workflow complete")
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
    ]:
        print(f"  {run_dir / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
