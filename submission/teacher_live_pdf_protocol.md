# Teacher-Supplied Live PDF Protocol

Use this protocol if the teacher asks the system to process a new PDF during
the presentation.

## Step 1: Save the PDF

Save the file to a simple path, for example:

```powershell
C:\Users\99303\git\llm_hypothesis_citation_agent\inputs\papers\teacher_live.pdf
```

Avoid spaces or Chinese punctuation in the filename during the live demo if
possible.

## Step 2: Preflight without API calls

```powershell
python scripts/live_pdf_preflight.py inputs/papers/teacher_live.pdf
```

Interpretation:

- `ready`: safe to run live.
- `usable_with_caution`: run live, but explain that labels may be Yellow if
  public APIs expose limited abstracts.
- `risky`: likely scanned, too short, or metadata-poor. Do not force a weak
  live claim. Show prepared evidence and explain the limitation.

## Step 3: Run live-demo mode

```powershell
python agent/workflow.py --pdf inputs/papers/teacher_live.pdf --task "Teacher-supplied live PDF: generate a research hypothesis and verify citations" --live-demo
```

Live-demo mode limits runtime:

- reads at most 2 pages;
- uses at most 1 seed query;
- disables follow-up queries;
- retrieves at most 1 result per provider/query;
- generates at most 1 hypothesis card.

## Step 4: Show artifacts

Open the generated `outputs/runs/<timestamp>/` directory and show:

- `tool_calls.jsonl`
- `retrieved_literature.jsonl`
- `citation_verification.csv`
- `final_report.md`

Explain that random PDFs can produce more Yellow labels because public APIs may
not expose full abstracts.

## Step 5: Fallback if live run fails

If the PDF is scanned, the network fails, or the API response is too slow:

1. Keep the terminal error visible.
2. Show `tool_calls.jsonl` if a run directory was created.
3. Explain the failure reason precisely.
4. Switch to canonical evidence:
   - `submission/evidence/success_case/`
   - `submission/evidence/boundary_case/`

Do not fabricate a successful live result.
