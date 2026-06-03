# Evidence Chain

Generated: 2026-05-31T16:53:39+00:00

| Claim ID | Hypothesis | Color | Support Category | Evidence IDs | Tool Calls | Reason |
|---|---|---|---|---|---|---|
| C001 | H001 | Red | insufficient_or_unsupported | E002;E029 | T008;T033 | DOI resolves to a different record. Abstract/snippet overlaps with claim terms: crucial, hallucination, imperative, language, llms, reducing, reliability, reproducibility. |
| C002 | H001 | Red | insufficient_or_unsupported | E003;E030 | T008;T034 | Year mismatch: cited 2020, public record 2026. Abstract/snippet overlaps with claim terms: achieve, been, downstream, factual, fine-tuned, knowledge, language, nlp. |
| C003 | H002 | Green | directly_supported | E004;E031 | T015;T035 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: language, lots, nlp, nowadays, performance, pre-trained, ptlm, remarkable. |
| C004 | H002 | Green | directly_supported | E005;E032 | T003;T036 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: abstract, amounts, biological, biomedical, complex, databases, facilitating, hosting. |
| C005 | H003 | Red | insufficient_or_unsupported | E006;E033 | T004;T037 | DOI resolves to a different record. Abstract/snippet overlaps with claim terms: ability, attention, attracted, due, especially, few-shot, gpt, has. |
| C006 | H003 | Green | directly_supported | E007;E034 | T006;T038 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: approaches, automate, compares, generation, language, literature, llm, multiple. |

## Category Meaning

- `directly_supported`: the cited literature exists, metadata matches, and available abstract/snippet supports the claim.
- `reasonable_inference_or_uncertain`: the cited literature exists, but support is partial or requires manual review.
- `insufficient_or_unsupported`: the citation is missing, mismatched, or unsupported by available evidence.