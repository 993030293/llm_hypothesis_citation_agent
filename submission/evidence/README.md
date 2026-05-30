# Evidence Directory

This folder contains frozen copies of two canonical workflow runs.

## Success case

- Source run: `outputs/runs/20260529_193717`
- Input PDF: `inputs/papers/success_demo.pdf`
- Main command:
  `python agent/workflow.py --pdf inputs/papers/success_demo.pdf --task "Generate a new research hypothesis and verify citations"`
- Verification labels observed in `citation_verification.csv`:
  - Green: 3
  - Yellow: 1
  - Red: 0

## Boundary case

- Source run: `outputs/runs/20260529_193944`
- Input PDF: `inputs/papers/boundary_demo.pdf`
- Main command:
  `python agent/workflow.py --pdf inputs/papers/boundary_demo.pdf --task "Generate a boundary-case hypothesis and verify citations" --inject-bad-citation`
- Verification labels observed in `citation_verification.csv`:
  - Green: 0
  - Yellow: 1
  - Red: 1

The boundary Red citation is intentionally invalid and is labeled Red by the
project-owned DOI format and existence checks. It is not presented as a real
paper.
