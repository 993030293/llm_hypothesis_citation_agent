# Verifier Parameter Optimization Report

This is an offline parameter search over manually reviewed citation labels. It does not call an LLM or any external API.

## Best Result

- Manual labels: 14
- Accuracy: 1.0
- Reward: 33
- False Green count: 0
- Wrong Red count: 0
- Predicted distribution: {'Yellow': 9, 'Green': 4, 'Red': 1}

## Selected Parameters

```json
{
  "title_mismatch_threshold": 0.55,
  "title_match_threshold": 0.9,
  "title_partial_threshold": 0.65,
  "author_min_match_score": 0.0,
  "version_title_author_threshold": 0.92,
  "version_preprint_title_threshold": 0.86,
  "version_year_delta_max": 2,
  "support_green_overlap_threshold": 0.32,
  "support_green_similarity_threshold": 0.42,
  "support_partial_overlap_threshold": 0.12,
  "support_partial_similarity_threshold": 0.2,
  "support_score_green_min": 0.7,
  "green_min_source_agreement": 2,
  "allow_input_pdf_fulltext_green": false,
  "cap_green_when_input_extraction_risky": true,
  "strong_claim_terms": [
    "fully solves",
    "solves",
    "eliminates",
    "guarantees",
    "proves",
    "always",
    "never",
    "complete solution"
  ],
  "false_green_penalty": -8,
  "wrong_red_penalty": -3,
  "yellow_when_green_penalty": -2,
  "yellow_when_red_penalty": -3,
  "correct_green_reward": 3,
  "correct_yellow_reward": 2,
  "correct_red_reward": 3
}
```

## Human Review Principle

- False Green is penalized most heavily.
- Year mismatch is Yellow when title/author/DOI still identify the same work.
- Input-PDF-only support stays Yellow by default.
- Risky PDF extraction caps Green to Yellow for classroom-safe reporting.
