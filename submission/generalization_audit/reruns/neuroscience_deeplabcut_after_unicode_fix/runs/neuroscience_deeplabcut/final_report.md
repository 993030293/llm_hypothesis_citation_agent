# Final Report

Generated: 2026-05-31T18:01:43+00:00
Task: Generalization audit case neuroscience_deeplabcut: generate hypothesis and verify citations
Input PDF: C:\Users\99303\git\llm_hypothesis_citation_agent\inputs\generalization_cases\papers\neuroscience_deeplabcut.pdf

## Paper Summary

Title: Markerless tracking of user-deﬁned features with deep learning
Pages read: 3 / 14
Keywords: neuroscience, behavior, institute, center, harvard, usa, tracking, mathis, ubingen, university, brain, markerless

Research problem:

(1) Training: extract images with distinct postures characteristic of the animal behavior in question. For computational eﬃciency, the region of interest (ROI) should be picked to be as small as possible while containing the behavior in question, which is reaching in the example.

## Toolchain Evidence

- Search queries generated: 7
- Literature records retrieved: 32
- Hypotheses generated: 3
- Citation-backed claims checked: 6
- Evidence items recorded: 44

Required run artifacts are in this same run directory: tool_calls.jsonl, retrieved_literature.jsonl, citation_verification.csv, and final_report.md.
Evidence-chain artifacts are also written as evidence_chain.csv and evidence_chain.md.

## Search Queries

| Query ID | Stage | Type | Query | Purpose |
|---|---|---|---|---|
| Q001 | initial | seed | Markerless tracking of user-deﬁned features with deep learning neuroscience behavior institute | Find papers directly related to the input paper topic. |
| Q002 | initial | seed | neuroscience behavior institute center harvard usa | Find thematically related literature from extracted keywords. |
| Q003 | initial | seed | behavior question training extract images distinct postures | Find papers around the research problem or gap. |
| Q004 | initial | seed | neuroscience behavior institute center survey review | Find broader review literature for citation grounding. |
| Q005 | followup | method-oriented | neuroscience behavior institute center harvard method framework | Follow-up method query from initial retrieval results. |
| Q006 | followup | application-oriented | neuroscience behavior institute center application cross disciplinary | Follow-up application query for cross-disciplinary hypothesis transfer. |
| Q007 | followup | limitation-oriented | neuroscience behavior institute center limitations challenge | Follow-up limitation query to surface uncertainty or contradiction. |

## Generated Research Ideas

### H001: conservative extension
Evidence status: `citation_backed`

Research gap: (1) Training: extract images with distinct postures characteristic of the animal behavior in question. For computational eﬃciency, the region of interest (ROI) should be picked to be as small as possible while containing the behavior in question, which is reaching in the example.

New hypothesis: A conservative next study should test whether techniques or observations from 'Quantitative Systems Pharmacology for Neuroscience Drug Discovery and Development: Current Status, Opportunities, and Challenges' and 'Pupil-DLC: an open-source deep learning pipeline for scalable, markerless tracking of pupil dynamics across conscious and unconscious states' improve evidence-grounded work on neuroscience, behavior, institute, center.

Risk or limitation: Novelty is moderate; the idea may be an incremental extension if the cited works already overlap strongly.
Citation claims: C001, C002

### H002: cross-disciplinary analogy
Evidence status: `citation_backed`

Research gap: (1) Training: extract images with distinct postures characteristic of the animal behavior in question. For computational eﬃciency, the region of interest (ROI) should be picked to be as small as possible while containing the behavior in question, which is reaching in the example.

New hypothesis: If the mechanisms discussed in 'Real-time markerless video tracking of body parts in mice using deep neural networks' transfer across domains, then neuroscience, behavior, institute, center may benefit from a cross-disciplinary evaluation protocol grounded by 'Identités numériques sur facebook : idiolectes et postures en question'.

Risk or limitation: The analogy may fail if the source domain assumptions do not hold for the input paper's domain.
Citation claims: C003, C004

### H003: high-risk speculative idea
Evidence status: `citation_backed`

Research gap: (1) Training: extract images with distinct postures characteristic of the animal behavior in question. For computational eﬃciency, the region of interest (ROI) should be picked to be as small as possible while containing the behavior in question, which is reaching in the example.

New hypothesis: A higher-risk hypothesis is that the shared signals behind 'Dana-Farber/Harvard Cancer Center' and 'The Modern Mathematics of Deep Learning' point to a broader latent factor affecting neuroscience, behavior, institute, center.

Risk or limitation: This is speculative and should be treated as Yellow unless stronger evidence is retrieved.
Citation claims: C005, C006

## Citation Verification Summary

Green: 3; Yellow: 1; Red: 2

