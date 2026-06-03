from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

MEMORY_DIR = Path(os.getcwd()) / "outputs" / "agent_memory"


class AgentMemory:
    """Hierarchical memory for the citation verification agent.

    Three levels:
      - working:    per-run state (in-memory dict, written to disk at checkpoints)
      - short_term: recent experiences (JSON array, auto-compressed when too large)
      - long_term:  consolidated rules & insights (multiple JSON files)
    """

    def __init__(self):
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        (MEMORY_DIR / "long_term").mkdir(exist_ok=True)

        # ── working memory (in-memory, per-run) ──
        self.working: dict[str, Any] = self._new_working()

        # ── short-term memory (loaded from disk) ──
        self.short_term: list[dict] = self._load_json("short_term.json", [])

        # ── long-term memory (multiple categories, loaded lazily) ──
        self.long_term: dict[str, list[dict]] = {}
        for lt_file in ["verification_rules", "provider_insights", "success_patterns"]:
            self.long_term[lt_file] = self._load_json(f"long_term/{lt_file}.json", [])

    # ───────── helpers ─────────

    def _load_json(self, path: str, default: Any) -> Any:
        filepath = MEMORY_DIR / path
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return default

    def _save_json(self, path: str, data: Any) -> None:
        filepath = MEMORY_DIR / path
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _new_working() -> dict[str, Any]:
        return {
            "started_at": time.time(),
            "current_pdf": "",
            "verified_dois": [],
            "used_providers": [],
            "claim_count": 0,
            "green_count": 0,
            "yellow_count": 0,
            "red_count": 0,
        }

    # ───────── working memory ─────────

    def set_working(self, key: str, value: Any) -> None:
        if key == "used_providers":
            existing = set(self.working.get("used_providers", []))
            if isinstance(value, str):
                existing.add(value)
            elif isinstance(value, (list, set)):
                existing.update(value)
            self.working["used_providers"] = sorted(existing)
        elif key == "verified_dois":
            existing = set(self.working.get("verified_dois", []))
            if isinstance(value, str):
                existing.add(value)
            elif isinstance(value, (list, set)):
                existing.update(value)
            self.working["verified_dois"] = sorted(existing)
        else:
            self.working[key] = value

    def get_working(self, key: str, default: Any = None) -> Any:
        return self.working.get(key, default)

    def reset_working(self, pdf_title: str = "") -> None:
        self.working = self._new_working()
        self.working["started_at"] = time.time()
        self.working["current_pdf"] = pdf_title

    def save_working(self) -> None:
        """Persist working memory to disk (as checkpoint)."""
        self._save_json("working/current.json", self.working)

    # ───────── short-term memory ─────────

    def add_experience(self, exp_type: str, **detail: Any) -> None:
        """Record a single experience (success or failure)."""
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": exp_type,
        }
        entry.update(detail)
        self.short_term.append(entry)
        self._save_json("short_term.json", self.short_term)
        self._compress_if_needed()

    def get_recent(self, n: int = 10, exp_type: str | None = None) -> list[dict]:
        if exp_type:
            filtered = [e for e in self.short_term if e.get("type") == exp_type]
            return filtered[-n:]
        return self.short_term[-n:]

    # ───────── success memory ─────────

    def add_success(self, success_type: str, detail: str, context: str = "") -> None:
        """Record a successful pattern that should be repeated."""
        self.add_experience(
            "success",
            success_type=success_type,
            detail=detail,
            context=context,
        )

        # 同类成功出现 3 次以上 → 升级为长期成功模式
        recent = [
            e for e in self.short_term
            if e.get("type") == "success" and e.get("success_type") == success_type
        ]
        if len(recent) >= 3:
            patterns = self.long_term["success_patterns"]
            # 避免完全重复
            if not any(p.get("success_type") == success_type for p in patterns):
                patterns.append({
                    "success_type": success_type,
                    "compiled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "occurrences": len(recent),
                    "summary": detail,
                    "examples": [e.get("context", "") for e in recent[-3:] if e.get("context")],
                })
                self._save_json("long_term/success_patterns.json", patterns)

    # ───────── memory compression ─────────

    def _compress_if_needed(self) -> None:
        """Auto-compress short-term memory when it exceeds threshold."""
        error_entries = [e for e in self.short_term if e.get("type") == "verification_error"]
        if len(error_entries) < 30:
            return

        # 按 error_type 分组压缩
        groups: dict[str, list[dict]] = {}
        for e in error_entries:
            et = e.get("error_type", "unknown")
            groups.setdefault(et, []).append(e)

        rules = self.long_term["verification_rules"]

        for error_type, entries in groups.items():
            # 跳过已经被压缩过的类型
            if any(r.get("error_type") == error_type for r in rules):
                continue

            reasons = [e.get("reason", "") for e in entries if e.get("reason")]
            unique_reasons = list(dict.fromkeys(reasons))

            rule_text = self._default_rule_for(error_type)
            rule = {
                "error_type": error_type,
                "compiled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "occurrences": len(unique_reasons),
                "rule": rule_text,
                "examples": unique_reasons[:3],
            }
            rules.append(rule)
            self._save_json("long_term/verification_rules.json", rules)

        # 从 short_term 中移除已压缩的错误条目
        self.short_term = [e for e in self.short_term if e.get("type") != "verification_error"]
        self._save_json("short_term.json", self.short_term)

    @staticmethod
    def _default_rule_for(error_type: str) -> str:
        rules = {
            "元数据伪造": "必须100%参照 search_literature 工具返回的真实数据，禁止捏造 DOI/标题/作者",
            "过度推断": "跨领域/跨学科推断时必须添加'可能有联系'等限定词，确保结论文献中有直接依据",
            "幻觉/引文无关": "提出 Claim 前必须精读检索返回的文献上下文，切忌自由发挥",
        }
        return rules.get(error_type, f"多次出现「{error_type}」类型错误，应检查验证流程")

    # ───────── long-term memory ─────────

    def add_provider_insight(self, provider: str, insight: str, success_rate: float | None = None) -> None:
        """Record a provider reliability insight."""
        insights = self.long_term["provider_insights"]
        # 更新已有记录而不是重复追加
        for existing in insights:
            if existing.get("provider") == provider and existing.get("insight") == insight:
                existing["last_seen"] = time.strftime("%Y-%m-%d %H:%M:%S")
                if success_rate is not None:
                    existing["success_rate"] = success_rate
                self._save_json("long_term/provider_insights.json", insights)
                return

        insights.append({
            "provider": provider,
            "insight": insight,
            "success_rate": success_rate,
            "first_seen": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_seen": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._save_json("long_term/provider_insights.json", insights)

    def get_insights(self, category: str | None = None) -> list[dict]:
        if category:
            return self.long_term.get(category, [])
        result = []
        for items in self.long_term.values():
            result.extend(items)
        return result

    # ───────── prompt builders ─────────

    def build_verification_guidance(self) -> str:
        """Build a guidance snippet for the LLM judge prompt."""
        parts: list[str] = []

        # 成功模式
        patterns = self.long_term["success_patterns"]
        if patterns:
            parts.append("✅ 已验证有效的策略：")
            for p in patterns[-2:]:
                parts.append(f"- [{p['success_type']}] {p['summary'][:120]}")

        # 长期验证规则
        rules = self.long_term["verification_rules"]
        if rules:
            parts.append("\n⚠️ 历史验证规则（请遵守）：")
            for r in rules[-3:]:
                parts.append(f"- [{r['error_type']}] {r['rule']}")

        # 数据源可靠性
        insights = self.long_term["provider_insights"]
        if insights:
            parts.append("\n📊 数据源参考：")
            for ins in insights[-3:]:
                sr = f" (成功率: {ins['success_rate']:.0%})" if ins.get("success_rate") is not None else ""
                parts.append(f"- {ins['provider']}: {ins['insight']}{sr}")

        return "\n".join(parts)

    def build_search_guidance(self) -> str:
        """Build guidance for the literature searcher."""
        insights = self.long_term["provider_insights"]
        if not insights:
            return ""
        parts = ["📊 搜索经验（来自历史记录）："]
        for ins in insights[-3:]:
            sr = f" (成功率: {ins['success_rate']:.0%})" if ins.get("success_rate") is not None else ""
            parts.append(f"- {ins['provider']}: {ins['insight']}{sr}")
        return "\n".join(parts)

    def build_hypothesis_guidance(self) -> str:
        """Build guidance for the hypothesis generator prompt.

        Returns (success_str, error_str) tuple for injection.
        """
        # 成功经验
        patterns = self.long_term["success_patterns"]
        success_str = ""
        if patterns:
            success_lines = ["✅ 成功经验（优先沿用）："]
            for p in patterns[-3:]:
                success_lines.append(f"- [{p['success_type']}] {p['summary'][:150]}")
            success_str = "\n".join(success_lines)

        # 错误教训（从 short_term 和 long_term 拿最近的）
        recent_errors = [e for e in self.short_term if e.get("type") == "verification_error"]
        rules = self.long_term["verification_rules"]

        error_lines: list[str] = []
        if recent_errors:
            error_lines.append("最近犯的错（避免重犯）：")
            for e in recent_errors[-3:]:
                error_lines.append(f"- [{e.get('error_type', '未知')}] {e.get('reason', '')[:120]}")
        if rules:
            if not error_lines:
                error_lines.append("❌ 历史错误规则（避免重犯）：")
            for r in rules[-3:]:
                error_lines.append(f"- [{r['error_type']}] {r['rule']}")

        return success_str, "\n".join(error_lines)


# ═══════════════════════════════════════
#  Singleton + backward-compatible API
# ═══════════════════════════════════════

_instance: AgentMemory | None = None


def get_memory() -> AgentMemory:
    global _instance
    if _instance is None:
        _instance = AgentMemory()
    return _instance


def reset_memory() -> None:
    global _instance
    _instance = None


# backward-compatible aliases (used by citation_verifier, hypothesis_generator)
def get_reflections() -> list[dict]:
    """Old name — returns recent errors in old {type, lesson} format."""
    recent = get_memory().get_recent(5, exp_type="verification_error")
    # Convert new format to old format that hypothesis_generator expects
    old_format = []
    for r in recent:
        old_format.append({
            "type": r.get("error_type", r.get("type", "unknown")),
            "lesson": r.get("reason", r.get("lesson", "")),
        })
    return old_format


def add_reflection(error_type: str, lesson: str) -> None:
    """Old name — records a verification error."""
    get_memory().add_experience(
        "verification_error",
        error_type=error_type,
        claim_text="",
        doi="",
        reason=lesson,
    )
