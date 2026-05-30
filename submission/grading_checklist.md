# Rubric Alignment Checklist

## 1. Problem definition and system understanding, 15 points

Evidence to show:

- `README.md`
- `docs/design_notes.md`
- `submission/poster/poster_120x80.pdf`

Talking points:

- The system addresses revised Project A: PDF input, related-literature search,
  research idea generation, and citation verification.
- The key risk is that LLM-generated research ideas may cite nonexistent or
  weakly supporting papers.
- The system follows a DeepScientist-style pipeline but implements its own
  local tools for parsing, retrieval, logging, generation, and verification.

## 2. Function implementation or experiment design, 25 points

Evidence to show:

- `agent/pdf_reader.py`
- `agent/query_planner.py`
- `agent/literature_search.py`
- `agent/hypothesis_generator.py`
- `agent/citation_verifier.py`
- `agent/report_writer.py`
- `agent/qq_demo_bridge.py`

Talking points:

- The system is not a prompt-only agent.
- Retrieval uses project-owned wrappers for Crossref and OpenAlex.
- Search is two-stage: initial queries from the PDF, then follow-up queries
  derived from the first retrieval pass.
- Verification has three layers: existence, metadata match, and support check.
- Every major step writes `tool_calls.jsonl` and evidence records.

## 3. Result evidence and reproducibility, 15 points

Evidence to show:

- `submission/reproducibility.md`
- `submission/stress_audit/stress_report.md`
- `submission/evidence/success_case/tool_calls.jsonl`
- `submission/evidence/success_case/retrieved_literature.jsonl`
- `submission/evidence/success_case/citation_verification.csv`
- `submission/evidence/boundary_case/citation_verification.csv`

Talking points:

- The prepared evidence comes from real workflow runs.
- The commands and expected artifact set are documented.
- The stress audit tests multiple PDF layouts and independently re-checks
  citation labels online.
- The teacher can rerun the system from the repository root.
- If live APIs fail, the prepared logs and reports still show how the system
  behaved in a completed run.

## 4. Analysis quality and failure cases, 15 points

Evidence to show:

- `docs/failure_analysis.md`
- `submission/failure_case_explanation.md`
- `submission/evidence/boundary_case/citation_verification.csv`

Talking points:

- Yellow is not treated as success: it means the paper exists but support is
  uncertain or incomplete.
- Red is produced when the cited work cannot be found, metadata is wrong, or
  the citation cannot support the claim.
- The system is conservative: uncertain support stays Yellow instead of being
  promoted to Green.

## 5. Live demo and Q&A, 30 points

Evidence to show:

- `submission/demo_script.md`
- `submission/teacher_live_pdf_protocol.md`
- `docs/qq_live_integration.md`
- real files added under `submission/screenshots/`
- real files added under `submission/recordings/`
- canonical evidence under `submission/evidence/`

Talking points:

- Start from the QQ/WeChat command or the local QQ command adapter.
- Show the run directory and label counts.
- If the teacher provides a new PDF, run `scripts/live_pdf_preflight.py` first,
  then `workflow.py --live-demo`.
- Open `tool_calls.jsonl`, `retrieved_literature.jsonl`,
  `citation_verification.csv`, and `final_report.md`.
- Demonstrate both success and boundary cases.

## Direct deduction risks to avoid

- Do not fabricate QQ/WeChat screenshots, DOI records, retrieval logs, or
  experimental outputs.
- Do not claim the system is fully LLM-autonomous if the demo uses deterministic
  local tools and conservative templates.
- Do not show only chat output; always show backend artifacts.
- Do not claim a citation supports a claim when only metadata or title overlap
  is available.
