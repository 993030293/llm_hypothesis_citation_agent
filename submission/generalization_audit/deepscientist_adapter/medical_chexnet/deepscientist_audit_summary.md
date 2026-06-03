# DeepScientist Citation Hallucination Audit

Generated: 2026-05-31T16:58:51+00:00
Source: C:\Users\99303\git\llm_hypothesis_citation_agent\outputs\generalization_audits\20260601_004420\runs\medical_chexnet\generated_claims.json

## Module Position

This module is inserted after DeepScientist-style hypothesis generation and before final report writing.
It audits generated citation-backed claims rather than generating the final labels with an LLM.

## Label Counts

- Green: 4
- Yellow: 0
- Red: 2

## Verification Table

| Claim ID | Hypothesis | Color | Exists | Metadata | Support | Reason |
|---|---|---|---|---|---|---|
| C001 | H001 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: accurate, care, chest, crucial, detection, early, images, patient. |
| C002 | H001 | Red | exists | mismatch | supports | DOI resolves to a different record. Abstract/snippet overlaps with claim terms: algorithm, chest, pneumonia, radiologists, x-rays. |
| C003 | H002 | Red | exists | mismatch | supports | Year mismatch: cited 2017, public record 2024. Abstract/snippet overlaps with claim terms: algorithm, chest, pneumonia, radiologists, x-rays. |
| C004 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: although, been, chest, collectively, compared, covid-19, deep, diagnosis. |
| C005 | H003 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: cad, chest, chronoxformer, computer-aided, designed, diagnostic, framework, image. |
| C006 | H003 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: accurately, annotations, chest, commonly, consuming, costly, detailed, diagnose. |

## Audit Boundary

- Green requires existence, metadata match, and concrete support from title/abstract/snippet.
- Yellow means the cited paper exists but support is partial or cannot be confirmed from public metadata.
- Red means the citation is missing, mismatched, or not supported by available evidence.
- LLM output may be used upstream for hypothesis wording, but this module's labels come from code and public API evidence.