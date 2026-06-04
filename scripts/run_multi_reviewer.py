#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.research_memory import ResearchMemory


@dataclass(frozen=True)
class ReviewerConfig:
    reviewer_id: str
    role: str
    env_var: str
    model: str
    focus: str


REVIEWERS = [
    ReviewerConfig(
        "R1",
        "novelty_reviewer",
        "DEEPSEEK_REVIEWER_1_API_KEY",
        "deepseek-v4-flash",
        "Judge whether the hypothesis is genuinely new or only a restatement of retrieved work.",
    ),
    ReviewerConfig(
        "R2",
        "evidence_reviewer",
        "DEEPSEEK_REVIEWER_2_API_KEY",
        "deepseek-v4-pro",
        "Judge whether the idea relies on Green/Yellow/Red citations appropriately.",
    ),
    ReviewerConfig(
        "R3",
        "methodology_reviewer",
        "DEEPSEEK_REVIEWER_3_API_KEY",
        "deepseek-v4-flash",
        "Judge whether the hypothesis is testable and whether the experiment plan is realistic.",
    ),
    ReviewerConfig(
        "R4",
        "risk_reviewer",
        "DEEPSEEK_REVIEWER_4_API_KEY",
        "deepseek-v4-pro",
        "Find over-strong claims, weak cross-domain analogies, citation risks, and tool failures.",
    ),
]

