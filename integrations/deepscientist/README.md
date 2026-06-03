# Official DeepScientist Integration

This directory contains the lightweight extension files for using
`llm_hypothesis_citation_agent` as a citation evidence-chain module for the
official DeepScientist repository.

Official DeepScientist clone used during development:

```text
C:\Users\99303\git\DeepScientist-official
```

Upstream repository:

```text
https://github.com/ResearAI/DeepScientist
```

## Integration Strategy

Do not rewrite the official DeepScientist codebase. Keep DeepScientist as the
base research agent and attach this project as a post-hypothesis audit tool:

```text
Official DeepScientist quest
-> idea/write stage produces citation_audit_claims.json
-> llm_hypothesis_citation_agent audits claims
-> citation_verification.csv + evidence_chain.csv + summary report
```

This is low-risk for live demos because DeepScientist can remain responsible for
the research-agent workflow while the course project module remains small,
testable, and explainable.

## Optional Skill Install

Copy the skill folder into official DeepScientist:

```powershell
python scripts/install_deepscientist_extension.py `
  --deepscientist-root C:\Users\99303\git\DeepScientist-official
```

The script installs:

```text
src/skills/citation-evidence-audit/SKILL.md
```

## Audit Command

After a DeepScientist quest writes `citation_audit_claims.json`, run:

```powershell
python scripts/audit_deepscientist_output.py `
  --quest-root "C:\path\to\DeepScientist\quest"
```

The command searches for:

```text
citation_audit_claims.json
generated_claims.json
deepscientist_claims.json
claims.json
```

and then writes audit artifacts under:

```text
outputs/deepscientist_audits/<timestamp>/
```

## Classroom Framing

Use this sentence:

> I use the official DeepScientist repository as the base scientific research
> agent. My added module is a citation evidence-chain audit tool. It receives
> DeepScientist-generated claims and citations, checks them through public
> scholarly APIs and deterministic matching rules, and outputs Green/Yellow/Red
> labels plus evidence IDs and tool logs.
