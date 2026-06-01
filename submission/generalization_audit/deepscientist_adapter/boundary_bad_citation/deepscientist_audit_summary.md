# DeepScientist Citation Hallucination Audit

Generated: 2026-05-31T17:49:58+00:00
Source: C:\Users\99303\git\llm_hypothesis_citation_agent\outputs\generalization_audits\20260601_004420\runs\boundary_bad_citation\generated_claims.json

## Module Position

This module is inserted after DeepScientist-style hypothesis generation and before final report writing.
It audits generated citation-backed claims rather than generating the final labels with an LLM.

## Label Counts

- Green: 4
- Yellow: 1
- Red: 2

## Verification Table

| Claim ID | Hypothesis | Color | Exists | Metadata | Support | Reason |
|---|---|---|---|---|---|---|
| C001 | H001 | Yellow | exists | match | partial_or_uncertain | Metadata matches public record (title similarity 1.00). The citation exists, but no sufficiently detailed abstract/snippet is available for concrete support. |
| C002 | H001 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: academic, commentary, freebase, like, manage, mp3s, nice, papers. |
| C003 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: academic, commentary, freebase, like, manage, mp3s, nice, papers. |
| C004 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: amount, content, currently, description, digital, diverse, extremely, facilitate. |
| C005 | H003 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: abstract, bibliographic, citation, count, fabricating, frequency, language, llms. |
| C006 | H003 | Red | exists | mismatch | supports | Year mismatch: cited 2024, public record 2025. Abstract/snippet overlaps with claim terms: generation, holds, hypothesis, including, prior, processes, promise, scientific. |
| C007 | H_BOUNDARY | Red | not_found | unknown | not_supported | Invalid DOI format: INTENTIONALLY_INVALID_DOI_FOR_DEMO |

## Audit Boundary

- Green requires existence, metadata match, and concrete support from title/abstract/snippet.
- Yellow means the cited paper exists but support is partial or cannot be confirmed from public metadata.
- Red means the citation is missing, mismatched, or not supported by available evidence.
- LLM output may be used upstream for hypothesis wording, but this module's labels come from code and public API evidence.