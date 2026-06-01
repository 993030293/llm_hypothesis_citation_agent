# DeepScientist Citation Hallucination Audit

Generated: 2026-05-31T17:07:49+00:00
Source: C:\Users\99303\git\llm_hypothesis_citation_agent\outputs\generalization_audits\20260601_004420\runs\physics_gravitational_waves\generated_claims.json

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
| C001 | H001 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: ago, albert, black, born, breakthroughs, century, collision, described. |
| C002 | H001 | Red | exists | mismatch | supports | Year mismatch: cited 2020, public record 2021. Abstract/snippet overlaps with claim terms: announced, binary, black, first, gravitational, gw150914, hole, known. |
| C003 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: detectors, gravitational-wave, interferometer, laser, observatory, observed, september, signal. |
| C004 | H002 | Red | exists | mismatch | supports | Year mismatch: cited 2020, public record 2022. Abstract/snippet overlaps with claim terms: abstract, applied, bayesian, been, black, coalescence, detection, estimates. |
| C005 | H003 | Red | exists | mismatch | supports | Year mismatch: cited 2018, public record 2019. Abstract/snippet overlaps with claim terms: accessible, binary, black-hole, collaboration, dawn, detection, directly, dynamics. |
| C006 | H003 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: astronomy, gravitational, has, motion, revolution, scientific, set, wave. |

## Audit Boundary

- Green requires existence, metadata match, and concrete support from title/abstract/snippet.
- Yellow means the cited paper exists but support is partial or cannot be confirmed from public metadata.
- Red means the citation is missing, mismatched, or not supported by available evidence.
- LLM output may be used upstream for hypothesis wording, but this module's labels come from code and public API evidence.