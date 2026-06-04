---
name: citation-hypothesis-claims
description: Generate conservative research hypotheses from a PDF and write a machine-checkable citation_audit_claims.json file for downstream citation hallucination audit.
skill_role: stage
---

# Citation Hypothesis Claims

Use this skill for the course Project A workflow when the input is a scientific
paper PDF and the required DeepScientist output is a small set of new research
ideas plus citation-backed claims that can be audited by an external verifier.

This skill is intentionally narrower than the general `idea` stage. It does not
run experiments, establish baselines, or produce a full manuscript. Its main
artifact is a valid JSON file:

```text
citation_audit_claims.json
```

The local `llm_hypothesis_citation_agent` repository will audit that file later
and assign Green / Yellow / Red labels. Do not decide those labels here.

## Goal

From the input paper:

1. understand the paper's title, abstract, keywords, and research problem;
2. search a small set of related papers with available DeepScientist tools;
3. generate 1-3 conservative research hypotheses or idea cards;
4. attach citation-backed claims to real retrieved papers;
5. write `citation_audit_claims.json` in the quest root.

## Output Contract

Write this file at the quest root before any long report or progress milestone:

```text
citation_audit_claims.json
```

Use this schema:

```json
{
  "case_id": "",
  "paper": {
    "title": "",
    "pdf_path_or_url": ""
  },
  "hypotheses": [
    {
      "hypothesis_id": "H001",
      "research_gap": "",
      "new_hypothesis": "",
      "why_novel": "",
      "risk_or_limitation": "",
      "testable_prediction": ""
    }
  ],
  "claims": [
    {
      "claim_id": "C001",
      "hypothesis_id": "H001",
      "claim_text": "",
      "claim_role": "citation_backed_claim",
      "cited_work": {
        "title": "",
        "authors": [],
        "year": "",
        "doi": "",
        "venue": "",
        "url": "",
        "retrieval_source": "official_deepscientist",
        "abstract": "",
        "snippet": ""
      }
    }
  ]
}
```

Unknown metadata must be an empty string or empty list. Never fabricate DOI,
author, year, venue, or abstract text.

## Workflow

1. Read `citation_audit_runner_brief.md`, `status.md`, and `plan.md` if present.
   They contain the PDF URL/path, case id, and exact artifact requirement.
2. Read the input paper or enough metadata from the PDF URL to identify the
   paper's title, abstract, keywords, research problem, and discipline.
3. Search related literature with available tools. Keep the search bounded:
   3-6 related works are enough for this artifact.
4. Generate 1-3 idea cards. Prefer:
   - one conservative extension;
   - one cross-disciplinary analogy when evidence supports it;
   - one speculative idea only if its risk is clearly stated.
5. For each idea, create 1-3 citation-backed claims. Each claim must cite a real
   retrieved work and must be specific enough for later verification.
6. Write `citation_audit_claims.json` at the quest root.
7. Validate that the file parses as JSON. Repair it once if needed.
8. Stop after the JSON file exists. The local verifier will do the audit.

## Rules

- Do not run a full baseline, experiment, optimization, or paper-writing loop.
- Do not wait for user confirmation.
- Do not call broad quest-state inspection tools such as `artifact.get_quest_state`;
  they are unnecessary for this artifact and may block. Use the runner brief,
  status, plan, and the input PDF metadata instead.
- Do not output Green, Yellow, or Red.
- Do not invent citations or DOI values.
- If tool output is incomplete, still write the JSON with conservative claims and
  empty unknown metadata.
- If a claim is only weakly supported, phrase it cautiously. The local verifier
  may later mark it Yellow.
- Prefer real arXiv / DOI / Crossref / OpenAlex / Semantic Scholar records when
  available.

## Validation Checklist

Before finishing, confirm:

- `citation_audit_claims.json` exists in the quest root;
- the JSON has at least one hypothesis;
- the JSON has at least one claim;
- every claim has `claim_id`, `claim_text`, and `cited_work.title`;
- every claim points to a hypothesis id;
- unknown metadata is blank, not invented.
