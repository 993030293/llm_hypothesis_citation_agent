# DeepScientist Citation Hallucination Audit

Generated: 2026-05-31T16:48:32+00:00
Source: C:\Users\99303\git\llm_hypothesis_citation_agent\outputs\generalization_audits\20260601_004420\runs\ai_transformer_attention\generated_claims.json

## Module Position

This module is inserted after DeepScientist-style hypothesis generation and before final report writing.
It audits generated citation-backed claims rather than generating the final labels with an LLM.

## Label Counts

- Green: 3
- Yellow: 0
- Red: 3

## Verification Table

| Claim ID | Hypothesis | Color | Exists | Metadata | Support | Reason |
|---|---|---|---|---|---|---|
| C001 | H001 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: action, adults, all, attention, behavior, call, considerate, encourage. |
| C002 | H001 | Red | exists | mismatch | supports | Year mismatch: cited 2022, public record 2024. Abstract/snippet overlaps with claim terms: applied, architectures, becoming, deep, domains, heavily, learning, modalities. |
| C003 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: been, community, computing, deemed, deep, few, gold, has. |
| C004 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: amount, atmosphere, changes, cycle, modify, over, ozone, solar. |
| C005 | H003 | Red | exists | mismatch | supports | Year mismatch: cited 2019, public record 2020. Abstract/snippet overlaps with claim terms: determines, essential, evidence, explanatory, identification, outcome, power, relevant. |
| C006 | H003 | Red | exists | mismatch | supports | Year mismatch: cited 2023, public record 2025. Abstract/snippet overlaps with claim terms: able, architectures, attention, cross-attention, dca, dual, effective, enhance. |

## Audit Boundary

- Green requires existence, metadata match, and concrete support from title/abstract/snippet.
- Yellow means the cited paper exists but support is partial or cannot be confirmed from public metadata.
- Red means the citation is missing, mismatched, or not supported by available evidence.
- LLM output may be used upstream for hypothesis wording, but this module's labels come from code and public API evidence.