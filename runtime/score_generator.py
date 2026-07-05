"""Generate a single Writer score from Director plan and merged suggestions."""

from __future__ import annotations

from typing import Any

from ..contracts.director_plan import DirectorPlan
from ..contracts.suggestion_merge_result import SuggestionMergeResult


class ScoreGenerator:
    """Compose executable Writer guidance.

    This is intentionally deterministic. It does not pretend to resolve every
    semantic conflict perfectly; it prevents raw, contradictory sub-agent lists
    from becoming the Writer's direct instruction surface.
    """

    def generate(
        self,
        director_plan: DirectorPlan,
        merge_result: SuggestionMergeResult | None,
    ) -> str:
        suggestions = self._adopted_suggestions(merge_result)
        conflicts = self._detect_semantic_conflicts(suggestions)
        explicit_conflicts = list(getattr(merge_result, "conflicts", []) or []) if merge_result else []

        return (
            "<direction>\n"
            "<inner_state>\n"
            f"{director_plan.turn_goal or 'Continue the current emotional beat coherently.'}\n"
            f"{self._format_optional('Relationship tension', director_plan.relationship_tensions)}"
            "</inner_state>\n\n"
            "<behavioral_cue>\n"
            f"{director_plan.scene_focus or 'React to the player input through visible behavior and sensory detail.'}\n"
            f"{self._format_suggestion_themes(suggestions)}"
            "</behavioral_cue>\n\n"
            "<pacing>\n"
            f"{director_plan.pacing_guidance or 'moderate'}\n"
            "</pacing>\n\n"
            "<constraint>\n"
            f"{self._format_constraints(director_plan)}"
            "\nWriter must follow the Director score over individual sub-agent suggestions.\n"
            "</constraint>\n"
            f"{self._format_conflicts(conflicts, explicit_conflicts)}"
            "</direction>"
        )

    def _adopted_suggestions(self, merge_result: SuggestionMergeResult | None) -> list[Any]:
        if not merge_result:
            return []
        return [
            item.suggestion
            for item in merge_result.adopted
            if getattr(item, "suggestion", None) is not None
        ]

    def _format_constraints(self, plan: DirectorPlan) -> str:
        constraints = []
        constraints.extend(plan.must_preserve_facts)
        constraints.extend(plan.must_not_do)
        constraints.extend(plan.writer_constraints)
        if not constraints:
            return "- Do not contradict established facts."
        return "\n".join(f"- {item}" for item in constraints if str(item).strip())

    def _format_optional(self, label: str, items: list[str]) -> str:
        clean = [str(item).strip() for item in items if str(item).strip()]
        if not clean:
            return ""
        return f"{label}: " + "; ".join(clean[:3]) + "\n"

    def _format_suggestion_themes(self, suggestions: list[Any]) -> str:
        if not suggestions:
            return ""
        lines = []
        for suggestion in suggestions[:5]:
            summary = str(getattr(suggestion, "summary", "") or "").strip()
            if summary:
                lines.append(f"- {summary}")
        return "\nSub-agent themes considered by Director:\n" + "\n".join(lines) + "\n" if lines else ""

    def _detect_semantic_conflicts(self, suggestions: list[Any]) -> list[tuple[str, str, str]]:
        conflicts = []
        for index, left in enumerate(suggestions):
            for right in suggestions[index + 1:]:
                reason = self._conflict_reason(self._suggestion_text(left), self._suggestion_text(right))
                if reason:
                    conflicts.append((
                        str(getattr(left, "suggestion_id", "")),
                        str(getattr(right, "suggestion_id", "")),
                        reason,
                    ))
        return conflicts

    def _suggestion_text(self, suggestion: Any) -> str:
        bits = [str(getattr(suggestion, "summary", "") or "")]
        bits.extend(str(item) for item in getattr(suggestion, "recommendations", []) or [])
        return " ".join(bits)

    def _conflict_reason(self, left: str, right: str) -> str:
        pairs = [
            (("信任", "靠近", "放松"), ("警惕", "后退", "怀疑")),
            (("立刻", "马上", "加快"), ("犹豫", "放慢", "等待")),
            (("透露", "说出", "坦白"), ("隐藏", "保密", "沉默")),
            (("攻击", "激化"), ("缓和", "退让")),
        ]
        for positive, negative in pairs:
            left_pos = any(token in left for token in positive)
            left_neg = any(token in left for token in negative)
            right_pos = any(token in right for token in positive)
            right_neg = any(token in right for token in negative)
            if (left_pos and right_neg) or (left_neg and right_pos):
                return "semantic tension"
        return ""

    def _format_conflicts(self, conflicts: list[tuple[str, str, str]], explicit_conflicts: list[Any]) -> str:
        lines = []
        for left_id, right_id, reason in conflicts:
            lines.append(f"- {left_id} vs {right_id}: {reason}")
        for item in explicit_conflicts:
            suggestion_id = str(getattr(item, "suggestion_id", "") or "")
            reason = str(getattr(item, "reason", "") or "merge conflict")
            if suggestion_id:
                lines.append(f"- {suggestion_id}: {reason}")
        if not lines:
            return "\n"
        return "\n<conflict>\n" + "\n".join(lines) + "\n</conflict>\n"
