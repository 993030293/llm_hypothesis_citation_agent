# Demo Runbook

This runbook is for the classroom demo. It emphasizes project-owned tools,
tool-call logs, retrieval outputs, and red/yellow/green citation verification.

## Create demo PDFs

```powershell
python scripts/create_demo_pdfs.py
```

## Success-style run

```powershell
python agent/workflow.py --pdf inputs/papers/success_demo.pdf --task "Generate a new research hypothesis and verify citations" --max-results-per-query 2
```

For a shorter run without second-stage retrieval:

```powershell
python agent/workflow.py --pdf inputs/papers/success_demo.pdf --task "Generate a new research hypothesis and verify citations" --max-results-per-query 2 --disable-followup
```

The default providers are Crossref and OpenAlex because they are free and stable
for live demos. To try additional APIs:

```powershell
python agent/workflow.py --pdf inputs/papers/success_demo.pdf --providers "crossref,openalex,semantic_scholar,arxiv" --max-results-per-query 2
```

Show these files from the generated `outputs/runs/<timestamp>/` directory:

- `tool_calls.jsonl`
- `retrieved_literature.jsonl`
- `generated_hypothesis.md`
- `citation_verification.csv`
- `final_report.md`

## Boundary run with a Red citation

```powershell
python agent/workflow.py --pdf inputs/papers/boundary_demo.pdf --task "Generate a boundary-case hypothesis and verify citations" --max-results-per-query 2 --inject-bad-citation
```

The injected citation is explicitly invalid and should be labeled Red. It is not
presented as a real DOI or real paper.

## QQ live-demo sequence

1. Trigger the workflow from QQ or from the terminal while sharing the output.
   ```powershell
   python agent/qq_demo_bridge.py --message "/hypothesis inputs/papers/success_demo.pdf"
   python agent/qq_demo_bridge.py --message "/hypothesis inputs/papers/boundary_demo.pdf --bad"
   ```
2. Open `tool_calls.jsonl` and point to each API/tool call.
3. Open `retrieved_literature.jsonl` and show normalized literature metadata.
4. Open `citation_verification.csv` and show Green/Yellow/Red labels.
5. Open `final_report.md` and explain how the table maps to the grading rubric.

Do not show only chat text. The grading evidence is the generated artifact set.
