#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.verifier_params import load_verifier_params


DEFAULT_LABELS = ROOT / "submission" / "audit_labels" / "manual_gold_labels.csv"
DEFAULT_PARAMS = ROOT / "configs" / "verifier_params.json"
DEFAULT_OUT = ROOT / "outputs" / "param_optimization" / "evaluation_report.json"


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def parse_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def authoritative_doi_lookup(row: dict[str, str]) -> bool:
    return row.get("verification_method", "").endswith("_doi") and row.get("doi", "").lower().startswith("10.")


def predict_color(row: dict[str, str], params: dict[str, Any]) -> tuple[str, str]:
    exists = row.get("exists_status", "")
    metadata = row.get("metadata_match_status", "")
    support = row.get("support_status", "")
    error_type = row.get("error_type", "")
    source_type = row.get("support_source_type", "")
    extraction_risk = row.get("input_extraction_risk", "")
    year_match = parse_bool(row.get("year_match"))
    support_score = parse_float(row.get("support_score"))
    source_agreement = parse_int(row.get("source_agreement_count"), 1)
    supporting_sentence_present = parse_bool(row.get("supporting_sentence_present"))
    version_status = row.get("version_match_status", "")

    if error_type in {"invalid_doi", "not_found", "doi_metadata_mismatch", "title_mismatch", "author_mismatch"}:
        return "Red", error_type
    if exists == "not_found":
        return "Red", "not_found"
    if exists == "unknown" or error_type == "api_inconclusive":
        return "Yellow", "api_inconclusive"
    if metadata == "mismatch":
        return "Red", "metadata_mismatch"
    if not year_match or error_type in {"year_mismatch_requires_review", "version_year_mismatch"}:
        return "Yellow", error_type or "year_mismatch_requires_review"
    if support == "not_supported":
        return "Red", "not_supported"

    input_pdf_allowed = bool(params["allow_input_pdf_fulltext_green"])
    risky_cap = bool(params["cap_green_when_input_extraction_risky"])
    can_use_source = source_type != "input_pdf_fulltext" or input_pdf_allowed
    enough_sources = source_agreement >= int(params["green_min_source_agreement"]) or authoritative_doi_lookup(row)
    enough_support = support_score >= float(params["support_score_green_min"])
    green_gate = (
        metadata == "match"
        and support == "supports"
        and supporting_sentence_present
        and can_use_source
        and enough_sources
        and enough_support
        and version_status != "version_year_mismatch"
        and not (risky_cap and extraction_risk == "risky")
    )
    if green_gate:
        return "Green", "green_gate_passed"
    return "Yellow", error_type or "insufficient_green_gate"


def score_prediction(predicted: str, human: str, params: dict[str, Any]) -> int:
    if predicted == human:
        return int(params.get(f"correct_{human.lower()}_reward", 2))
    if predicted == "Green" and human != "Green":
        return int(params["false_green_penalty"])
    if predicted == "Red" and human != "Red":
        return int(params["wrong_red_penalty"])
    if predicted == "Yellow" and human == "Green":
        return int(params["yellow_when_green_penalty"])
    if predicted == "Yellow" and human == "Red":
        return int(params["yellow_when_red_penalty"])
    return -1


def evaluate(rows: list[dict[str, str]], params: dict[str, Any]) -> dict[str, Any]:
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    details: list[dict[str, Any]] = []
    reward = 0
    for row in rows:
        predicted, rule_reason = predict_color(row, params)
        human = row.get("human_color", "")
        item_reward = score_prediction(predicted, human, params)
        reward += item_reward
        confusion[human][predicted] += 1
        details.append(
            {
                "source_run": row.get("source_run", ""),
                "case_id": row.get("case_id", ""),
                "claim_id": row.get("claim_id", ""),
                "system_color": row.get("system_color", ""),
                "human_color": human,
                "predicted_color": predicted,
                "rule_reason": rule_reason,
                "reward": item_reward,
                "human_reason": row.get("human_reason", ""),
            }
        )
    correct = sum(1 for item in details if item["predicted_color"] == item["human_color"])
    false_green = sum(1 for item in details if item["predicted_color"] == "Green" and item["human_color"] != "Green")
    wrong_red = sum(1 for item in details if item["predicted_color"] == "Red" and item["human_color"] != "Red")
    return {
        "label_count": len(rows),
        "accuracy": round(correct / len(rows), 4) if rows else 0.0,
        "reward": reward,
        "false_green_count": false_green,
        "wrong_red_count": wrong_red,
        "human_distribution": dict(Counter(row.get("human_color", "") for row in rows)),
        "predicted_distribution": dict(Counter(item["predicted_color"] for item in details)),
        "confusion": {human: dict(counter) for human, counter in confusion.items()},
        "details": details,
    }


def write_outputs(result: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    detail_path = out_path.with_suffix(".details.csv")
    fieldnames = [
        "source_run",
        "case_id",
        "claim_id",
        "system_color",
        "human_color",
        "predicted_color",
        "rule_reason",
        "reward",
        "human_reason",
    ]
    with detail_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(result["details"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate verifier parameters against manual gold labels.")
    parser.add_argument("--labels", default=str(DEFAULT_LABELS))
    parser.add_argument("--params", default=str(DEFAULT_PARAMS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = load_rows(Path(args.labels))
    params = load_verifier_params(args.params)
    result = evaluate(rows, params)
    result["params_path"] = str(Path(args.params).resolve())
    result["labels_path"] = str(Path(args.labels).resolve())
    write_outputs(result, Path(args.out))
    print(f"labels={result['label_count']} accuracy={result['accuracy']} reward={result['reward']}")
    print(f"false_green={result['false_green_count']} wrong_red={result['wrong_red_count']}")
    print(f"wrote {Path(args.out).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
