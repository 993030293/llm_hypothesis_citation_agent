# Stress Audit

This project includes a non-lightweight stress audit for PDF extraction,
literature retrieval, citation verification, and independent online review.

## Create stress cases

```powershell
python scripts/create_stress_cases.py
```

This creates `inputs/stress_cases/` with at least eight PDF layout/source cases.
Synthetic cases are clearly marked as parser stress fixtures and are not
presented as real published papers. Their purpose is to test PDF layout
behavior, while retrieved and verified citations still come from public APIs.

## Full non-lightweight audit

```powershell
python scripts/stress_audit.py --case-dir inputs/stress_cases --providers "crossref,openalex,semantic_scholar,arxiv"
```

Default behavior:

- runs full workflow, not `--live-demo`;
- reads multiple PDF pages;
- uses seed and follow-up queries;
- queries all requested providers;
- verifies citations;
- runs independent online audit for citation rows;
- copies the final audit package to `submission/stress_audit/`.

## Classroom-safe smoke audit

Use this before a demo to verify that the stress-audit machinery still works
without waiting for all cases and providers:

```powershell
python scripts/stress_audit.py --case-id keywords_before_abstract --providers crossref --max-pages 2 --max-queries 1 --max-followup-queries 0 --max-results-per-query 1 --timeout-seconds 180
```

## Output files

Each run writes to:

```text
outputs/stress_audits/<timestamp>/
```

Core files:

- `stress_summary.csv`
- `case_manifest_resolved.json`
- `extraction_audit.csv`
- `query_audit.csv`
- `retrieval_audit.csv`
- `citation_label_audit.csv`
- `online_verification_audit.csv`
- `failure_cases.md`
- `stress_report.md`

Each case also has a workflow run directory under:

```text
outputs/stress_audits/<timestamp>/runs/<case_id>/
```

Those case run directories contain the normal nine workflow artifacts, including
`tool_calls.jsonl`, `retrieved_literature.jsonl`, `citation_verification.csv`,
and `final_report.md`.

## How to explain it

The stress audit separates three failure modes:

- PDF extraction/layout problems, recorded in `extraction_audit.csv`;
- retrieval/API problems, recorded in `retrieval_audit.csv` and each case's
  `tool_calls.jsonl`;
- citation label disagreement, recorded in `online_verification_audit.csv`.

The online audit is a second opinion. It does not rewrite the original
`citation_verification.csv`.
