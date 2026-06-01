# Evidence Chain

Generated: 2026-05-31T16:58:51+00:00

| Claim ID | Hypothesis | Color | Support Category | Evidence IDs | Tool Calls | Reason |
|---|---|---|---|---|---|---|
| C001 | H001 | Green | directly_supported | E002;E002 | T002 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: accurate, care, chest, crucial, detection, early, images, patient. |
| C002 | H001 | Red | insufficient_or_unsupported | E003;E003 | T003 | DOI resolves to a different record. Abstract/snippet overlaps with claim terms: algorithm, chest, pneumonia, radiologists, x-rays. |
| C003 | H002 | Red | insufficient_or_unsupported | E004;E004 | T004 | Year mismatch: cited 2017, public record 2024. Abstract/snippet overlaps with claim terms: algorithm, chest, pneumonia, radiologists, x-rays. |
| C004 | H002 | Green | directly_supported | E005;E005 | T005 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: although, been, chest, collectively, compared, covid-19, deep, diagnosis. |
| C005 | H003 | Green | directly_supported | E017;E006 | T006 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: cad, chest, chronoxformer, computer-aided, designed, diagnostic, framework, image. |
| C006 | H003 | Green | directly_supported | E006;E007 | T006;T007 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: accurately, annotations, chest, commonly, consuming, costly, detailed, diagnose. |

## Category Meaning

- `directly_supported`: the cited literature exists, metadata matches, and available abstract/snippet supports the claim.
- `reasonable_inference_or_uncertain`: the cited literature exists, but support is partial or requires manual review.
- `insufficient_or_unsupported`: the citation is missing, mismatched, or unsupported by available evidence.