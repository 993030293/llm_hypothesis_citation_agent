# DeepScientist Citation Hallucination Audit

Generated: 2026-05-31T17:45:46+00:00
Source: C:\Users\99303\git\llm_hypothesis_citation_agent\outputs\generalization_audits\20260601_004420\runs\existing_finance_evomarket\generated_claims.json

## Module Position

This module is inserted after DeepScientist-style hypothesis generation and before final report writing.
It audits generated citation-backed claims rather than generating the final labels with an LLM.

## Label Counts

- Green: 5
- Yellow: 0
- Red: 1

## Verification Table

| Claim ID | Hypothesis | Color | Exists | Metadata | Support | Reason |
|---|---|---|---|---|---|---|
| C001 | H001 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: analyzing, computational, examines, language, limitations, llms, perspective, position. |
| C002 | H001 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: agents, complex, interact, market, multiple, represents, stock, systems. |
| C003 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: counterfactual, evaluation, high-fidelity, instrument, key, market, mechanism, policy. |
| C004 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: abm, accounting, activity, agent-based, banks, calibration, capable, central. |
| C005 | H003 | Red | exists | mismatch | supports | Year mismatch: cited 2024, public record 2025. Abstract/snippet overlaps with claim terms: agent-based, been, certain, different, discrepancy, frequently, has, indistinguishable. |
| C006 | H003 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: better, competitive, comprehensive, customers, develop, dynamics, featuring, market. |

## Audit Boundary

- Green requires existence, metadata match, and concrete support from title/abstract/snippet.
- Yellow means the cited paper exists but support is partial or cannot be confirmed from public metadata.
- Red means the citation is missing, mismatched, or not supported by available evidence.
- LLM output may be used upstream for hypothesis wording, but this module's labels come from code and public API evidence.