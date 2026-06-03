# DeepScientist Citation Hallucination Audit

Generated: 2026-05-31T17:36:23+00:00
Source: C:\Users\99303\git\llm_hypothesis_citation_agent\outputs\generalization_audits\20260601_004420\runs\education_llm_harm_learning\generated_claims.json

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
| C001 | H001 | Red | exists | mismatch | supports | Year mismatch: cited 2024, public record 2025. Abstract/snippet overlaps with claim terms: artificial, content, genai, generate, generative, intelligence, language, llms. |
| C002 | H001 | Red | exists | mismatch | supports | Year mismatch: cited 2024, public record 2025. Abstract/snippet overlaps with claim terms: analyzing, artificial, capable, intelligence, language, llms, mimicking, natural. |
| C003 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: broad, chatgpt, converse, enabling, generative, language, launched, machine. |
| C004 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: applications, artificial, become, chatgpt, fastest, gai, generative, growing. |
| C005 | H003 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: accessibility, educational, emphasizing, enhanced, environments, experiences, explores, inclusivity. |
| C006 | H003 | Red | exists | mismatch | supports | Year mismatch: cited 2024, public record 2025. Abstract/snippet overlaps with claim terms: accuracy, artificial, background, dental, fields, generative, increasing, intelligence. |

## Audit Boundary

- Green requires existence, metadata match, and concrete support from title/abstract/snippet.
- Yellow means the cited paper exists but support is partial or cannot be confirmed from public metadata.
- Red means the citation is missing, mismatched, or not supported by available evidence.
- LLM output may be used upstream for hypothesis wording, but this module's labels come from code and public API evidence.