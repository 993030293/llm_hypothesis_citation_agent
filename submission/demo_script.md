# Classroom Demo Script

Target timing: 10 minutes demo plus 5 minutes Q&A.

## 0:00-1:00 Problem and direction

State the chosen direction:

> Project A, revised direction: a DeepScientist-style research agent that reads
> article PDFs, searches related literature, proposes research hypotheses, and
> verifies whether its citations exist and support the generated claims.

Key problem:

> LLM research agents can produce plausible ideas with weak or fabricated
> citations. This system focuses on auditable citation verification.

## 1:00-2:30 System architecture

Show:

- `README.md`
- `docs/design_notes.md`
- `submission/poster/poster_120x80.pdf`

Explain pipeline:

`PDF -> summary -> query planner -> literature search -> hypothesis card -> citation verifier -> report`

Emphasize self-implemented tools:

- PDF reader;
- query planner;
- Crossref/OpenAlex search wrappers;
- evidence store and tool logger;
- hypothesis generator;
- citation verifier;
- report writer;
- QQ command adapter.

## 2:30-4:30 Success case interaction

Run or show recorded QQ-style command:

```powershell
python agent/qq_demo_bridge.py --message "/hypothesis inputs/papers/success_demo.pdf"
```

For a real QQ interaction through NapCat, send this message to the bot account:

```text
/hypothesis inputs/papers/success_demo.pdf
```

If running live, show the printed run directory and label counts.

If using prepared evidence, open:

- `submission/evidence/success_case/tool_calls.jsonl`
- `submission/evidence/success_case/retrieved_literature.jsonl`
- `submission/evidence/success_case/citation_verification.csv`
- `submission/evidence/success_case/final_report.md`

Explain one Green row.

## 4:30-6:30 Verification table explanation

Open `citation_verification.csv`.

Explain columns:

- `exists_status`: whether public records found the work;
- `metadata_match_status`: title, author, year, DOI agreement;
- `support_status`: whether abstract/snippet supports the claim;
- `color_label`: Green, Yellow, Red;
- `reason`: human-readable explanation;
- `evidence_id`: link back to evidence logging.

Emphasize:

> Green requires existence, metadata match, and concrete support. Metadata
> alone is not enough.

## 6:30-8:00 Boundary case

Run or show recorded QQ-style command:

```powershell
python agent/qq_demo_bridge.py --message "/hypothesis inputs/papers/boundary_demo.pdf --bad"
```

For a real QQ interaction through NapCat, send:

```text
/hypothesis inputs/papers/boundary_demo.pdf --bad
```

Open:

- `submission/evidence/boundary_case/citation_verification.csv`
- `submission/failure_case_explanation.md`

Explain:

- Yellow row: citation exists, support uncertain.
- Red row: intentionally invalid DOI, rejected by verifier.

## 8:00-9:00 Reproducibility and logs

Show:

- `submission/reproducibility.md`
- `submission/evidence_manifest.json`
- `tool_calls.jsonl`
- `retrieved_literature.jsonl`

Explain:

> The system is not a prompt-only demo. Every tool call and retrieval result is
> written to disk for inspection.

## 9:00-10:00 Limitations and backup plan

Limitations:

- public APIs may not expose abstracts;
- support checking is conservative;
- cross-disciplinary hypotheses may need full-text human review;
- live APIs can fail because of network or provider rate limits.

Backup plan:

- If live run fails, show canonical evidence under `submission/evidence/`.
- Show screenshots and recordings collected in `submission/screenshots/` and
  `submission/recordings/`.
- Explain the failure cause and point to the reproducible command.

If the teacher provides a new PDF live:

```powershell
python scripts/live_pdf_preflight.py "C:\path\to\teacher.pdf"
python agent/workflow.py --pdf "C:\path\to\teacher.pdf" --task "Teacher-supplied live PDF: generate a research hypothesis and verify citations" --live-demo
```

If preflight reports `risky`, explain that the PDF has too little extractable
text or appears scanned, then switch to the prepared canonical evidence.

## Q&A preparation

Likely question: why is this not just prompt engineering?

Answer:

> The project implements local tools for PDF parsing, query planning, API
> retrieval, evidence storage, citation verification, and report writing. The
> generated answer is only one artifact; the grading evidence is the logged
> tool chain.

Likely question: why does Yellow count as useful?

Answer:

> Yellow is an honest uncertainty label. It prevents the system from claiming
> that a citation supports a hypothesis when only metadata or a weak snippet is
> available.

Likely question: why is Red valid if injected?

Answer:

> The Red citation is a boundary test. It is explicitly marked as intentionally
> invalid and proves that the verifier rejects malformed or nonexistent
> citations instead of accepting all generated references.
