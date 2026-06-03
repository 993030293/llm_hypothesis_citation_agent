# Cross-Domain Generalization Audit Report

Generated: 2026-05-31T18:02:18+00:00

## Scope

- Cases configured: 1
- Completed workflow cases: 1
- Distinct fields: 1
- Providers requested: crossref, openalex, semantic_scholar, arxiv
- DeepScientist adapter completed: 1

## Label Distribution

- Green: 3
- Yellow: 1
- Red: 2

## Domain Coverage

| Field | Cases | Completed | Green | Yellow | Red |
|---|---:|---:|---:|---:|---:|
| Neuroscience / Behavior | 1 | 1 | 3 | 1 | 2 |

## Acceptance Check

- At least 12 of 15 cases complete: FAIL (1/15)
- At least 8 distinct fields: FAIL (1)
- At least one Green: PASS
- At least one Red: PASS

## Limitations

- Public APIs may rate-limit requests; those rows should remain Yellow/inconclusive rather than fabricated.
- Public metadata often lacks abstracts, so Yellow labels are expected for some real citations.
- This audit proves cross-domain behavior of the evidence-chain module, not scientific truth of each generated hypothesis.

## Failure Summary

- Failure entries recorded: 0