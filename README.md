# LLM Hypothesis Citation Agent

This workspace is for the updated LLM course Project A direction.

## Goal

Build a DeepScientist-style research Agent that accepts article PDFs from
different disciplines, searches for related literature, generates a new research
idea or hypothesis, and checks whether the cited literature is correct.

## Required output behavior

- Green: the cited literature exists and supports the claim.
- Yellow: the cited literature exists but support is uncertain or only partial.
- Red: the citation is wrong, missing, or does not support the claim.

## Planned structure

- `agent/`: PDF parsing, literature search, hypothesis generation, citation
  verification, and report writing code.
- `inputs/papers/`: local PDFs used for testing and classroom demonstration.
- `outputs/`: generated run directories, evidence tables, reports, and logs.
- `docs/`: design notes, presentation runbook, and grading alignment.
- `tests/`: smoke tests and citation-checking test cases.
- `submission/`: final course report, evidence PDF, screenshots, and zip package.

## Relationship to finalproj

The existing `finalproj` repository remains useful as a source of evidence-chain
tracking patterns. This new workspace focuses on the revised requirement:
article PDF input, literature lookup, hypothesis generation, and citation
verification with red/yellow/green labels.

## Quick start

Install dependencies if needed:

```powershell
pip install -r requirements.txt
```

Create local demo PDFs:

```powershell
python scripts/create_demo_pdfs.py
```

Run the workflow:

```powershell
python agent/workflow.py --pdf inputs/papers/success_demo.pdf --task "Generate a new research hypothesis and verify citations"
```

The default live-demo providers are Crossref and OpenAlex. Optional providers
can be enabled with `--providers "crossref,openalex,semantic_scholar,arxiv"`.
The workflow now performs two-stage retrieval by default: initial PDF-derived
queries, then follow-up method/application/limitation/review queries derived
from the first retrieval pass. Use `--disable-followup` for a minimal run.

Each run writes a complete artifact set to `outputs/runs/<timestamp>/`:

- `input_task.md`
- `paper_summary.json`
- `search_queries.json`
- `retrieved_literature.jsonl`
- `generated_hypothesis.md`
- `citation_verification.csv`
- `final_report.md`
- `tool_calls.jsonl`
- `evidence_items.jsonl`

For a boundary demonstration with one explicitly invalid citation:

```powershell
python agent/workflow.py --pdf inputs/papers/boundary_demo.pdf --task "Generate a boundary-case hypothesis and verify citations" --inject-bad-citation
```

QQ-style demo adapter:

```powershell
python agent/qq_demo_bridge.py --message "/hypothesis inputs/papers/success_demo.pdf"
python agent/qq_demo_bridge.py --message "/hypothesis inputs/papers/boundary_demo.pdf --bad"
```

Demo case metadata is stored in `inputs/cases/`.

## Real QQ / NapCat interaction

The project also includes a NapCat/OneBot QQ bot entrypoint:

```powershell
python qqbot\main.py --debug --port 3002
```

Configure NapCat reverse WebSocket to:

```text
ws://127.0.0.1:3002
```

This reuses the already configured NapCat setup in
`C:\Users\99303\git\qqbot-agent`. Do not run the old `qqbot-agent` Python bot
at the same time, because it also listens on port `3002`.

Then send QQ messages such as:

```text
/hypothesis inputs/papers/success_demo.pdf
/hypothesis inputs/papers/boundary_demo.pdf --bad
/preflight inputs/papers/teacher_live.pdf
/hypothesis inputs/papers/teacher_live.pdf --live
```

See `docs/qq_live_integration.md` for the full setup and screenshot checklist.

## Stress audit

Generate stress-test PDF cases:

```powershell
python scripts/create_stress_cases.py
```

Run the non-lightweight batch audit with independent online citation review:

```powershell
python scripts/stress_audit.py --case-dir inputs/stress_cases --providers "crossref,openalex,semantic_scholar,arxiv"
```

Outputs are written to `outputs/stress_audits/<timestamp>/` and copied to
`submission/stress_audit/` by default. See `docs/stress_audit.md`.

## Teacher-supplied live PDF

If the teacher provides a new PDF during the presentation, preflight it before
running the full workflow:

```powershell
python scripts/live_pdf_preflight.py "C:\path\to\teacher.pdf"
```

If the preflight says `ready` or `usable_with_caution`, run the time-bounded
live mode:

```powershell
python agent/workflow.py --pdf "C:\path\to\teacher.pdf" --task "Teacher-supplied live PDF: generate a research hypothesis and verify citations" --live-demo
```

The QQ-style adapter also supports live mode:

```powershell
python agent/qq_demo_bridge.py --message "/hypothesis C:\path\to\teacher.pdf --live"
```

If the preflight says `risky`, explain that the PDF is likely scanned or has too
little extractable text, then show the prepared logs in `submission/evidence/`.
The full two-stage retrieval workflow remains available for prepared demo runs;
`--live-demo` intentionally prioritizes speed and predictable classroom timing.

## Submission package

Course-facing evidence is organized under `submission/`:

- `submission/evidence/success_case/`: canonical successful run artifacts.
- `submission/evidence/boundary_case/`: canonical boundary run artifacts.
- `submission/reproducibility.md`: commands and validation steps.
- `submission/grading_checklist.md`: rubric-to-evidence mapping.
- `submission/demo_script.md`: 10-minute demo flow and backup plan.
- `submission/poster/poster_120x80.pdf`: printable 120 cm x 80 cm poster.
- `docs/qq_live_integration.md`: real NapCat/OneBot QQ setup.
- `docs/stress_audit.md`: non-lightweight stress audit and online review guide.

Real QQ/WeChat screenshots and recordings must be captured before final
presentation and stored in `submission/screenshots/` and
`submission/recordings/`. Do not fabricate chat evidence or retrieval logs.
