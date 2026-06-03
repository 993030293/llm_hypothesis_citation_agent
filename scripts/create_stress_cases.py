#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.utils import write_json


def _draw_lines(c: canvas.Canvas, lines: list[str], x: int, y: int, leading: int = 15) -> None:
    for line in lines:
        c.drawString(x, y, line)
        y -= leading


def _pdf(path: Path, title: str, lines: list[tuple[int, int, list[str]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle(title)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, 735, title)
    c.setFont("Helvetica", 10)
    for x, y, block_lines in lines:
        _draw_lines(c, block_lines, x, y)
    c.save()


def build_cases(root: Path) -> list[dict[str, Any]]:
    papers = root / "papers"
    cases: list[dict[str, Any]] = []

    specs = [
        {
            "case_id": "keywords_before_abstract",
            "discipline": "finance",
            "layout_type": "keywords_before_abstract",
            "expected_keyword_source": "declared",
            "expected_readiness": "ready",
            "expected_keywords": ["agent-based modeling", "financial market simulation", "calibration", "scalability"],
            "title": "MarketSimX: Agent-Based Financial Market Simulation",
            "blocks": [
                (72, 705, ["ARTICLE INFO", "Keywords:", "Agent-based modeling", "financial market simulation", "calibration", "scalability"]),
                (
                    300,
                    705,
                    [
                        "ABSTRACT",
                        "This paper studies agent-based financial market simulation for stress testing and",
                        "counterfactual policy evaluation. The simulator calibrates heterogeneous trading",
                        "agents against limit order book traces and supports regulatory intervention tests.",
                        "1. Introduction",
                        "Financial markets require robust simulation tools for systemic risk analysis.",
                    ],
                ),
            ],
        },
        {
            "case_id": "abstract_before_keywords",
            "discipline": "biomedicine",
            "layout_type": "abstract_before_keywords",
            "expected_keyword_source": "declared",
            "expected_readiness": "ready",
            "expected_keywords": ["protein design", "antibody discovery", "molecular docking"],
            "title": "Cross-Modal Protein Design for Antibody Discovery",
            "blocks": [
                (
                    72,
                    705,
                    [
                        "Abstract. This paper investigates cross-modal protein design for antibody discovery.",
                        "The method links sequence representations, molecular docking signals, and wet-lab",
                        "screening outcomes to prioritize candidates under limited biological assays.",
                        "Keywords: protein design; antibody discovery; molecular docking; active learning",
                        "1. Introduction",
                        "Biological design tasks require reliable links between model predictions and evidence.",
                    ],
                ),
            ],
        },
        {
            "case_id": "no_declared_keywords",
            "discipline": "social_science",
            "layout_type": "no_declared_keywords",
            "expected_keyword_source": "inferred",
            "expected_readiness": "ready",
            "expected_keywords": ["misinformation", "public trust", "survey"],
            "title": "Public Trust and Misinformation Exposure in Online Communities",
            "blocks": [
                (
                    72,
                    705,
                    [
                        "Abstract. This study examines misinformation exposure, public trust, and civic",
                        "participation in online communities. We combine survey evidence with network",
                        "features to identify conditions under which misinformation changes institutional",
                        "trust and health information behavior.",
                        "1. Introduction",
                        "Digital platforms shape public reasoning and social coordination.",
                    ],
                ),
            ],
        },
        {
            "case_id": "index_terms_style",
            "discipline": "computer_science",
            "layout_type": "index_terms_style",
            "expected_keyword_source": "declared",
            "expected_readiness": "ready",
            "expected_keywords": ["retrieval augmented generation", "citation verification", "large language models"],
            "title": "Citation-Aware Retrieval-Augmented Generation for Scientific Writing",
            "blocks": [
                (
                    72,
                    705,
                    [
                        "Abstract. Retrieval-augmented generation can improve scientific writing when",
                        "retrieved documents are checked against generated claims and citation metadata.",
                        "Index Terms: retrieval augmented generation; citation verification; large language models",
                        "1. Introduction",
                        "Scientific writing agents need robust attribution and evidence tracking.",
                    ],
                ),
            ],
        },
        {
            "case_id": "metadata_only_or_weak_text",
            "discipline": "engineering",
            "layout_type": "metadata_only_or_weak_text",
            "expected_keyword_source": "inferred",
            "expected_readiness": "usable_with_caution",
            "expected_keywords": ["sensor calibration"],
            "title": "Sensor Calibration Notes",
            "blocks": [(72, 705, ["Short note on sensor calibration and drift."])],
        },
        {
            "case_id": "two_column_misaligned",
            "discipline": "climate_science",
            "layout_type": "two_column_misaligned",
            "expected_keyword_source": "declared",
            "expected_readiness": "ready",
            "expected_keywords": ["urban heat island", "climate adaptation", "remote sensing"],
            "title": "Remote Sensing for Urban Heat Island Adaptation",
            "blocks": [
                (72, 705, ["Keywords:", "urban heat island", "climate adaptation", "remote sensing", "thermal imagery"]),
                (
                    310,
                    705,
                    [
                        "ABSTRACT",
                        "Remote sensing measurements can identify urban heat island exposure and guide",
                        "climate adaptation policies. We compare thermal imagery, land cover features,",
                        "and neighborhood vulnerability indicators across metropolitan regions.",
                        "1. Introduction",
                    ],
                ),
            ],
        },
        {
            "case_id": "scanned_or_low_text",
            "discipline": "unknown",
            "layout_type": "scanned_or_low_text",
            "expected_keyword_source": "missing",
            "expected_readiness": "risky",
            "expected_keywords": [],
            "title": "Scanned Article Placeholder",
            "blocks": [(72, 705, ["SCAN PAGE"])],
        },
        {
            "case_id": "cross_domain",
            "discipline": "robotics_healthcare",
            "layout_type": "cross_domain",
            "expected_keyword_source": "declared",
            "expected_readiness": "ready",
            "expected_keywords": ["robotic rehabilitation", "clinical decision support", "human-in-the-loop"],
            "title": "Human-in-the-Loop Robotic Rehabilitation with Clinical Decision Support",
            "blocks": [
                (
                    72,
                    705,
                    [
                        "Abstract. This paper connects robotic rehabilitation, clinical decision support,",
                        "and human-in-the-loop adaptation. The system personalizes therapy intensity using",
                        "patient response signals and clinician feedback.",
                        "Keywords: robotic rehabilitation; clinical decision support; human-in-the-loop; adaptive control",
                        "1. Introduction",
                    ],
                ),
            ],
        },
    ]

    for spec in specs:
        pdf_path = papers / f"{spec['case_id']}.pdf"
        _pdf(pdf_path, spec["title"], spec["blocks"])
        manifest = {
            "case_id": spec["case_id"],
            "pdf_path": str(pdf_path.relative_to(ROOT)),
            "source_type": "synthetic_parser_stress_fixture",
            "source_note": "Generated locally to test PDF layout and extraction behavior; not claimed as a real published paper.",
            "discipline": spec["discipline"],
            "layout_type": spec["layout_type"],
            "expected_keyword_source": spec["expected_keyword_source"],
            "expected_keywords": spec["expected_keywords"],
            "expected_readiness": spec["expected_readiness"],
            "online_audit": spec["case_id"] != "scanned_or_low_text",
            "demo_command": f"python agent/workflow.py --pdf {pdf_path.relative_to(ROOT)} --task \"Stress audit case {spec['case_id']}\"",
        }
        write_json(root / f"{spec['case_id']}.json", manifest)
        cases.append(manifest)

    evomarket = ROOT / "inputs" / "papers" / "EvoMarket.pdf"
    if evomarket.exists():
        target = papers / "real_evomarket.pdf"
        shutil.copyfile(evomarket, target)
        manifest = {
            "case_id": "real_evomarket",
            "pdf_path": str(target.relative_to(ROOT)),
            "source_type": "local_real_pdf",
            "source_note": "Real local PDF supplied by the user for live testing.",
            "discipline": "finance",
            "layout_type": "keywords_before_abstract_two_column",
            "expected_keyword_source": "declared",
            "expected_keywords": [
                "agent-based modeling",
                "financial market simulation",
                "calibration",
                "scalability",
                "multi-agent systems",
                "simulation fidelity",
            ],
            "expected_readiness": "ready",
            "online_audit": True,
            "demo_command": f"python agent/workflow.py --pdf {target.relative_to(ROOT)} --task \"Stress audit case real_evomarket\"",
        }
        write_json(root / "real_evomarket.json", manifest)
        cases.append(manifest)

    write_json(root / "stress_cases_manifest.json", {"cases": cases})
    return cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create local stress-audit PDF fixtures and manifests.")
    parser.add_argument("--output-dir", default=str(ROOT / "inputs" / "stress_cases"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    cases = build_cases(output_dir)
    print(f"Created {len(cases)} stress cases under {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
