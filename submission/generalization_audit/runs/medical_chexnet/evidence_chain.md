# Evidence Chain

Generated: 2026-05-31T16:58:09+00:00

| Claim ID | Hypothesis | Color | Support Category | Evidence IDs | Tool Calls | Reason |
|---|---|---|---|---|---|---|
| C001 | H001 | Green | directly_supported | E002;E026 | T003;T033 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: accurate, care, chest, crucial, detection, early, images, patient. |
| C002 | H001 | Red | insufficient_or_unsupported | E003;E027 | T004;T034 | DOI resolves to a different record. Abstract/snippet overlaps with claim terms: algorithm, chest, pneumonia, radiologists, x-rays. |
| C003 | H002 | Red | insufficient_or_unsupported | E004;E028 | T006;T035 | Year mismatch: cited 2017, public record 2024. Abstract/snippet overlaps with claim terms: algorithm, chest, pneumonia, radiologists, x-rays. |
| C004 | H002 | Green | directly_supported | E005;E029 | T017;T036 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: although, been, chest, collectively, compared, covid-19, deep, diagnosis. |
| C005 | H003 | Green | directly_supported | E017;E030 | T020;T037 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: cad, chest, chronoxformer, computer-aided, designed, diagnostic, framework, image. |
| C006 | H003 | Green | directly_supported | E006;E031 | T006;T038 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: accurately, annotations, chest, commonly, consuming, costly, detailed, diagnose. |

## Category Meaning

- `directly_supported`: the cited literature exists, metadata matches, and available abstract/snippet supports the claim.
- `reasonable_inference_or_uncertain`: the cited literature exists, but support is partial or requires manual review.
- `insufficient_or_unsupported`: the citation is missing, mismatched, or unsupported by available evidence.