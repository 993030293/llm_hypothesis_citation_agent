from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger("hypothesis_qqbot.multi_agent_judge")

# ───────── 模型分配：4 位平行的审稿人各用不同模型 ─────────
REVIEWER_MODEL_MAP: dict[str, str] = {
    "reviewer_1": "glm",
    "reviewer_2": "minimax",
    "reviewer_3": "deepseek_v4_pro",
    "reviewer_4": "deepseek_v4_flash",
}

# ───────── 4 位平行的审稿人（相同角色，不同模型）─────────
_SHARED_REVIEWER_ROLE = (
    "你是一位审稿人，负责对「结论（Claim）」与「证据（论文摘要）」之间的支撑关系进行评分。\n\n"
    "评分标准（1-6 分）：\n"
    "  1-2 分 = 不支持：证据与结论矛盾、无关，或完全无法支撑结论\n"
    "  3-4 分 = 不确定：证据部分支撑结论，但存在推断成分或不完全对应\n"
    "  5-6 分 = 支持：证据明确、充分地支撑结论，无需重大推断\n\n"
    "请仔细阅读下方的结论与证据，给出评分并附上简要理由。"
)

REVIEWER_CONFIGS: dict[str, dict[str, str]] = {
    "reviewer_1": {"name": "审稿人 1", "role": _SHARED_REVIEWER_ROLE},
    "reviewer_2": {"name": "审稿人 2", "role": _SHARED_REVIEWER_ROLE},
    "reviewer_3": {"name": "审稿人 3", "role": _SHARED_REVIEWER_ROLE},
    "reviewer_4": {"name": "审稿人 4", "role": _SHARED_REVIEWER_ROLE},
}

AC_SYSTEM_PROMPT = (
    "你是一位领域主席，负责综合多位审稿人的评分和意见并做出最终裁决。\n\n"
    "裁决原则：\n"
    "1. 阅读每位审稿人的评分（1-6 分）和理由，评估说服力而非简单平均\n"
    "2. 评分较低的审稿人若有充分理由，其意见权重较高\n"
    "3. 评分较高的审稿人需要扎实的证据佐证才可采信\n"
    "4. 输出最终评分并给出综合理由，引用具体审稿人的意见\n\n"
    "评分标准：\n"
    "  1-2 分 = 不支持：证据与结论矛盾、无关，或完全无法支撑结论\n"
    "  3-4 分 = 不确定：证据部分支撑结论，但存在推断成分或不完全对应\n"
    "  5-6 分 = 支持：证据明确、充分地支撑结论，无需重大推断\n\n"
    "输出格式（仅输出 JSON，不要其他内容）：\n"
    '{"score": <1-6的整数>, "reason": "综合各位审稿人意见后的最终判断理由（中文）", '
    '"agreement_level": "unanimous 或 majority 或 split"}'
)

JSON_OUTPUT_INSTRUCTION = (
    "\n\n请严格按照以下 JSON 格式输出，不要输出任何其他文本：\n"
    '{"score": <1-6的整数>, "reason": "你的审稿理由（中文，200字以内）"}'
)


# ───────── Prompt 构建 ─────────

def build_reviewer_prompt(config: dict[str, str], evidence: dict[str, Any]) -> str:
    parts = [
        config["role"],
        "\n\n---\n",
        f"结论 (Claim): {evidence['claim_text']}",
        f"论文标题: {evidence['paper_title']}",
        f"DOI: {evidence['doi']}",
    ]
    abstract = evidence.get("abstract", "")
    if abstract and abstract != "（无可获取的摘要）":
        parts.append(f"论文摘要: {abstract}")
    else:
        parts.append("论文摘要: （无可获取的摘要）")

    overlap = evidence.get("vocabulary_overlap", "N/A")
    parts.append(f"词汇重叠度: {overlap}")
    shared = evidence.get("shared_terms", [])
    if shared:
        parts.append(f"共享术语: {', '.join(shared[:8])}")

    parts.append(JSON_OUTPUT_INSTRUCTION)
    return "\n".join(parts)


