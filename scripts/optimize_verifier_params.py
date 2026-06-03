#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import itertools
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.verifier_params import load_verifier_params
from scripts.evaluate_verifier_params import DEFAULT_LABELS, DEFAULT_PARAMS, evaluate, load_rows


DEFAULT_OUT_DIR = ROOT / "outputs" / "param_optimization"


def candidate_grid(base: dict[str, Any]) -> list[dict[str, Any]]:
    support_score_values = [0.32, 0.42, 0.55, 0.7]
    source_agreement_values = [1, 2]
    allow_input_values = [False, True]
    risky_cap_values = [True, False]
    title_match_values = [0.82, 0.86, 0.9]
    candidates = []
    for support_score, source_agreement, allow_input, risky_cap, title_match in itertools.product(
        support_score_values,
        source_agreement_values,
        allow_input_values,
        risky_cap_values,
        title_match_values,
    ):
        params = dict(base)
        params.update(
            {
                "support_score_green_min": support_score,
                "green_min_source_agreement": source_agreement,
                "allow_input_pdf_fulltext_green": allow_input,
                "cap_green_when_input_extraction_risky": risky_cap,
                "title_match_threshold": title_match,
            }
        )
        candidates.append(params)
    return candidates


def rank_key(result: dict[str, Any]) -> tuple[int, int, float, int, int, int, float, float]:
    params = result["params"]
    return (
        -int(result["false_green_count"]),
        -int(result["wrong_red_count"]),
        float(result["reward"]),
        int(round(float(result["accuracy"]) * 10000)),
        int(params["green_min_source_agreement"]),
        1 if not bool(params["allow_input_pdf_fulltext_green"]) else 0,
        float(params["support_score_green_min"]),
        float(params["title_match_threshold"]),
    )


def write_report(best: dict[str, Any], out_dir: Path, rows: list[dict[str, str]]) -> None:
    lines = [
        "# Verifier Parameter Optimization Report",
        "",
        "This is an offline parameter search over manually reviewed citation labels. It does not call an LLM or any external API.",
        "",
        "## Best Result",
        "",
        f"- Manual labels: {len(rows)}",
        f"- Accuracy: {best['accuracy']}",
        f"- Reward: {best['reward']}",
        f"- False Green count: {best['false_green_count']}",
        f"- Wrong Red count: {best['wrong_red_count']}",
        f"- Predicted distribution: {best['predicted_distribution']}",
        "",
        "## Selected Parameters",
        "",
        "```json",
        json.dumps(best["params"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## Human Review Principle",
        "",
        "- False Green is penalized most heavily.",
        "- Year mismatch is Yellow when title/author/DOI still identify the same work.",
        "- Input-PDF-only support stays Yellow by default.",
        "- Risky PDF extraction caps Green to Yellow for classroom-safe reporting.",
    ]
    (out_dir / "optimization_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grid-search verifier parameters using manual gold labels.")
    parser.add_argument("--labels", default=str(DEFAULT_LABELS))
    parser.add_argument("--base-params", default=str(DEFAULT_PARAMS))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = load_rows(Path(args.labels))
    base = load_verifier_params(args.base_params)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for params in candidate_grid(base):
        result = evaluate(rows, params)
        result["params"] = params
        results.append(result)
    results.sort(key=rank_key, reverse=True)
    best = results[0]

    result_csv = out_dir / "optimization_results.csv"
    with result_csv.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "rank",
            "accuracy",
            "reward",
            "false_green_count",
            "wrong_red_count",
            "support_score_green_min",
            "green_min_source_agreement",
            "allow_input_pdf_fulltext_green",
            "cap_green_when_input_extraction_risky",
            "title_match_threshold",
            "predicted_distribution",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for idx, result in enumerate(results, start=1):
            params = result["params"]
            writer.writerow(
                {
                    "rank": idx,
                    "accuracy": result["accuracy"],
                    "reward": result["reward"],
                    "false_green_count": result["false_green_count"],
                    "wrong_red_count": result["wrong_red_count"],
                    "support_score_green_min": params["support_score_green_min"],
                    "green_min_source_agreement": params["green_min_source_agreement"],
                    "allow_input_pdf_fulltext_green": params["allow_input_pdf_fulltext_green"],
                    "cap_green_when_input_extraction_risky": params["cap_green_when_input_extraction_risky"],
                    "title_match_threshold": params["title_match_threshold"],
                    "predicted_distribution": json.dumps(result["predicted_distribution"], ensure_ascii=False),
                }
            )

    optimized_path = out_dir / "optimized_verifier_params.json"
    optimized_path.write_text(json.dumps(best["params"], indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "best_evaluation.json").write_text(json.dumps(best, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(best, out_dir, rows)

    print(f"evaluated={len(results)} best_accuracy={best['accuracy']} best_reward={best['reward']}")
    print(f"false_green={best['false_green_count']} wrong_red={best['wrong_red_count']}")
    print(f"wrote {optimized_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