| Claim ID | Color | Exists | Metadata | Support | Scores | Reason | Evidence |
|---|---|---|---|---|---|---|---|
| C001 | Red | exists | mismatch | supports | title=1.0; author=1.0; support=0.864 | Year mismatch: cited 2019, public record 2020. Abstract/snippet overlaps with claim terms: adequately, basic, brain, central, clinical, cns, diseases, has. | E038 |
| C002 | Green | exists | match | supports | title=1.0; author=1.0; support=0.842 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: abstract, arousal, attention, biomarker, brain, cognitive, consciousness, correlating. | E039 |
| C003 | Green | exists | match | supports | title=1.0; author=1.0; support=0.8 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: abstract, accurate, applications, behavioral, biomedical, interest, markerless, mouse. | E040 |
| C004 | Green | exists | match | supports | title=1.0; author=1.0; support=0.88 | Metadata matches public record (title similarity 1.00). Abstract/snippet overlaps with claim terms: applique, cette, contribution, crire, crit, dans, des, ethnographique. | E041 |
| C005 | Yellow | exists | match | partial_or_uncertain | title=1.0; author=1.0; support=1.0 | Metadata matches public record (title similarity 1.00). The citation exists, but no sufficiently detailed abstract/snippet is available for concrete support. | E042 |
| C006 | Red | exists | mismatch | supports | title=1.0; author=1.0; support=0.667 | Year mismatch: cited 2021, public record 2022. Abstract/snippet overlaps with claim terms: deep, describe, field, learning, mathematical, new. | E043 |

## Evidence Chain Table

| Claim ID | Hypothesis | Color | Support Category | Evidence IDs | Tool Calls | Manual Review |
|---|---|---|---|---|---|---|
| C001 | H001 | Red | insufficient_or_unsupported | E022;E038 | T025;T033 | True |
| C002 | H001 | Green | directly_supported | E002;E039 | T003;T034 | False |
| C003 | H002 | Green | directly_supported | E003;E040 | T003;T035 | False |
| C004 | H002 | Green | directly_supported | E004;E041 | T011;T036 | False |
| C005 | H003 | Yellow | reasonable_inference_or_uncertain | E023;E042 | T020;T037 | True |
| C006 | H003 | Red | insufficient_or_unsupported | E005;E043 | T006;T038 | True |

## Retrieved Literature Preview

| Literature ID | Selected | Relevance | Source | Year | Title | DOI | Evidence |
|---|---:|---:|---|---|---|---|---|
| L001 | True | 0.8 | openalex | 2019 | Quantitative Systems Pharmacology for Neuroscience Drug Discovery and Development: Current Status, Opportunities, and Challenges | 10.1002/psp4.12478 | E022 |
| L002 | True | 0.68 | crossref | 2026 | Pupil-DLC: an open-source deep learning pipeline for scalable, markerless tracking of pupil dynamics across conscious and unconscious states | 10.64898/2026.01.18.700183 | E002 |
| L003 | True | 0.61 | crossref | 2018 | Real-time markerless video tracking of body parts in mice using deep neural networks | 10.1101/482349 | E003 |
| L004 | True | 0.6 | crossref | 2020 | Identités numériques sur facebook : idiolectes et postures en question | 10.4000/corela.12517 | E004 |
| L005 | True | 0.597 | crossref | 2020 | Dana-Farber/Harvard Cancer Center | 10.32388/m0n6zf | E023 |
| L006 | True | 0.567 | arxiv | 2021 | The Modern Mathematics of Deep Learning |  | E005 |
| L007 | False | 0.52 | arxiv | 2021 | Technological Competence is a Precondition for Effective Implementation of Virtual Reality Head Mounted Displays in Human Neuroscience: A Technological Review and Meta-analysis |  | E006 |
| L008 | False | 0.517 | openalex | 2017 | Global, regional, and national incidence, prevalence, and years lived with disability for 328 diseases and injuries for 195 countries, 1990–2016: a systematic analysis for the Global Burden of Disease Study 2016 | 10.1016/s0140-6736(17)32154-2 | E007 |
| L009 | False | 0.517 | openalex | 2018 | Global, regional, and national incidence, prevalence, and years lived with disability for 354 diseases and injuries for 195 countries and territories, 1990–2017: a systematic analysis for the Global Burden of Disease Study 2017 | 10.1016/s0140-6736(18)32279-7 | E008 |
| L010 | False | 0.517 | crossref | 2023 | The Brief Observation of Social Communication Change (BOSCC): Procedures, Strengths, Limitations, and Future Directions | 10.47739/2641-774x.paediatricpathology.1026 | E024 |
| L011 | False | 0.5 | openalex | 2022 | Particle Swarm Optimization Algorithm and Its Applications: A Systematic Review | 10.1007/s11831-021-09694-4 | E009 |
| L012 | False | 0.497 | arxiv | 2023 | Learn to Accumulate Evidence from All Training Samples: Theory and Practice |  | E010 |

## Boundary And Failure Handling

- Missing DOI/title matches are labeled Red.
- Existing papers with weak or abstract-only support are labeled Yellow.
- Green requires both metadata match and concrete support from title/abstract/snippet.
- API failures are preserved in tool_calls.jsonl and do not become fabricated evidence.