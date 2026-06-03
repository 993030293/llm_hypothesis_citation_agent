# Design Notes

## Scope

The MVP implements the revised Project A direction:

PDF input -> paper summary -> search queries -> public literature API retrieval
-> conservative hypothesis generation -> citation verification -> report.

The deeper research version adds a second retrieval stage and emits structured
research idea cards. Each card shows the research gap, new hypothesis, novelty
argument, required evidence, supporting citations, limitation, and testable
prediction.

## Official DeepScientist module framing

The selected base direction is official DeepScientist research-agent behavior.
The official repository is cloned at `C:\Users\99303\git\DeepScientist-official`.
DeepScientist provides the research workflow pattern:

```text
paper reading -> research-gap discovery -> hypothesis generation -> report
```

This project adds a citation evidence-chain tracking module after hypothesis
generation. The module takes citation-backed claims, checks whether each cited
paper exists, validates metadata, checks support from public abstracts/snippets,
links source evidence IDs and tool calls, and emits Green/Yellow/Red labels.

The adapter entrypoint is `agent/deepscientist_adapter.py`. The official
DeepScientist helper runner is `scripts/audit_deepscientist_output.py`, which
can audit a quest directory containing `citation_audit_claims.json`.

## Self-implemented components

- `agent/pdf_reader.py`: reads the first PDF pages and extracts title, abstract,
  keywords, and research problem.
- `agent/query_planner.py`: creates search queries from extracted content.
- `agent/literature_search.py`: calls Crossref, OpenAlex, Semantic Scholar, and
  arXiv through project-owned API wrappers.
- `agent/hypothesis_generator.py`: generates conservative research idea cards
  and citation-backed claims.
- `agent/deepscientist_adapter.py`: exposes the verifier as a DeepScientist
  post-hypothesis module with standalone outputs.
- `agent/evidence_chain_tracer.py`: links claims to retrieval evidence,
  verification evidence, tool-call IDs, and support categories.
- `agent/citation_verifier.py`: verifies DOI/title existence, metadata match,
  and support strength.
- `agent/report_writer.py`: writes the required run artifacts.
- `agent/qq_demo_bridge.py`: parses QQ-style commands and runs the workflow
  without changing the core pipeline.

## Label policy

- Green: citation exists, metadata matches, and abstract/snippet specifically
  supports the checked claim.
- Yellow: citation exists but support is partial, abstract-only, or uncertain.
- Red: citation cannot be found, metadata is mismatched, or the available
  metadata does not support the claim.

The verifier is intentionally conservative. If support cannot be confirmed from
public metadata and abstracts, it should return Yellow rather than overclaim.

The citation CSV also records title similarity, author match score, year match,
support score, matched evidence text, and verification method for auditability.
