# DeepScientist Citation Hallucination Audit

Generated: 2026-05-31T18:02:18+00:00
Source: C:\Users\99303\git\llm_hypothesis_citation_agent\outputs\generalization_audits\20260601_015740\runs\neuroscience_deeplabcut\generated_claims.json

## Module Position

This module is inserted after DeepScientist-style hypothesis generation and before final report writing.
It audits generated citation-backed claims rather than generating the final labels with an LLM.

## Label Counts

- Green: 3
- Yellow: 1
- Red: 2

## Verification Table

| Claim ID | Hypothesis | Color | Exists | Metadata | Support | Reason |
|---|---|---|---|---|---|---|
| C001 | H001 | Red | exists | mismatch | supports | Year mismatch: cited 2019, public record 2020. Abstract/snippet overlaps with claim terms: adequately, basic, brain, central, clinical, cns, diseases, has. |
| C002 | H001 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: abstract, arousal, attention, biomarker, brain, cognitive, consciousness, correlating. |
| C003 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: abstract, accurate, applications, behavioral, biomedical, interest, markerless, mouse. |
| C004 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: applique, cette, contribution, crire, crit, dans, des, ethnographique. |
| C005 | H003 | Yellow | exists | match | partial_or_uncertain | Metadata matches public record (title similarity 1.00). The citation exists, but no sufficiently detailed abstract/snippet is available for concrete support. |
| C006 | H003 | Red | exists | mismatch | supports | Year mismatch: cited 2021, public record 2022. Abstract/snippet overlaps with claim terms: deep, describe, field, learning, mathematical, new. |

## Audit Boundary

- Green requires existence, metadata match, and concrete support from title/abstract/snippet.
- Yellow means the cited paper exists but support is partial or cannot be confirmed from public metadata.
- Red means the citation is missing, mismatched, or not supported by available evidence.
- LLM output may be used upstream for hypothesis wording, but this module's labels come from code and public API evidence.