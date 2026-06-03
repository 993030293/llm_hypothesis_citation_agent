# Citation Evidence Audit

Use this skill after the DeepScientist `idea` or `write` stage when a hypothesis,
research summary, or report contains citation-backed claims that need evidence
chain checking.

## Purpose

Create a machine-checkable claim file and run the external citation evidence
audit module from `llm_hypothesis_citation_agent`.

The audit checks:

- whether each cited work exists;
- whether title, author, year, and DOI metadata match public records;
- whether available title/abstract/snippet evidence supports the claim;
- whether the claim should be labeled Green, Yellow, or Red.

## Required Claim File

Write a JSON file named `citation_audit_claims.json` under the current quest
root before running the audit. Use this schema:

```json
{
  "claims": [
    {
      "claim_id": "C001",
      "hypothesis_id": "H001",
      "claim_text": "Prior work reports that ...",
      "cited_work": {
        "title": "Paper title",
        "authors": ["First Author", "Second Author"],
        "year": 2024,
        "doi": "10.xxxx/yyyy",
        "url": "https://...",
        "venue": "Venue name"
      }
    }
  ]
}
```

Do not invent missing DOI, author, or year metadata. Leave unknown fields empty.

## Command

From the `llm_hypothesis_citation_agent` repository root:

```powershell
python scripts/audit_deepscientist_output.py --quest-root "C:\path\to\deepscientist\quest"
```

Or pass the claim file directly:

```powershell
python scripts/audit_deepscientist_output.py --claims "C:\path\to\citation_audit_claims.json"
```

## Required Outputs

The audit writes:

- `citation_verification.csv`
- `evidence_chain.csv`
- `evidence_chain.md`
- `deepscientist_audit_summary.md`
- `tool_calls.jsonl`
- `evidence_items.jsonl`

## Label Rules

- Green: citation exists, metadata matches, and public abstract/snippet supports the claim.
- Yellow: citation exists but support is partial, abstract is missing, or manual review is needed.
- Red: citation is missing, metadata is mismatched, or available evidence does not support the claim.

The final labels must come from the audit tool, not from an LLM judgment.
