# DeepScientist Citation Hallucination Audit

Generated: 2026-05-31T16:54:26+00:00
Source: C:\Users\99303\git\llm_hypothesis_citation_agent\outputs\generalization_audits\20260601_004420\runs\ai_rag_knowledge_nlp\generated_claims.json

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
| C001 | H001 | Red | exists | mismatch | supports | DOI resolves to a different record. Abstract/snippet overlaps with claim terms: crucial, hallucination, imperative, language, llms, reducing, reliability, reproducibility. |
| C002 | H001 | Red | exists | mismatch | supports | Year mismatch: cited 2020, public record 2026. Abstract/snippet overlaps with claim terms: achieve, been, downstream, factual, fine-tuned, knowledge, language, nlp. |
| C003 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: language, lots, nlp, nowadays, performance, pre-trained, ptlm, remarkable. |
| C004 | H002 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: abstract, amounts, biological, biomedical, complex, databases, facilitating, hosting. |
| C005 | H003 | Red | exists | mismatch | supports | DOI resolves to a different record. Abstract/snippet overlaps with claim terms: ability, attention, attracted, due, especially, few-shot, gpt, has. |
| C006 | H003 | Green | exists | match | supports | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: approaches, automate, compares, generation, language, literature, llm, multiple. |

## Audit Boundary

- Green requires existence, metadata match, and concrete support from title/abstract/snippet.
- Yellow means the cited paper exists but support is partial or cannot be confirmed from public metadata.
- Red means the citation is missing, mismatched, or not supported by available evidence.
- LLM output may be used upstream for hypothesis wording, but this module's labels come from code and public API evidence.