def build_ac_prompt(evidence: dict[str, Any], reviewer_results: dict[str, dict[str, Any]]) -> str:
    parts = [
        "## 需要最终裁决的结论与证据\n",
        f"结论 (Claim): {evidence['claim_text']}",
        f"论文标题: {evidence['paper_title']}",
        f"论文摘要: {evidence.get('abstract', 'N/A')}",
        f"词汇重叠度: {evidence.get('vocabulary_overlap', 'N/A')}",
    ]
    shared = evidence.get("shared_terms", [])
    if shared:
        parts.append(f"共享术语: {', '.join(shared[:8])}")

    parts.append("\n## 4 位审稿人的意见\n")
    for rid, cfg in REVIEWER_CONFIGS.items():
        result = reviewer_results.get(rid, {})
        score = result.get("score", "N/A")
        reason = result.get("reason", "审稿人未返回有效判决")
        parts.append(f"\n[{cfg['name']}]")
        parts.append(f"评分: {score}/6")
        parts.append(f"理由: {reason}")

    parts.append("\n## 你的裁决\n请基于以上审稿意见做出最终判断（1-6 分）。")
    return "\n".join(parts)


# ───────── 各个模型的正式名称 ─────────
MINIMAX_MODEL = "minimax-text-01"
GLM_MODEL = "glm-4-plus"

MODEL_SOURCE_CONFIG: dict[str, dict[str, str]] = {
    "glm":               {"provider": "glm",       "model": GLM_MODEL},
    "minimax":           {"provider": "minimax",   "model": MINIMAX_MODEL},
    "deepseek_v4_pro":   {"provider": "deepseek",  "model": "deepseek-chat"},
    "deepseek_v4_flash": {"provider": "deepseek",  "model": "deepseek-reasoner"},
}


# ───────── 单审稿人执行 ─────────

def run_reviewer(config: dict[str, str], evidence: dict[str, Any],
                 client: Any = None, model_name: str = "deepseek-chat") -> dict[str, Any]:
    from agent.llm_client import call_llm
    prompt = build_reviewer_prompt(config, evidence)
    messages = [{"role": "user", "content": prompt}]
    try:
        resp = call_llm(messages, temperature=0.1, model=model_name, client=client) if client \
                else call_llm(messages, temperature=0.1)
        content = resp.get("content", "").strip()
        return _parse_json_response(content, config["name"])
    except Exception as e:
        logger.warning("Reviewer %s failed: %s", config["name"], e)
        return {"score": 3, "reason": f"审稿人调用失败: {e}"}


