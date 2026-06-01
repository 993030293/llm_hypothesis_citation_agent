# Official DeepScientist Extension Plan

## Decision

Use the official DeepScientist repository as the base research agent and attach
this project as a citation evidence-chain audit extension.

Official repository cloned locally:

```text
C:\Users\99303\git\DeepScientist-official
```

Upstream:

```text
https://github.com/ResearAI/DeepScientist
```

Inspected official DeepScientist sources:

- `README.md`: describes DeepScientist as a local-first autonomous research
  studio that keeps research progress, artifacts, reports, and experiments in a
  durable workspace.
- `assets/text/agents/core-agent.md`: defines the canonical research graph:
  `scout -> baseline -> idea -> experiment -> analysis_campaign -> write -> finalize`.
- `assets/text/agents/writer.md`: requires evidence-bound writing, a
  claim-evidence map, missing-evidence reporting, and no invented citations.
- `src/skills/`: contains the official skill layout used by DeepScientist.

## Integration Boundary

The course module is inserted after DeepScientist generates ideas or report
claims:

```text
Official DeepScientist quest
-> idea/write stage
-> citation_audit_claims.json
-> this project's citation evidence-chain audit
-> Green/Yellow/Red evidence report
```

The added module does not replace DeepScientist. It audits its citation-backed
claims.

## Implemented Artifacts

Project-side adapter:

```text
agent/deepscientist_adapter.py
```

Evidence-chain module:

```text
agent/evidence_chain_tracer.py
```

Official DeepScientist helper skill:

```text
integrations/deepscientist/citation-evidence-audit/SKILL.md
```

Install helper:

```text
scripts/install_deepscientist_extension.py
```

Audit runner:

```text
scripts/audit_deepscientist_output.py
```

## Claim File Contract

DeepScientist should write this file in a quest/output directory:

```text
citation_audit_claims.json
```

Schema:

```json
{
  "claims": [
    {
      "claim_id": "C001",
      "hypothesis_id": "H001",
      "claim_text": "Prior work reports that ...",
      "cited_work": {
        "title": "Paper title",
        "authors": ["Author One"],
        "year": 2024,
        "doi": "10.xxxx/yyyy",
        "url": "https://...",
        "venue": "Venue"
      }
    }
  ]
}
```

Unknown metadata should be left empty rather than invented.

## Commands

Install the optional DeepScientist skill:

```powershell
python scripts/install_deepscientist_extension.py `
  --deepscientist-root C:\Users\99303\git\DeepScientist-official
```

Audit an official DeepScientist quest/output directory:

```powershell
python scripts/audit_deepscientist_output.py `
  --quest-root "C:\path\to\deepscientist\quest"
```

Audit a claim file directly:

```powershell
python scripts/audit_deepscientist_output.py `
  --claims "C:\path\to\citation_audit_claims.json"
```

## Output

The audit produces:

```text
citation_verification.csv
evidence_chain.csv
evidence_chain.md
deepscientist_audit_summary.md
tool_calls.jsonl
evidence_items.jsonl
```

## Classroom Explanation

Use this wording:

> I use the official DeepScientist repository as the base scientific research
> agent. DeepScientist handles the research-agent workflow: paper input,
> idea generation, and report writing. My extension is a citation evidence-chain
> audit module. It receives DeepScientist-generated citation-backed claims,
> verifies them through Crossref/OpenAlex and deterministic matching rules, and
> writes evidence IDs, tool logs, and Green/Yellow/Red labels.
