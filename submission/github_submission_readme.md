# GitHub Submission Checklist

This repository is the complete implementation package for the course Project A
submission: a DeepScientist-based citation evidence-chain audit agent.

## 1. Source Code And Experiment Scripts

- Core audit modules: `agent/`
  - PDF parsing, query planning, literature retrieval, citation verification,
    evidence-chain writing, report generation, and DeepScientist adapter.
- Official DeepScientist automation: `scripts/run_official_ds_case.py`
- 20-paper command-line campaign: `scripts/deepscientist_20x_campaign.py`
- Paper downloader / manifest support: `scripts/download_deepscientist_20_papers.py`
- Multi-reviewer entry: `scripts/run_multi_reviewer.py`
- QQ live demo bridge: `qqbot/`

## 2. Key Configuration Files

- Python dependencies: `requirements.txt`
- Verifier parameters: `configs/verifier_params.json`
- DeepScientist skill contracts:
  - `integrations/deepscientist/citation-hypothesis-claims/SKILL.md`
  - `integrations/deepscientist/citation-evidence-audit/SKILL.md`
- Git ignore policy for generated runs and large paper PDFs: `.gitignore`

## 3. Installation And Startup

Recommended setup:

```powershell
cd C:\Users\99303\git\llm_hypothesis_citation_agent
pip install -r requirements.txt
python scripts/setup_path2_claude.py --force-skill
ds --runner claude
```

Run one official DeepScientist case with the required 30-minute official-agent
limit:

```powershell
python scripts/run_official_ds_case.py `
  --case-id demo_clip `
  --pdf-path-or-url "C:\path\paper.pdf" `
  --timeout-seconds 1800
```

Start the QQ demo bot:

```powershell
start_qqbot.bat
```

Restart the QQ demo bot after code changes:

```powershell
restart_qqbot.bat
```

## 4. Test Data And Test Samples

- Built-in demo PDFs: `inputs/papers/`
- 20-paper campaign manifest: `inputs/deepscientist_20_cases/manifest.json`
- Download audit for campaign papers:
  `inputs/deepscientist_20_cases/download_audit.csv`

Large downloaded PDFs are intentionally ignored by Git and can be restored with:

```powershell
python scripts/download_deepscientist_20_papers.py
```

## 5. Run Logs And Reproducible Outputs

Each official case writes a complete run directory under:

```text
outputs/deepscientist_20x_campaigns/<run_id>/cases/<case_id>/
```

Important artifacts include:

- `deepscientist/citation_audit_claims.json`
- `citation_audit/citation_verification.csv`
- `citation_audit/evidence_chain.csv`
- `citation_audit/tool_calls.jsonl`
- `citation_audit/evidence_items.jsonl`
- `multi_review/multi_review_report.md`
- `final_case_report.md`

Generated run directories are not committed because they can be large and
machine-specific. Curated reports, screenshots, poster, and presentation files
are kept under `submission/`.

## 6. Minimal Runnable Demo For Presentation

QQ command examples:

```text
/local "C:\path\paper.pdf"
/official "C:\path\paper.pdf"
```

The bot replies with:

- accepted command and progress heartbeat;
- run directory;
- Green / Yellow / Red counts;
- reviewer decision when available;
- final `DONE` or `FAILED` message;
- key artifact paths.

## 7. What We Modified Or Added On Top Of DeepScientist

DeepScientist is used as the base research agent. This project adds the
verifiable citation-audit layer:

- self-written DeepScientist skills for claim export and audit contract;
- deterministic verifier for existence, metadata, and support checks;
- public scholarly API wrappers for Crossref, OpenAlex, Semantic Scholar, and
  arXiv;
- evidence IDs and tool-call logs for reproducibility;
- QQ live interaction layer;
- multi-reviewer scoring that cannot override deterministic Green / Yellow /
  Red labels;
- memory records for prior citation, provider, reviewer, and failure patterns.

API keys are read from environment variables only and must not be committed.