def run_area_chair(evidence: dict[str, Any], reviewer_results: dict[str, dict[str, Any]],
                   client: Any = None) -> dict[str, Any]:
    from agent.llm_client import call_llm
    prompt = build_ac_prompt(evidence, reviewer_results)
    messages = [
        {"role": "system", "content": AC_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    try:
        resp = call_llm(messages, temperature=0.0, model="deepseek-chat", client=client) if client \
                else call_llm(messages, temperature=0.0)
        content = resp.get("content", "").strip()
        result = _parse_json_response(content, "Area Chair")
        return result
    except Exception as e:
        logger.warning("Area Chair failed: %s", e)
        return _majority_vote_fallback(reviewer_results, str(e))


# ───────── 工具函数 ─────────

def _parse_json_response(content: str, name: str) -> dict[str, Any]:
    if not content:
        return {"score": 3, "reason": f"{name}返回为空"}
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        content = match.group()
    try:
        res = json.loads(content)
        # 新格式：score
        if "score" in res:
            score = int(res["score"])
            score = max(1, min(6, score))
            return {"score": score, "reason": res.get("reason", "")}
        # 旧格式兼容：status → 映射为 score
        status = res.get("status", "")
        score_map = {"supports": 5, "partial_or_uncertain": 3, "not_supported": 2}
        return {"score": score_map.get(status, 3), "reason": res.get("reason", "")}
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"score": 3, "reason": f"{name}返回非JSON: {content[:80]}"}


def _majority_vote_fallback(reviewer_results: dict[str, dict[str, Any]], error: str) -> dict[str, Any]:
    scores = []
    for r in reviewer_results.values():
        s = r.get("score")
        if isinstance(s, (int, float)):
            scores.append(int(s))
    avg = round(sum(scores) / len(scores)) if scores else 3
    return {
        "score": avg,
        "reason": f"领域主席调用失败，按评分均值回退: avg={avg}",
        "agreement_level": "majority",
        "decision_basis": "majority_vote_fallback",
    }


def _build_detailed_reason(reviewer_results: dict[str, dict[str, Any]], ac_result: dict[str, Any]) -> str:
    parts = ["[多审稿人判决]"]
    for rid, cfg in REVIEWER_CONFIGS.items():
        result = reviewer_results.get(rid, {})
        score = result.get("score", "?")
        reason_preview = result.get("reason", "")[:80]
        parts.append(f"  [{cfg['name']}] {score}/6 | {reason_preview}")

    ac_score = ac_result.get("score", "?")
    ac_reason = ac_result.get("reason", "")
    agreement = ac_result.get("agreement_level", "")
    decision = ac_result.get("decision_basis", "")
    parts.append(f"\n  ▶ 领域主席综合判决: {ac_score}/6")
    if agreement:
        parts.append(f"  一致性: {agreement}")
    if decision:
        parts.append(f"  裁决依据: {decision}")
    parts.append(f"  最终理由: {ac_reason}")
    return "\n".join(parts)


# ───────── 主入口 ─────────

def judge(claim_text: str, candidate: dict[str, Any], overlap_result: tuple[float, list[str]] | None = None) -> dict[str, Any]:
    """Run 4 reviewers (parallel) + 1 AC (sequential) for citation support assessment.

    Each reviewer returns a score 1-6.
    The AC aggregates and returns a final score 1-6.
    The final score is mapped to support_status / support_score for downstream compatibility.

    Args:
        claim_text: The claim to verify.
        candidate: Candidate paper metadata (title, abstract, doi, etc.).
        overlap_result: Optional pre-calculated (score, shared_terms).

    Returns:
        dict with keys: support_status, support_reason, support_score,
                        reviewer_results, ac_result
    """
    # 计算词汇重叠
    if overlap_result:
        overlap_score_val, shared_terms = overlap_result
    else:
        from agent.utils import overlap_score
        evidence_text = f"{candidate.get('title', '')} {candidate.get('abstract', '') or candidate.get('snippet', '')}"
        overlap_score_val, shared_terms = overlap_score(claim_text, evidence_text)

    # 准备审稿材料
    evidence_package: dict[str, Any] = {
        "claim_text": claim_text,
        "paper_title": candidate.get("title", ""),
        "abstract": candidate.get("abstract") or candidate.get("snippet") or "（无可获取的摘要）",
        "doi": candidate.get("doi", ""),
        "vocabulary_overlap": round(overlap_score_val, 3),
        "shared_terms": shared_terms[:10] if shared_terms else [],
    }

    # Phase 2: 4 个审稿人并行（使用各自的模型）
    from agent.llm_client import get_llm_client, get_minimax_client, get_glm_client
    _deepseek_client = get_llm_client()
    _minimax_client = get_minimax_client()
    _glm_client = get_glm_client()
    _client_cache = {
        "deepseek": _deepseek_client,
        "minimax": _minimax_client,
        "glm": _glm_client,
    }

    reviewer_results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        def _run_with_model(rid: str) -> dict[str, Any]:
            cfg = REVIEWER_CONFIGS[rid]
            source_key = REVIEWER_MODEL_MAP.get(rid, "deepseek_v4_pro")
            source_cfg = MODEL_SOURCE_CONFIG[source_key]
            client = _client_cache[source_cfg["provider"]]
            model = source_cfg["model"]
            return run_reviewer(cfg, evidence_package, client=client, model_name=model)

        future_map = {
            executor.submit(_run_with_model, rid): rid
            for rid in REVIEWER_CONFIGS
        }
        for future in as_completed(future_map):
            rid = future_map[future]
            try:
                reviewer_results[rid] = future.result()
            except Exception as e:
                reviewer_results[rid] = {"score": 3, "reason": f"审稿人异常: {e}"}

    # Phase 3: 领域主席汇总（使用 DeepSeek V4 Pro）
    ac_result = run_area_chair(evidence_package, reviewer_results, client=_deepseek_client)

    # 构建详细理由
    detailed_reason = _build_detailed_reason(reviewer_results, ac_result)

    # 将 AC 评分映射为下游兼容的 support_status / support_score
    ac_score = ac_result.get("score", 3)
    if ac_score >= 5:
        final_status = "supports"
        final_score = 1.0
    elif ac_score >= 3:
        final_status = "partial_or_uncertain"
        final_score = 0.5
    else:
        final_status = "not_supported"
        final_score = 0.0

    return {
        "support_status": final_status,
        "support_reason": detailed_reason,
        "support_score": final_score,
        "ac_score": ac_score,
        "reviewer_results": reviewer_results,
        "ac_result": ac_result,
    }
