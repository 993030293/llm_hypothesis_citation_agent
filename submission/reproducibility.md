# Reproducibility Guide

This guide describes how to reproduce the demo artifacts for the revised
Project A system.

## Environment

Run from:

```powershell
cd C:\Users\99303\git\llm_hypothesis_citation_agent
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

The default live-demo providers are Crossref and OpenAlex. They require network
access but no API key.

## Recreate demo PDFs

```powershell
python scripts/create_demo_pdfs.py
```

Expected files:

- `inputs/papers/success_demo.pdf`
- `inputs/papers/boundary_demo.pdf`

## Success case

```powershell
python agent/workflow.py --pdf inputs/papers/success_demo.pdf --task "Generate a new research hypothesis and verify citations"
```

Expected behavior:

- A new `outputs/runs/<timestamp>/` directory is created.
- The run contains all core artifacts, including `evidence_chain.csv`.
- `citation_verification.csv` contains at least one Green label.

Canonical prepared evidence:

- `submission/evidence/success_case/citation_verification.csv`
- `submission/evidence/success_case/evidence_chain.csv`
- `submission/evidence/success_case/tool_calls.jsonl`
- `submission/evidence/success_case/retrieved_literature.jsonl`
- `submission/evidence/success_case/final_report.md`

## Boundary case

```powershell
python agent/workflow.py --pdf inputs/papers/boundary_demo.pdf --task "Generate a boundary-case hypothesis and verify citations" --inject-bad-citation
```

Expected behavior:

- A new `outputs/runs/<timestamp>/` directory is created.
- `citation_verification.csv` contains at least one Red label.
- The Red row is the intentionally invalid boundary citation, not a fabricated
  real paper.

Canonical prepared evidence:

- `submission/evidence/boundary_case/citation_verification.csv`
- `submission/evidence/boundary_case/evidence_chain.csv`
- `submission/evidence/boundary_case/tool_calls.jsonl`
- `submission/evidence/boundary_case/retrieved_literature.jsonl`
- `submission/evidence/boundary_case/final_report.md`

## QQ command adapter

Terminal adapter commands for classroom rehearsal:

```powershell
python agent/qq_demo_bridge.py --message "/hypothesis inputs/papers/success_demo.pdf"
python agent/qq_demo_bridge.py --message "/hypothesis inputs/papers/boundary_demo.pdf --bad"
```

The adapter prints:

- parsed workflow command;
- workflow output;
- run directory;
- Green/Yellow/Red count summary;
- artifact paths to show.

If a real QQ/WeChat bot is not connected, describe this honestly as a local
QQ-style command adapter. Do not present terminal output as a real chat
screenshot.

## Teacher-supplied PDF live test

Before running an unknown PDF from the teacher, preflight it:

```powershell
python scripts/live_pdf_preflight.py "C:\path\to\teacher.pdf"
```

Then run the time-bounded live mode:

```powershell
python agent/workflow.py --pdf "C:\path\to\teacher.pdf" --task "Teacher-supplied live PDF: generate a research hypothesis and verify citations" --live-demo
```

If the PDF has too little extractable text, the correct response is to explain
the limitation and show the prepared canonical evidence, not to fabricate a
successful run.

## Core artifact set

Every complete run should contain:

- `input_task.md`
- `paper_summary.json`
- `search_queries.json`
- `retrieved_literature.jsonl`
- `generated_hypothesis.md`
- `citation_verification.csv`
- `evidence_chain.csv`
- `evidence_chain.md`
- `final_report.md`
- `tool_calls.jsonl`
- `evidence_items.jsonl`

## Validation

Run the test suite:

```powershell
python -m pytest -q
```

Manual validation before presentation:

- Open `tool_calls.jsonl` and confirm API/tool calls are logged.
- Open `retrieved_literature.jsonl` and confirm records are real provider
  responses normalized by project code.
- Open `citation_verification.csv` and confirm Green/Yellow/Red labels have
  reasons and evidence IDs.
- Open `evidence_chain.csv` and confirm every claim links to evidence IDs and
  tool-call IDs.
- Open `final_report.md` and confirm the report explains the labels.