META_MODEL = "deepseek-v4-pro"
META_ENV_VAR = "DEEPSEEK_META_REVIEWER_API_KEY"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
RED_LINE_ERROR_TYPES = {
    "not_found",
    "invalid_doi",
    "doi_metadata_mismatch",
    "title_mismatch",
    "author_mismatch",
    "numeric_or_condition_contradiction",
}
CAP_ERROR_TYPES = {
    "claim_too_strong",
    "critical_terms_missing",
    "numeric_or_condition_contradiction",
    "supporting_sentence_missing",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a multi-reviewer panel over a citation audit run.",
    )
    parser.add_argument("--audit-run-dir", required=True)
    parser.add_argument("--quest-root", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--review-mode",
        choices=("auto", "deepseek", "deterministic"),
        default="auto",
        help="auto uses DeepSeek when the reviewer key exists, otherwise deterministic fallback.",
    )
    parser.add_argument("--deepseek-base-url", default=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--reviewer-timeout-seconds", type=int, default=90)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    status = run_multi_review(args)
    print(f"Multi-review complete: {status['out_dir']}")
    print(
        "Reviewer sources: "
        + ", ".join(f"{item['reviewer_id']}={item.get('review_source', 'unknown')}" for item in status["reviews"])
    )
    return 0


def run_multi_review(args: argparse.Namespace) -> dict[str, Any]:
    audit_dir = Path(args.audit_run_dir).resolve()
    quest_root = Path(args.quest_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    tool_log = out_dir / "multi_reviewer_tool_calls.jsonl"
    rows = load_csv(audit_dir / "citation_verification.csv")
    chain_rows = load_csv(audit_dir / "evidence_chain.csv")
    tool_rows = load_jsonl(audit_dir / "tool_calls.jsonl")
    provider_rows = load_jsonl(audit_dir / "provider_verification.jsonl")
    claims_payload = load_json(audit_dir / "input_claims.json")
    memory_summary = check_memory(rows)
    memory_hits = memory_summary.get("citation_hits", [])

    log_tool(tool_log, "load_artifact", {"path": str(audit_dir / "citation_verification.csv")}, {"rows": len(rows)})
    log_tool(tool_log, "load_artifact", {"path": str(audit_dir / "evidence_chain.csv")}, {"rows": len(chain_rows)})
    log_tool(tool_log, "load_artifact", {"path": str(audit_dir / "tool_calls.jsonl")}, {"rows": len(tool_rows)})
    label_summary = summarize_labels(rows)
    log_tool(tool_log, "summarize_citation_labels", {}, label_summary)
    evidence_summary = summarize_evidence_chain(chain_rows)
    log_tool(tool_log, "extract_evidence_chain", {}, evidence_summary)
    provider_summary = summarize_provider_errors(provider_rows, tool_rows)
    log_tool(tool_log, "summarize_provider_errors", {}, provider_summary)
    log_tool(tool_log, "check_memory", {}, memory_summary)

    context = {
        "audit_dir": str(audit_dir),
        "quest_root": str(quest_root),
        "label_summary": label_summary,
        "evidence_summary": evidence_summary,
        "provider_summary": provider_summary,
        "memory_hit_count": len(memory_hits),
        "memory_hits": memory_hits[:8],
        "memory_summary": memory_summary,
        "claims_count": len(rows),
        "hypotheses_count": count_hypotheses(claims_payload, rows),
        "claims_preview": build_claims_preview(rows),
        "review_mode": args.review_mode,
        "deepseek_base_url": args.deepseek_base_url,
    }

    reviews = [
        build_review_with_optional_deepseek(config, context, rows, args, tool_log)
        for config in REVIEWERS
    ]
    write_jsonl(out_dir / "reviewer_scores.jsonl", reviews)

    meta = build_meta_decision_with_optional_deepseek(reviews, label_summary, context, args, tool_log)
    (out_dir / "meta_decision.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "multi_review_report.md").write_text(render_report(reviews, meta, context), encoding="utf-8")
    status = {
        "out_dir": str(out_dir),
        "reviews": reviews,
        "meta": meta,
        "label_summary": label_summary,
    }
    (out_dir / "multi_review_status.json").write_text(json.dumps(safe_for_logs(status), indent=2, ensure_ascii=False), encoding="utf-8")
    return status


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def log_tool(path: Path, tool_name: str, args: dict[str, Any], result: dict[str, Any], status: str = "success") -> None:
    entry = {
        "tool_name": tool_name,
        "args": safe_for_logs(args),
        "status": status,
        "result": safe_for_logs(result),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def int_field(value: Any) -> int:
    try:
        return int(float(str(value).strip() or "0"))
    except Exception:
        return 0


def summarize_labels(rows: list[dict[str, str]]) -> dict[str, Any]:
    counts = {"Green": 0, "Yellow": 0, "Red": 0}
    error_types: dict[str, int] = {}
    green_gate_passed = 0
    manual_review = 0
    risk_penalty_total = 0
    red_line_count = 0
    missing_critical_terms_count = 0
    for row in rows:
        label = row.get("color_label", "")
        if label in counts:
            counts[label] += 1
        error_type = row.get("error_type", "") or "none"
        error_types[error_type] = error_types.get(error_type, 0) + 1
        risk_penalty_total += int_field(row.get("risk_penalty", 0))
        if error_type in RED_LINE_ERROR_TYPES or row.get("contradiction_type"):
            red_line_count += 1
        if row.get("missing_critical_terms"):
            missing_critical_terms_count += 1
        if str(row.get("green_gate_passed", "")).lower() == "true":
            green_gate_passed += 1
        if str(row.get("manual_review_required", "")).lower() == "true" or row.get("manual_review_action"):
            manual_review += 1
    total = len(rows)
    summary = {
        "green": counts["Green"],
        "yellow": counts["Yellow"],
        "red": counts["Red"],
        "total": total,
        "error_types": error_types,
        "green_gate_passed": green_gate_passed,
        "manual_review_count": manual_review,
        "risk_penalty_total": risk_penalty_total,
        "red_line_count": red_line_count,
        "missing_critical_terms_count": missing_critical_terms_count,
        "yellow_ratio": round(counts["Yellow"] / total, 3) if total else 0.0,
    }
    cap, breakdown, red_line_triggered = deterministic_score_cap(summary)
    summary["deterministic_score_cap"] = cap
    summary["penalty_breakdown"] = breakdown
    summary["red_line_triggered"] = red_line_triggered
    return summary


def deterministic_score_cap(labels: dict[str, Any]) -> tuple[int, list[dict[str, Any]], bool]:
    cap = 6
    breakdown: list[dict[str, Any]] = []
    red_line_triggered = False
    total = max(1, int(labels.get("total") or 0))
    yellow_ratio = float(labels.get("yellow", 0)) / total
    error_types = labels.get("error_types", {}) or {}
    if int(labels.get("red", 0)) > 0:
        cap = min(cap, 2)
        red_line_triggered = True
        breakdown.append({"rule": "any_red_claim", "cap": 2, "reason": "At least one citation is Red."})
    if int(labels.get("red_line_count", 0)) > 0:
        cap = min(cap, 2)
        red_line_triggered = True
        breakdown.append({"rule": "red_line_error_type", "cap": 2, "reason": "A hard citation error or contradiction was detected."})
    if yellow_ratio > 0.5:
        cap = min(cap, 3)
        breakdown.append({"rule": "yellow_majority", "cap": 3, "reason": f"Yellow ratio is {yellow_ratio:.2f}."})
    if int(labels.get("green", 0)) == 0:
        cap = min(cap, 3)
        breakdown.append({"rule": "no_green_claims", "cap": 3, "reason": "No citation passed the strict Green gate."})
    cap_error_hits = {name: count for name, count in error_types.items() if name in CAP_ERROR_TYPES and count}
    if cap_error_hits:
        cap = min(cap, 3)
        breakdown.append(
            {
                "rule": "support_risk_error_types",
                "cap": 3,
                "reason": "Support-risk errors exist: "
                + ", ".join(f"{name}={count}" for name, count in sorted(cap_error_hits.items())),
            }
        )
    if int(labels.get("risk_penalty_total", 0)) >= 3:
        cap = min(cap, 4)
        breakdown.append(
            {
                "rule": "risk_penalty_total",
                "cap": 4,
                "reason": f"Total deterministic risk penalty is {labels.get('risk_penalty_total')}.",
            }
        )
    return cap, breakdown, red_line_triggered


def summarize_evidence_chain(rows: list[dict[str, str]]) -> dict[str, Any]:
    categories: dict[str, int] = {}
    evidence_ids: set[str] = set()
    tool_ids: set[str] = set()
    manual_review = 0
    for row in rows:
        category = row.get("support_category", "") or "unknown"
        categories[category] = categories.get(category, 0) + 1
        for value in str(row.get("verification_evidence_id", "")).split(";"):
            if value.strip():
                evidence_ids.add(value.strip())
        for value in str(row.get("tool_call_ids", "")).replace(",", ";").split(";"):
            if value.strip():
                tool_ids.add(value.strip())
        if str(row.get("manual_review_required", "")).lower() == "true":
            manual_review += 1
    return {
        "support_categories": categories,
        "evidence_id_count": len(evidence_ids),
        "tool_call_id_count": len(tool_ids),
        "manual_review_count": manual_review,
    }


def summarize_provider_errors(provider_rows: list[dict[str, Any]], tool_rows: list[dict[str, Any]]) -> dict[str, Any]:
    providers: dict[str, dict[str, int]] = {}
    for row in provider_rows:
        provider = str(row.get("provider") or row.get("retrieval_source") or "unknown")
        status = str(row.get("status") or row.get("exists_status") or "unknown")
        providers.setdefault(provider, {})
        providers[provider][status] = providers[provider].get(status, 0) + 1
    tool_errors = 0
    for row in tool_rows:
        status = str(row.get("status") or "")
        if status.lower() in {"error", "failed", "timeout"} or row.get("error"):
            tool_errors += 1
    return {"providers": providers, "tool_error_count": tool_errors, "provider_rows": len(provider_rows)}


def check_memory(rows: list[dict[str, str]]) -> dict[str, Any]:
    return ResearchMemory().summarize_for_review(rows)


def normalize_title(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def count_hypotheses(payload: dict[str, Any], rows: list[dict[str, str]]) -> int:
    hypotheses = payload.get("hypotheses")
    if isinstance(hypotheses, list) and hypotheses:
        return len(hypotheses)
    ids = {row.get("hypothesis_id", "") for row in rows if row.get("hypothesis_id")}
    return len(ids)


def build_claims_preview(rows: list[dict[str, str]], limit: int = 8) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for row in rows[:limit]:
        preview.append(
            {
                "claim_id": row.get("claim_id", ""),
                "hypothesis_id": row.get("hypothesis_id", ""),
                "claim_text": row.get("claim_text", "")[:500],
                "cited_title": row.get("cited_title", ""),
                "doi": row.get("doi", ""),
                "color_label": row.get("color_label", ""),
                "error_type": row.get("error_type", ""),
                "support_status": row.get("support_status", ""),
                "supporting_sentence": row.get("supporting_sentence", "")[:500],
                "reason": row.get("reason", "")[:500],
            }
        )
    return preview


def build_review_with_optional_deepseek(
    config: ReviewerConfig,
    context: dict[str, Any],
    rows: list[dict[str, str]],
    args: argparse.Namespace,
    tool_log: Path,
) -> dict[str, Any]:
    fallback = build_review(config.reviewer_id, config.role, context, rows)
    fallback.update(
        {
            "model": "deterministic",
            "review_source": "deterministic",
            "fallback_reason": "",
        }
    )
    if args.review_mode == "deterministic":
        return fallback

    api_key = os.environ.get(config.env_var, "").strip()
    if not api_key:
        fallback["fallback_reason"] = f"missing_env:{config.env_var}"
        if args.review_mode == "deepseek":
            fallback["review_source"] = "deterministic_fallback"
        log_tool(
            tool_log,
            "deepseek_reviewer_call",
            {"reviewer_id": config.reviewer_id, "model": config.model, "env_var": config.env_var, "key_configured": False},
            {"fallback_reason": fallback["fallback_reason"]},
            status="skipped",
        )
        return fallback

    started = time.time()
    try:
        prompt = build_reviewer_prompt(config, context, fallback)
        raw = call_deepseek_json(
            api_key=api_key,
            base_url=args.deepseek_base_url,
            model=config.model,
            messages=prompt,
            temperature=args.temperature,
            timeout_seconds=args.reviewer_timeout_seconds,
        )
        review = normalize_reviewer_json(raw, config, fallback)
        review.update({"model": config.model, "review_source": "deepseek", "fallback_reason": ""})
        log_tool(
            tool_log,
            "deepseek_reviewer_call",
            {
                "reviewer_id": config.reviewer_id,
                "model": config.model,
                "env_var": config.env_var,
                "key_configured": True,
            },
            {"status": "parsed_json", "duration_seconds": round(time.time() - started, 3)},
        )
        return review
    except Exception as exc:  # pragma: no cover - external API failure path
        fallback["review_source"] = "deterministic_fallback"
        fallback["fallback_reason"] = f"{type(exc).__name__}: {str(exc)[:180]}"
        log_tool(
            tool_log,
            "deepseek_reviewer_call",
            {
                "reviewer_id": config.reviewer_id,
                "model": config.model,
                "env_var": config.env_var,
                "key_configured": True,
            },
            {"fallback_reason": fallback["fallback_reason"], "duration_seconds": round(time.time() - started, 3)},
            status="error",
        )
        return fallback


def build_reviewer_prompt(
    config: ReviewerConfig,
    context: dict[str, Any],
    deterministic_anchor: dict[str, Any],
) -> list[dict[str, Any]]:
    payload = {
        "role": config.role,
        "focus": config.focus,
        "label_summary": context["label_summary"],
        "evidence_summary": context["evidence_summary"],
        "provider_summary": context["provider_summary"],
        "memory_hit_count": context["memory_hit_count"],
        "memory_hits": context["memory_hits"],
        "memory_summary": context["memory_summary"],
        "claims_preview": context["claims_preview"],
        "deterministic_anchor": deterministic_anchor,
    }
    system = (
        "You are one reviewer in a scientific multi-reviewer panel. "
        "You evaluate idea quality and citation risk only. "
        "Do not change Green/Yellow/Red labels; they are produced by deterministic code. "
        "Return one strict JSON object and no markdown."
    )
    user = (
        "Review this citation-audited research idea package. "
        "Use only the provided artifact summaries and evidence IDs. "
        "Output JSON with exactly these keys: reviewer_id, role, score_1_to_6, strengths, weaknesses, "
        "required_revision, evidence_ids_used, tool_calls_used, confidence.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_deepseek_json(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    timeout_seconds: int,
) -> dict[str, Any]:
    import httpx
    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout_seconds,
        http_client=httpx.Client(proxy=None, trust_env=False, follow_redirects=True, timeout=timeout_seconds),
    )
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or ""
    return parse_json_object(content)


def parse_json_object(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if not text:
        raise ValueError("empty_model_response")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("model_response_not_object")
    return value


def normalize_reviewer_json(
    raw: dict[str, Any],
    config: ReviewerConfig,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    reviewer_id = str(raw.get("reviewer_id") or config.reviewer_id)
    role = str(raw.get("role") or config.role)
    if reviewer_id != config.reviewer_id:
        reviewer_id = config.reviewer_id
    if role != config.role:
        role = config.role
    max_score = int(fallback.get("deterministic_role_cap") or 6)
    return {
        "reviewer_id": reviewer_id,
        "role": role,
        "score_1_to_6": min(clamp_score(raw.get("score_1_to_6"), fallback["score_1_to_6"]), max_score),
        "strengths": normalize_str_list(raw.get("strengths"), fallback["strengths"]),
        "weaknesses": normalize_str_list(raw.get("weaknesses"), fallback["weaknesses"]),
        "required_revision": normalize_str_list(raw.get("required_revision"), fallback["required_revision"]),
        "evidence_ids_used": normalize_str_list(raw.get("evidence_ids_used"), fallback["evidence_ids_used"]),
        "tool_calls_used": normalize_str_list(raw.get("tool_calls_used"), fallback["tool_calls_used"]),
        "confidence": normalize_confidence(raw.get("confidence"), fallback["confidence"]),
        "deterministic_role_cap": max_score,
    }


def clamp_score(value: Any, default: int) -> int:
    try:
        score = int(round(float(value)))
    except Exception:
        score = int(default)
    return max(1, min(6, score))


def reviewer_role_cap(role: str, labels: dict[str, Any]) -> int:
    if role not in {"evidence_reviewer", "risk_reviewer"}:
        return 6
    cap = 6
    if labels.get("red") or labels.get("red_line_triggered"):
        cap = min(cap, 2)
    if labels.get("missing_critical_terms_count") or any(
        name in CAP_ERROR_TYPES for name, count in (labels.get("error_types") or {}).items() if count
    ):
        cap = min(cap, 3)
    if float(labels.get("yellow_ratio") or 0.0) > 0.5:
        cap = min(cap, 3)
    return cap


def normalize_str_list(value: Any, default: list[Any]) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items[:12] if items else [str(item) for item in default]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return [str(item) for item in default]


def normalize_confidence(value: Any, default: str) -> str:
    confidence = str(value or "").strip().lower()
    if confidence in {"low", "medium", "high"}:
        return confidence
    return default if default in {"low", "medium", "high"} else "medium"


def build_review(reviewer_id: str, role: str, context: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, Any]:
    labels = context["label_summary"]
    total = max(1, labels["total"])
    green = labels["green"]
    yellow = labels["yellow"]
    red = labels["red"]
    role_cap = reviewer_role_cap(role, labels)
    evidence_ids = sorted({row.get("evidence_id", "") for row in rows if row.get("evidence_id")})[:8]
    tool_ids = sorted({row.get("verification_method", "") for row in rows if row.get("verification_method")})[:8]

    if role == "novelty_reviewer":
        score = 4 if context["hypotheses_count"] >= 2 else 3
        if red:
            score -= 1
        strengths = ["The idea set is generated from a real input paper and linked to retrieved related work."]
        weaknesses = ["Novelty is not independently proven; it is inferred from citation-backed idea cards."]
        revisions = ["Keep novelty wording conservative and avoid claiming the idea is unprecedented."]
    elif role == "evidence_reviewer":
        score = 2 + min(3, green) + (1 if yellow and not red else 0)
        if red:
            score = max(1, score - red)
        strengths = [f"All {total} claims passed through deterministic citation verification."]
        weaknesses = [f"Label distribution is Green={green}, Yellow={yellow}, Red={red}; Yellow claims require manual review."]
        revisions = ["Use only Green claims for strong presentation claims; explain Yellow as uncertain support."]
    elif role == "methodology_reviewer":
        score = 4 if total >= 2 else 3
        if labels["manual_review_count"] > total / 2:
            score -= 1
        strengths = ["The workflow produces auditable artifacts instead of a chat-only answer."]
        weaknesses = ["The generated hypotheses still need downstream experimental design before they become research results."]
        revisions = ["Add a minimal experiment plan for the selected hypothesis before treating it as actionable."]
    else:
        score = 4
        if yellow / total > 0.5:
            score -= 1
        if red:
            score -= min(2, red)
        strengths = ["The verifier is conservative and does not upgrade uncertain support to Green."]
        weaknesses = list(top_error_types(labels["error_types"]))
        if not weaknesses:
            weaknesses = ["No major verifier error type dominated this run."]
        revisions = ["During demo, explicitly state that Yellow means citation exists but support is not fully confirmed."]

    penalty_reasons = [item.get("reason", "") for item in labels.get("penalty_breakdown", []) if item.get("reason")]
    if penalty_reasons and role in {"evidence_reviewer", "risk_reviewer"}:
        weaknesses.extend(penalty_reasons[:3])
        revisions.append("Resolve deterministic citation penalties before using this as a success demo.")

    score = max(1, min(role_cap, min(6, int(score))))
    return {
        "reviewer_id": reviewer_id,
        "role": role,
        "score_1_to_6": score,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "required_revision": revisions,
        "evidence_ids_used": evidence_ids,
        "tool_calls_used": tool_ids,
        "confidence": "high" if total >= 3 else "medium",
        "deterministic_role_cap": role_cap,
    }


def top_error_types(error_types: dict[str, int]) -> list[str]:
    return [f"{name}: {count}" for name, count in sorted(error_types.items(), key=lambda item: item[1], reverse=True)[:3]]


def build_meta_decision_with_optional_deepseek(
    reviews: list[dict[str, Any]],
    labels: dict[str, Any],
    context: dict[str, Any],
    args: argparse.Namespace,
    tool_log: Path,
) -> dict[str, Any]:
    fallback = build_meta_decision(reviews, labels, context)
    fallback.update({"model": "deterministic", "review_source": "deterministic", "fallback_reason": ""})
    if args.review_mode == "deterministic":
        return fallback

    api_key = os.environ.get(META_ENV_VAR, "").strip() or os.environ.get("DEEPSEEK_REVIEWER_4_API_KEY", "").strip()
    if not api_key:
        fallback["fallback_reason"] = f"missing_env:{META_ENV_VAR}|DEEPSEEK_REVIEWER_4_API_KEY"
        if args.review_mode == "deepseek":
            fallback["review_source"] = "deterministic_fallback"
        log_tool(
            tool_log,
            "deepseek_meta_reviewer_call",
            {"model": META_MODEL, "env_var": f"{META_ENV_VAR}|DEEPSEEK_REVIEWER_4_API_KEY", "key_configured": False},
            {"fallback_reason": fallback["fallback_reason"]},
            status="skipped",
        )
        return fallback

    started = time.time()
    try:
        raw = call_deepseek_json(
            api_key=api_key,
            base_url=args.deepseek_base_url,
            model=META_MODEL,
            messages=build_meta_prompt(reviews, labels, context, fallback),
            temperature=args.temperature,
            timeout_seconds=args.reviewer_timeout_seconds,
        )
        meta = normalize_meta_json(raw, fallback)
        meta.update({"model": META_MODEL, "review_source": "deepseek", "fallback_reason": ""})
        log_tool(
            tool_log,
            "deepseek_meta_reviewer_call",
            {"model": META_MODEL, "env_var": f"{META_ENV_VAR}|DEEPSEEK_REVIEWER_4_API_KEY", "key_configured": True},
            {"status": "parsed_json", "duration_seconds": round(time.time() - started, 3)},
        )
        return meta
    except Exception as exc:  # pragma: no cover - external API failure path
        fallback["review_source"] = "deterministic_fallback"
        fallback["fallback_reason"] = f"{type(exc).__name__}: {str(exc)[:180]}"
        log_tool(
            tool_log,
            "deepseek_meta_reviewer_call",
            {"model": META_MODEL, "env_var": f"{META_ENV_VAR}|DEEPSEEK_REVIEWER_4_API_KEY", "key_configured": True},
            {"fallback_reason": fallback["fallback_reason"], "duration_seconds": round(time.time() - started, 3)},
            status="error",
        )
        return fallback


def build_meta_prompt(
    reviews: list[dict[str, Any]],
    labels: dict[str, Any],
    context: dict[str, Any],
    deterministic_anchor: dict[str, Any],
) -> list[dict[str, Any]]:
    payload = {
        "reviewer_scores": reviews,
        "label_summary": labels,
        "provider_summary": context["provider_summary"],
        "evidence_summary": context["evidence_summary"],
        "deterministic_anchor": deterministic_anchor,
    }
    system = (
        "You are the meta-reviewer for a scientific idea review panel. "
        "You may decide accept/revise/reject for demo readiness, but you must not change Green/Yellow/Red labels. "
        "Return one strict JSON object and no markdown."
    )
    user = (
        "Make a final decision from the four reviewer JSON objects and deterministic citation audit summary. "
        f"The final_score_1_to_6 must not exceed deterministic_score_cap={deterministic_anchor.get('deterministic_score_cap')}. "
        "If the cap is 2, the decision must be reject_or_boundary_case; if the cap is 3, it cannot be accept_for_demo. "
        "Output JSON with keys: final_score_1_to_6, decision, main_reason, must_fix_before_demo, "
        "citation_risk_summary, reviewer_agreement, deterministic_score_cap, penalty_breakdown, red_line_triggered.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def normalize_meta_json(raw: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    cap = int(fallback.get("deterministic_score_cap") or 6)
    decision = str(raw.get("decision") or fallback["decision"])
    if decision not in {"accept_for_demo", "revise_before_demo", "reject_or_boundary_case"}:
        decision = fallback["decision"]
    decision = cap_decision(decision, cap)
    risk = raw.get("citation_risk_summary")
    if not isinstance(risk, dict):
        risk = fallback["citation_risk_summary"]
    raw_score = clamp_score(raw.get("final_score_1_to_6"), round(float(fallback["final_score_1_to_6"])))
    return {
        "final_score_1_to_6": min(raw_score, cap),
        "decision": decision,
        "main_reason": str(raw.get("main_reason") or fallback["main_reason"]),
        "must_fix_before_demo": normalize_str_list(raw.get("must_fix_before_demo"), fallback["must_fix_before_demo"]),
        "citation_risk_summary": {
            "green": int(risk.get("green", fallback["citation_risk_summary"]["green"])),
            "yellow": int(risk.get("yellow", fallback["citation_risk_summary"]["yellow"])),
            "red": int(risk.get("red", fallback["citation_risk_summary"]["red"])),
        },
        "reviewer_agreement": normalize_agreement(raw.get("reviewer_agreement"), fallback["reviewer_agreement"]),
        "deterministic_score_cap": cap,
        "penalty_breakdown": fallback.get("penalty_breakdown", []),
        "red_line_triggered": bool(fallback.get("red_line_triggered")),
    }


def cap_decision(decision: str, cap: int) -> str:
    if cap <= 2:
        return "reject_or_boundary_case"
    if cap <= 3 and decision == "accept_for_demo":
        return "revise_before_demo"
    return decision


def normalize_agreement(value: Any, default: str) -> str:
    agreement = str(value or "").strip().lower()
    if agreement in {"low", "medium", "high"}:
        return agreement
    return default if default in {"low", "medium", "high"} else "medium"


def build_meta_decision(reviews: list[dict[str, Any]], labels: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    scores = [int(review["score_1_to_6"]) for review in reviews]
    avg = statistics.mean(scores) if scores else 1.0
    cap = int(labels.get("deterministic_score_cap") or 6)
    final_score = round(min(avg, cap), 2)
    if labels["red"] > 0 or cap <= 2:
        decision = "reject_or_boundary_case"
    elif cap <= 3:
        decision = "revise_before_demo"
    elif labels["green"] > 0 and avg >= 4:
        decision = "accept_for_demo"
    else:
        decision = "revise_before_demo"
    return {
        "final_score_1_to_6": final_score,
        "decision": decision,
        "main_reason": (
            f"Deterministic audit found Green={labels['green']}, Yellow={labels['yellow']}, "
            f"Red={labels['red']} across {labels['total']} claims. "
            f"Score is capped at {cap} by deterministic risk rules."
        ),
        "must_fix_before_demo": build_must_fix(labels, context),
        "citation_risk_summary": {
            "green": labels["green"],
            "yellow": labels["yellow"],
            "red": labels["red"],
        },
        "reviewer_agreement": agreement_level(scores),
        "deterministic_score_cap": cap,
        "penalty_breakdown": labels.get("penalty_breakdown", []),
        "red_line_triggered": bool(labels.get("red_line_triggered")),
    }


def build_must_fix(labels: dict[str, Any], context: dict[str, Any]) -> list[str]:
    fixes = []
    if labels["red"]:
        fixes.append("Treat Red claims as boundary cases or remove them from the success demo.")
    if labels["yellow"]:
        fixes.append("Explain Yellow claims as existing citations with uncertain or partial support.")
    if labels["green"] == 0:
        fixes.append("For a success demo, select another paper or rerun with more sources to obtain at least one Green claim.")
    if labels.get("red_line_triggered"):
        fixes.append("Fix Red-line citation errors before presenting the case as successful.")
    if labels.get("missing_critical_terms_count"):
        fixes.append("Qualify claims with missing critical terms or retrieve stronger supporting evidence.")
    if context["provider_summary"].get("tool_error_count", 0):
        fixes.append("Mention provider/tool failures in the failure analysis instead of hiding them.")
    return fixes


def agreement_level(scores: list[int]) -> str:
    if len(scores) < 2:
        return "medium"
    spread = max(scores) - min(scores)
    if spread <= 1:
        return "high"
    if spread <= 2:
        return "medium"
    return "low"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(safe_for_logs(row), ensure_ascii=False) + "\n")


def safe_for_logs(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: safe_for_logs(item) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_for_logs(item) for item in value]
    if isinstance(value, str):
        return redact_secret_like_text(value)
    return value


def redact_secret_like_text(value: str) -> str:
    return re.sub(r"sk-[A-Za-z0-9_-]{12,}", "sk-***REDACTED***", value)


def render_report(reviews: list[dict[str, Any]], meta: dict[str, Any], context: dict[str, Any]) -> str:
    lines = [
        "# Multi-Reviewer Report",
        "",
        f"Audit run: `{context['audit_dir']}`",
        f"Quest root: `{context['quest_root']}`",
        f"Mode: `{context['review_mode']}`",
        "",
        "## Citation Risk",
        "",
        f"- Green: {context['label_summary']['green']}",
        f"- Yellow: {context['label_summary']['yellow']}",
        f"- Red: {context['label_summary']['red']}",
        "",
        "## Reviewer Scores",
        "",
        "| Reviewer | Role | Model | Source | Score | Confidence |",
        "|---|---|---|---|---:|---|",
    ]
    for review in reviews:
        lines.append(
            f"| {review['reviewer_id']} | {review['role']} | {review.get('model', '')} | "
            f"{review.get('review_source', '')} | {review['score_1_to_6']} | {review['confidence']} |"
        )
    lines.extend(
        [
            "",
            "## Meta Decision",
            "",
            f"- Final score: {meta['final_score_1_to_6']}",
            f"- Deterministic score cap: {meta.get('deterministic_score_cap', 6)}",
            f"- Red-line triggered: {meta.get('red_line_triggered', False)}",
            f"- Decision: {meta['decision']}",
            f"- Source: {meta.get('review_source', 'unknown')}",
            f"- Model: {meta.get('model', 'unknown')}",
            f"- Reason: {meta['main_reason']}",
            "",
            "## Penalty Breakdown",
            "",
        ]
    )
    for item in meta.get("penalty_breakdown", []):
        lines.append(f"- `{item.get('rule')}` caps score at {item.get('cap')}: {item.get('reason')}")
    if not meta.get("penalty_breakdown"):
        lines.append("- No deterministic score cap penalty was triggered.")
    lines.extend(
        [
            "",
            "## Required Revisions",
            "",
        ]
    )
    for item in meta["must_fix_before_demo"]:
        lines.append(f"- {item}")
    if not meta["must_fix_before_demo"]:
        lines.append("- No mandatory revision from the meta-reviewer.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
