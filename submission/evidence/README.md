# Evidence Directory

This folder contains frozen copies of two canonical workflow runs.

## Success case

- Source run: `outputs/runs/submission_success_refresh`
- Input PDF: `inputs/papers/success_demo.pdf`
- Main command:
  `python agent/workflow.py --pdf inputs/papers/success_demo.pdf --task "Canonical success case with evidence chain" --live-demo --run-dir outputs/runs/submission_success_refresh`
- Verification labels observed in `citation_verification.csv`:
  - Green: 1
  - Yellow: 1
  - Red: 0
- Evidence chain output:
  - `evidence_chain.csv`
  - `evidence_chain.md`

## Boundary case

- Source run: `outputs/runs/submission_boundary_refresh`
- Input PDF: `inputs/papers/boundary_demo.pdf`
- Main command:
  `python agent/workflow.py --pdf inputs/papers/boundary_demo.pdf --task "Canonical boundary case with evidence chain" --live-demo --inject-bad-citation --run-dir outputs/runs/submission_boundary_refresh`
- Verification labels observed in `citation_verification.csv`:
  - Green: 1
  - Yellow: 1
  - Red: 1
- Evidence chain output:
  - `evidence_chain.csv`
  - `evidence_chain.md`

The boundary Red citation is intentionally invalid and is labeled Red by the
project-owned DOI format and existence checks. It is not presented as a real
paper.
