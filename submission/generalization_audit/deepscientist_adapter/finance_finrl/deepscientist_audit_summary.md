# DeepScientist Citation Hallucination Audit

Generated: 2026-05-31T17:03:23+00:00
Source: C:\Users\99303\git\llm_hypothesis_citation_agent\outputs\generalization_audits\20260601_004420\runs\finance_finrl\generated_claims.json

## Module Position

This module is inserted after DeepScientist-style hypothesis generation and before final report writing.
It audits generated citation-backed claims rather than generating the final labels with an LLM.

## Label Counts

- Green: 3
- Yellow: 2
- Red: 1

## Verification Table

| Claim ID | Hypothesis | Color | Exists | Metadata | Support | Reason |
|---|---|---|---|---|---|---|
| C001 | H001 | Red | exists | mismatch | supports | DOI resolves to a different record. Abstract/snippet overlaps with claim terms: approach, attractive, been, beginners, deep, drl, effective, experiences. |
| C002 | H001 | Yellow | exists | match | partial_or_uncertain | Metadata matches public record (title similarity 1.00). The citation exists, but no sufficiently detailed abstract/snippet is available for concrete support. |
| C003 | H002 | Yellow | exists | match | partial_or_uncertain | Metadata matches public record (title similarity 1.00). The citation exists, but no sufficiently detailed abstract/snippet is available for concrete support. |
| C004 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: approach, attractive, been, beginners, deep, drl, effective, experiences. |
| C005 | H003 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: been, competitive, deep, drl, edge, envisioned, finance, has. |
| C006 | H003 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: attracted, behavior, both, classic, computer, difficult, economists, forecasting. |

## Audit Boundary

- Green requires existence, metadata match, and concrete support from title/abstract/snippet.
- Yellow means the cited paper exists but support is partial or cannot be confirmed from public metadata.
- Red means the citation is missing, mismatched, or not supported by available evidence.
- LLM output may be used upstream for hypothesis wording, but this module's labels come from code and public API evidence.