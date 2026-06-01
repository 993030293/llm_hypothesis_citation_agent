# DeepScientist Citation Hallucination Audit

Generated: 2026-05-31T17:40:42+00:00
Source: C:\Users\99303\git\llm_hypothesis_citation_agent\outputs\generalization_audits\20260601_004420\runs\optimization_adam\generated_claims.json

## Module Position

This module is inserted after DeepScientist-style hypothesis generation and before final report writing.
It audits generated citation-backed claims rather than generating the final labels with an LLM.

## Label Counts

- Green: 1
- Yellow: 2
- Red: 3

## Verification Table

| Claim ID | Hypothesis | Color | Exists | Metadata | Support | Reason |
|---|---|---|---|---|---|---|
| C001 | H001 | Yellow | exists | match | partial_or_uncertain | Metadata matches public record (title similarity 1.00). The citation exists, but no sufficiently detailed abstract/snippet is available for concrete support. |
| C002 | H001 | Yellow | exists | match | partial_or_uncertain | Metadata matches public record (title similarity 1.00). The citation exists, but no sufficiently detailed abstract/snippet is available for concrete support. |
| C003 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: bi-objective, cbsop, considers, constrained, constraints, deterministic, functions, optimization. |
| C004 | H002 | Red | exists | mismatch | supports | Year mismatch: cited 2024, public record 2025. Abstract/snippet overlaps with claim terms: accelerating, addresses, algorithm, approaches, challenge, dmops, dynamic, evolutionary. |
| C005 | H003 | Red | exists | mismatch | supports | Year mismatch: cited 2018, public record 2022. Abstract/snippet overlaps with claim terms: asymptotic, condition, functions, introduces, investigates, objective, optimization, polynomial. |
| C006 | H003 | Red | exists | mismatch | supports | Year mismatch: cited 2018, public record 2019. Abstract/snippet overlaps with claim terms: approximate-proximal, aprox, bundle, convex, develop, family, includes, introducing. |

## Audit Boundary

- Green requires existence, metadata match, and concrete support from title/abstract/snippet.
- Yellow means the cited paper exists but support is partial or cannot be confirmed from public metadata.
- Red means the citation is missing, mismatched, or not supported by available evidence.
- LLM output may be used upstream for hypothesis wording, but this module's labels come from code and public API evidence.