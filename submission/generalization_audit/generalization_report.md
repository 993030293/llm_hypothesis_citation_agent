# Cross-Domain Generalization Audit Report

Generated: 2026-05-31T18:05:07+00:00

## Scope

- Cases configured: 15
- Completed workflow cases: 15
- Distinct fields: 15
- Providers requested: crossref, openalex, semantic_scholar, arxiv
- DeepScientist adapter completed: 15

## Label Distribution

- Green: 52
- Yellow: 15
- Red: 24

## Domain Coverage

| Field | Cases | Completed | Green | Yellow | Red |
|---|---:|---:|---:|---:|---:|
| Boundary Case | 1 | 1 | 4 | 1 | 2 |
| Climate / Remote Sensing | 1 | 1 | 3 | 3 | 0 |
| Education | 1 | 1 | 5 | 1 | 0 |
| Education / HCI | 1 | 1 | 3 | 0 | 3 |
| Education / Social Science | 1 | 1 | 5 | 1 | 0 |
| Finance / Simulation | 1 | 1 | 5 | 0 | 1 |
| Materials Science | 1 | 1 | 6 | 0 | 0 |
| Medical AI | 1 | 1 | 4 | 0 | 2 |
| NLP / AI | 1 | 1 | 3 | 0 | 3 |
| NLP / RAG | 1 | 1 | 3 | 0 | 3 |
| Neuroscience / Behavior | 1 | 1 | 3 | 1 | 2 |
| Optimization / ML | 1 | 1 | 1 | 2 | 3 |
| Physics | 1 | 1 | 3 | 0 | 3 |
| Quantitative Finance | 1 | 1 | 3 | 2 | 1 |
| Robotics | 1 | 1 | 1 | 4 | 1 |

## Acceptance Check

- At least 12 of 15 cases complete: PASS (15/15)
- At least 8 distinct fields: PASS (15)
- At least one Green: PASS
- At least one Red: PASS

## Limitations

- Public APIs may rate-limit requests; those rows should remain Yellow/inconclusive rather than fabricated.
- Public metadata often lacks abstracts, so Yellow labels are expected for some real citations.
- This audit proves cross-domain behavior of the evidence-chain module, not scientific truth of each generated hypothesis.

## Failure Summary

- Failure entries recorded: 0

## Rerun Note

The `neuroscience_deeplabcut` case originally exposed a Windows Unicode console-output bug. It was fixed and rerun successfully; see `unicode_rerun_note.md`.
