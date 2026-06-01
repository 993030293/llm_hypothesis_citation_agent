# DeepScientist Citation Hallucination Audit

Generated: 2026-05-31T17:32:04+00:00
Source: C:\Users\99303\git\llm_hypothesis_citation_agent\outputs\generalization_audits\20260601_004420\runs\education_gpt_surprise\generated_claims.json

## Module Position

This module is inserted after DeepScientist-style hypothesis generation and before final report writing.
It audits generated citation-backed claims rather than generating the final labels with an LLM.

## Label Counts

- Green: 5
- Yellow: 1
- Red: 0

## Verification Table

| Claim ID | Hypothesis | Color | Exists | Metadata | Support | Reason |
|---|---|---|---|---|---|---|
| C001 | H001 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: accessible, adopted, being, broadly, chat, chatgpt, copilot, especially. |
| C002 | H001 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: behavior, design, diagrams, essential, language, modeling, software, structure. |
| C003 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: artificial, assisted, emergence, intelligence, interact, language, llms, prior. |
| C004 | H002 | Yellow | exists | match | partial_or_uncertain | Metadata matches public record (title similarity 1.00). The citation exists, but no sufficiently detailed abstract/snippet is available for concrete support. |
| C005 | H003 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: ability, access, advanced, amount, artificial, background, been, capabilities. |
| C006 | H003 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: codes, coding, details, hospitals, icd-9-cm, including, information, instructions. |

## Audit Boundary

- Green requires existence, metadata match, and concrete support from title/abstract/snippet.
- Yellow means the cited paper exists but support is partial or cannot be confirmed from public metadata.
- Red means the citation is missing, mismatched, or not supported by available evidence.
- LLM output may be used upstream for hypothesis wording, but this module's labels come from code and public API evidence.