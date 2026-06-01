# Path 2: Official DeepScientist + Claude Code

This is the primary project route.

```text
official DeepScientist quest
-> Claude Code runner generates hypothesis / citation-backed claims
-> citation_audit_claims.json
-> llm_hypothesis_citation_agent audit module
-> citation_verification.csv + evidence_chain.csv + tool logs
```

## What Belongs To DeepScientist

DeepScientist is the base research agent. It owns:

- the research quest workspace;
- the Claude Code runner;
- research planning and hypothesis generation;
- writing or exporting citation-backed claims.

This repository does not replace DeepScientist. It adds a post-generation
citation evidence-chain audit module.

## What Belongs To This Repository

This repository owns:

- `integrations/deepscientist/citation-evidence-audit/SKILL.md`;
- `agent/deepscientist_adapter.py`;
- `agent/citation_verifier.py`;
- `agent/evidence_chain_tracer.py`;
- `scripts/audit_deepscientist_output.py`;
- `scripts/setup_path2_claude.py`;
- `scripts/path2_smoke_test.py`.

The final Green/Yellow/Red labels are produced by code and public scholarly API
lookups, not by Claude.

## Setup On Your Machine

Run from this repository root:

```powershell
python scripts/setup_path2_claude.py --force-skill
```

The setup script checks:

- Node.js/npm;
- Claude Code CLI;
- Claude Code headless prompt execution;
- global `ds` DeepScientist CLI;
- installation of the `citation-evidence-audit` skill;
- `ds doctor --runner claude`.

If `ds` is missing, the script installs it with:

```powershell
npm install -g @researai/deepscientist
```

Start the official DeepScientist live system with Claude Code:

```powershell
ds --runner claude
```

## Teammate Setup

Each teammate should:

1. Clone this repository.
2. Install Python dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Make sure Claude Code works locally:

   ```powershell
   claude --version
   claude -p "Reply with exactly HELLO." --output-format json --tools=
   ```

4. Prepare DeepScientist path 2:

   ```powershell
   python scripts/setup_path2_claude.py --force-skill
   ```

5. Run the smoke test:

   ```powershell
   python scripts/path2_smoke_test.py
   ```

## Real Quest Audit

Inside a real DeepScientist quest, ask the agent to create:

```text
citation_audit_claims.json
```

Required schema:

```json
{
  "claims": [
    {
      "claim_id": "C001",
      "hypothesis_id": "H001",
      "claim_text": "Prior work reports that ...",
      "claim_role": "supporting_literature_claim",
      "cited_work": {
        "title": "...",
        "authors": ["..."],
        "year": 2024,
        "doi": "10.xxxx/xxxxx",
        "url": "...",
        "retrieval_source": "deepscientist_output"
      }
    }
  ]
}
```

Then audit the quest:

```powershell
python scripts/audit_deepscientist_output.py --quest-root "C:\Users\<you>\DeepScientist\quests\<quest_id>"
```

## Expected Outputs

The audit module writes:

```text
citation_verification.csv
evidence_chain.csv
evidence_chain.md
deepscientist_audit_summary.md
tool_calls.jsonl
evidence_items.jsonl
```

These files are the core classroom evidence that this is not only prompt-based
chat. They show tool calls, public retrieval evidence, evidence IDs, and
Green/Yellow/Red labels.

## Windows Note

Official DeepScientist native Windows support is marked experimental upstream.
On this machine, the global npm package path passed:

```powershell
ds doctor --runner claude
```

If a source checkout of DeepScientist fails while the global npm package passes,
use the global package for the live demo and teammate reproduction.
