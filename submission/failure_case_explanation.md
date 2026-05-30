# Failure Case Explanation

This file summarizes the labels to explain during the classroom demo.

## Success case: Green and Yellow together

Canonical file:

`submission/evidence/success_case/citation_verification.csv`

Observed labels:

- Green: 3
- Yellow: 1
- Red: 0

Example Green row:

- Claim ID: `C002`
- Cited title: `Text Data Augmentation for Deep Learning`
- DOI: `10.1186/s40537-021-00492-0`
- Why Green: public metadata matches and the abstract directly supports the
  claim that NLP is an important application of deep learning.

Example Yellow row:

- Claim ID: `C004`
- Cited title: `A Comparative Study of Retrieval-Augmented Generation, Graph Retrieval-Augmented Generation, and Fine-Tuned Large Language Models for Fire Engineering Knowledge Retrieval`
- DOI: `10.2139/ssrn.5253805`
- Why Yellow: the citation exists and metadata matches, but public metadata did
  not expose a detailed abstract or snippet that can confirm the generated
  claim. A human should inspect the full text.

## Boundary case: Yellow and Red

Canonical file:

`submission/evidence/boundary_case/citation_verification.csv`

Observed labels:

- Green: 0
- Yellow: 1
- Red: 1

Example Yellow row:

- Claim ID: `C001`
- Cited title: `MedDiscovery: Emergent Cross-Domain Scientific Reasoning in an Autonomous Multi-Agent Hypothesis Generation System`
- DOI: `10.2139/ssrn.5920904`
- Why Yellow: the citation exists and metadata matches, but available public
  text is insufficient for concrete claim support.

Example Red row:

- Claim ID: `C002`
- Cited title: `Clearly Nonexistent Citation Verification Paper for Boundary Demo`
- DOI: `INTENTIONALLY_INVALID_DOI_FOR_DEMO`
- Why Red: this intentionally invalid citation fails DOI format validation and
  cannot identify a real paper.

## Demo explanation

The boundary Red row is intentionally injected by `--inject-bad-citation` to
prove that the verifier rejects malformed or nonexistent citations. It should
not be described as a real DOI or real paper.

The Yellow rows demonstrate a key research-agent limitation: existence and
metadata match are not enough. If the support relationship is uncertain, the
system keeps the label Yellow and asks for human inspection.
