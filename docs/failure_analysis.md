# Failure and Boundary Case Analysis

The citation verifier intentionally separates three questions:

1. Does the cited work exist?
2. Does the public metadata match the cited title, author, year, and DOI?
3. Does the available title, abstract, or snippet specifically support the
   checked claim?

This separation is important because a real paper can still be a weak or wrong
citation for a generated hypothesis.

## Yellow: existing paper, uncertain support

Yellow means the work exists, but the system cannot confirm concrete claim
support from the available metadata, abstract, or snippet.

Common causes:

- Crossref/OpenAlex has title and DOI metadata but no usable abstract.
- The result is topically related but does not directly state the claim.
- The claim is too broad or too strong for the available public snippet.
- Full text would be needed for a reliable human judgment.

Canonical example:

- File: `submission/evidence/boundary_case/citation_verification.csv`
- Row: `C001`
- Label: Yellow
- Reason: the citation exists and metadata matches, but the available public
  record does not provide enough detailed support text.

## Red: invalid or unsupported citation

Red means the verifier found a serious citation problem.

Common causes:

- DOI format is invalid.
- No matching public record is found.
- Title, author, or year clearly conflicts with public metadata.
- The available metadata contradicts or fails to support the claim.

Canonical example:

- File: `submission/evidence/boundary_case/citation_verification.csv`
- Row: `C002`
- Label: Red
- Reason: `INTENTIONALLY_INVALID_DOI_FOR_DEMO` fails DOI format validation and
  cannot identify a real work.

## Green: verified support

Green requires all of the following:

- the work exists;
- DOI/title/author/year metadata basically match;
- abstract or snippet text specifically supports the claim.

Canonical example:

- File: `submission/evidence/success_case/citation_verification.csv`
- Row: `C002`
- Label: Green
- Reason: the citation exists, metadata matches, and the available abstract
  explicitly discusses Natural Language Processing as an application of Deep
  Learning.

## Why conservative labeling matters

The goal is not to make the agent look successful. The goal is to detect
citation risk. If the system cannot confirm support, Yellow is the correct
answer. This avoids turning weak topical similarity into a false Green result.

## Known limitations

- Public APIs often expose metadata but not full abstracts.
- Cross-disciplinary ideas can require evidence from multiple fields, making
  support harder to confirm from a single paper.
- DOI and title matching are not enough to prove claim support.
- API failures should appear in `tool_calls.jsonl`; they must not be silently
  ignored.
