# DeepScientist-style Hypothesis and Citation Verification Agent

## Problem

Large language model research agents can generate plausible research ideas, but
their citations may be wrong, weak, or fabricated. The project goal is to make
PDF-based hypothesis generation auditable through literature retrieval and
Green/Yellow/Red citation verification.

## Pipeline

PDF paper input -> paper summary -> two-stage query planning -> Crossref and
OpenAlex retrieval -> structured research idea cards -> citation verification
-> final report and CSV table.

## Self-implemented tool chain

- PDF reader: extracts title, abstract, keywords, and research problem.
- Query planner: creates seed and follow-up queries.
- Literature search: calls public APIs and normalizes metadata.
- Evidence store: records retrieved papers and tool calls.
- Hypothesis generator: creates conservative, citation-backed idea cards.
- Citation verifier: checks existence, metadata match, and claim support.
- QQ command adapter: triggers the workflow and reports artifact paths.

## Verification labels

- Green: paper exists, metadata matches, and abstract/snippet supports the
  claim.
- Yellow: paper exists, but support is weak, partial, abstract-only, or needs
  human review.
- Red: paper is missing, metadata is wrong, DOI is invalid, or the paper cannot
  support the claim.

## Demo evidence

Success case:

- Input: `inputs/papers/success_demo.pdf`
- Evidence: `submission/evidence/success_case/`
- Observed labels: Green 3, Yellow 1, Red 0

Boundary case:

- Input: `inputs/papers/boundary_demo.pdf`
- Evidence: `submission/evidence/boundary_case/`
- Observed labels: Green 0, Yellow 1, Red 1

## Reproducibility

Core artifacts are generated for every run:

- `tool_calls.jsonl`
- `retrieved_literature.jsonl`
- `generated_hypothesis.md`
- `citation_verification.csv`
- `final_report.md`

Run:

```powershell
python agent/workflow.py --pdf inputs/papers/success_demo.pdf --task "Generate a new research hypothesis and verify citations"
python agent/workflow.py --pdf inputs/papers/boundary_demo.pdf --task "Generate a boundary-case hypothesis and verify citations" --inject-bad-citation
```

## Limitations

The verifier is conservative. Public APIs may lack abstracts, so some existing
citations must be labeled Yellow. Full-text human review is still needed for
high-stakes scientific claims.
