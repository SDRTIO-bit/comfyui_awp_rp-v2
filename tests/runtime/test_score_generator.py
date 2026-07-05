"""Tests for Writer score generation."""

from awp_rp_runtime_v2.contracts.agent_suggestion import AgentSuggestion, SuggestionKind
from awp_rp_runtime_v2.contracts.director_plan import DirectorPlan
from awp_rp_runtime_v2.contracts.suggestion_merge_result import (
    MergeDecision,
    MergeItem,
    SuggestionMergeResult,
)
from awp_rp_runtime_v2.runtime.score_generator import ScoreGenerator


class TestScoreGenerator:

    def test_generates_executable_score_from_director_plan(self):
        plan = DirectorPlan(
            turn_goal="让角色在门前犹豫而不是立刻行动",
            scene_focus="门把手、呼吸、沉默",
            pacing_guidance="slow",
            must_preserve_facts=["她还没有开门"],
            must_not_do=["不要替玩家做决定"],
            writer_constraints=["只写可见行为"],
        )

        score = ScoreGenerator().generate(plan, None)

        assert "<direction>" in score
        assert "<inner_state>" in score
        assert "让角色在门前犹豫而不是立刻行动" in score
        assert "<behavioral_cue>" in score
        assert "门把手、呼吸、沉默" in score
        assert "<constraint>" in score
        assert "不要替玩家做决定" in score

    def test_detects_semantic_conflict_before_writer(self):
        trust = AgentSuggestion(
            suggestion_id="s1",
            role="emotion_relationship",
            kind=SuggestionKind.ER_AFFECTION_RESTRAINT,
            summary="角色A应该信任对方并靠近",
            recommendations=["表现出信任"],
        )
        distrust = AgentSuggestion(
            suggestion_id="s2",
            role="continuity",
            kind=SuggestionKind.CONTINUITY_WRITER_CONSTRAINT,
            summary="角色A必须保持警惕并后退",
            recommendations=["表现出警惕"],
        )
        merge = SuggestionMergeResult(
            adopted=[
                MergeItem(suggestion_id="s1", role="emotion_relationship",
                          decision=MergeDecision.ADOPTED, suggestion=trust),
                MergeItem(suggestion_id="s2", role="continuity",
                          decision=MergeDecision.ADOPTED, suggestion=distrust),
            ],
        )

        score = ScoreGenerator().generate(
            DirectorPlan(turn_goal="保持紧张关系", scene_focus="两人的距离"),
            merge,
        )

        assert "<conflict>" in score
        assert "s1" in score
        assert "s2" in score
        assert "Writer must follow the Director score" in score

    def test_detects_real_chinese_trust_vs_alert_conflict(self):
        trust = AgentSuggestion(
            suggestion_id="cn1",
            role="emotion_relationship",
            kind=SuggestionKind.RELATIONSHIP_SHIFT,
            summary="\u89d2\u8272\u5e94\u8be5\u4fe1\u4efb\u5bf9\u65b9\u5e76\u9760\u8fd1",
        )
        alert = AgentSuggestion(
            suggestion_id="cn2",
            role="continuity",
            kind=SuggestionKind.CONTINUITY_WRITER_CONSTRAINT,
            summary="\u89d2\u8272\u5fc5\u987b\u4fdd\u6301\u8b66\u60d5\u5e76\u540e\u9000",
        )
        merge = SuggestionMergeResult(
            adopted=[
                MergeItem(suggestion_id="cn1", role="emotion_relationship",
                          decision=MergeDecision.ADOPTED, suggestion=trust),
                MergeItem(suggestion_id="cn2", role="continuity",
                          decision=MergeDecision.ADOPTED, suggestion=alert),
            ],
        )

        score = ScoreGenerator().generate(
            DirectorPlan(turn_goal="\u7ef4\u6301\u7d27\u5f20", scene_focus="\u95e8\u524d"),
            merge,
        )

        assert "<conflict>" in score
        assert "cn1" in score
        assert "cn2" in score
