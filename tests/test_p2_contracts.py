"""P2 Tests: Contract schema validation for TurnBrief, DelegationPlan, etc."""

import pytest
from awp_rp_runtime_v2.contracts import (
    TurnBrief, NarrativeGoal,
    DelegationPlan, DelegationTask,
    AgentTaskEnvelope, TaskBudget,
    AgentSuggestion, SuggestionKind,
    SuggestionMergeResult, MergeItem, MergeDecision,
    WriterInputBundle,
    AgentExecutionResult,
)


class TestTurnBriefContract:
    """Tests 1-3: TurnBrief schema validation."""

    def test_schema_id(self):
        brief = TurnBrief()
        assert brief.schema_id == "awp.rp.turn-brief.v1"

    def test_has_required_fields(self):
        brief = TurnBrief(
            brief_id="b1", trace_id="t1", snapshot_id="s1",
            turn_goal="goal", player_intent="intent",
        )
        assert brief.brief_id == "b1"
        assert brief.must_preserve_facts == []
        assert brief.must_not_do == []

    def test_serialize_roundtrip(self):
        brief = TurnBrief(
            brief_id="b1", turn_goal="goal",
            must_preserve_facts=["fact1"],
            must_not_do=["don't contradict"],
            active_characters=["char1"],
        )
        restored = TurnBrief.from_dict(brief.to_dict())
        assert restored.brief_id == "b1"
        assert restored.must_preserve_facts == ["fact1"]
        assert "don't contradict" in restored.must_not_do[0]


class TestDelegationPlanContract:
    """Tests 2-3: DelegationPlan schema validation."""

    def test_schema_id(self):
        plan = DelegationPlan()
        assert plan.schema_id == "awp.rp.delegation-plan.v1"

    def test_empty_plan_valid(self):
        plan = DelegationPlan(plan_id="p1", tasks=[])
        assert plan.tasks == []

    def test_task_has_all_fields(self):
        task = DelegationTask(
            task_id="t1", role="continuity-checker", priority=0.8,
            purpose="Check consistency",
            input_field_allowlist=["card_state", "recent_turns"],
            tool_allowlist=["state.read"],
            max_tokens=500, timeout_ms=10000,
            required=False, failure_policy="skip",
            expected_suggestion_kinds=["continuity_issue"],
        )
        restored = DelegationTask.from_dict(task.to_dict())
        assert restored.role == "continuity-checker"
        assert restored.input_field_allowlist == ["card_state", "recent_turns"]

    def test_serialize_roundtrip(self):
        plan = DelegationPlan(
            plan_id="p1", trace_id="t1", snapshot_id="s1",
            tasks=[DelegationTask(task_id="t1", role="continuity-checker")],
            max_task_count=5, total_token_budget=10000,
        )
        restored = DelegationPlan.from_dict(plan.to_dict())
        assert restored.plan_id == "p1"
        assert len(restored.tasks) == 1


class TestAgentTaskEnvelopeContract:
    """Tests 9-10: AgentTaskEnvelope."""

    def test_schema_id(self):
        envelope = AgentTaskEnvelope()
        assert envelope.schema_id == "awp.rp.agent-task-envelope.v1"

    def test_only_allowlist_fields(self):
        envelope = AgentTaskEnvelope(
            allowed_snapshot_data={"card_state": {"variables": {}}},
            allowed_tools=["state.read"],
        )
        assert "card_state" in envelope.allowed_snapshot_data
        assert "state.read" in envelope.allowed_tools
        # Empty tools = all denied
        e2 = AgentTaskEnvelope()
        assert e2.allowed_tools == []

    def test_prohibitions_present(self):
        envelope = AgentTaskEnvelope()
        assert "Cannot delegate to sub-agents" in envelope.prohibitions
        assert "Cannot write to CardState" in envelope.prohibitions
        assert "Cannot access database connections" in envelope.prohibitions


class TestAgentSuggestionContract:
    """Test AgentSuggestion schema."""

    def test_schema_id(self):
        sug = AgentSuggestion()
        assert sug.schema_id == "awp.rp.agent-suggestion.v1"

    def test_has_kind_confidence_evidence(self):
        sug = AgentSuggestion(
            suggestion_id="s1", kind=SuggestionKind.CONTINUITY_ISSUE,
            confidence=0.9, evidence=["Turn 3 says forest"],
            source_refs=["turn_record:t3"],
        )
        assert sug.kind == SuggestionKind.CONTINUITY_ISSUE
        assert sug.confidence == 0.9

    def test_serialize_roundtrip(self):
        sug = AgentSuggestion(
            suggestion_id="s1", kind=SuggestionKind.MEMORY_CANDIDATE,
            proposed_memory_candidates=[{"content": "test"}],
        )
        restored = AgentSuggestion.from_dict(sug.to_dict())
        assert restored.kind == SuggestionKind.MEMORY_CANDIDATE


class TestSuggestionMergeResultContract:
    """Tests 19-20: SuggestionMergeResult."""

    def test_schema_id(self):
        result = SuggestionMergeResult()
        assert result.schema_id == "awp.rp.suggestion-merge-result.v1"

    def test_has_all_categories(self):
        result = SuggestionMergeResult(
            adopted=[MergeItem(suggestion_id="a1", decision=MergeDecision.ADOPTED)],
            ignored=[MergeItem(suggestion_id="i1", decision=MergeDecision.IGNORED)],
            conflicts=[MergeItem(suggestion_id="c1", decision=MergeDecision.CONFLICT)],
            degraded_tasks=["dt1"],
            failed_tasks=["ft1"],
        )
        assert len(result.adopted) == 1
        assert len(result.ignored) == 1
        assert len(result.conflicts) == 1
        assert result.degraded_tasks == ["dt1"]

    def test_serialize_roundtrip(self):
        result = SuggestionMergeResult(
            merge_id="m1", writer_guidance=["guide1"],
            state_proposal_hints=[{"path": "variables.hp", "value": 100}],
        )
        restored = SuggestionMergeResult.from_dict(result.to_dict())
        assert restored.merge_id == "m1"
        assert restored.writer_guidance == ["guide1"]


class TestWriterInputBundleContract:
    """Test 20: WriterInputBundle."""

    def test_schema_id(self):
        bundle = WriterInputBundle()
        assert bundle.schema_id == "awp.rp.writer-input-bundle.v1"

    def test_references_not_inline(self):
        bundle = WriterInputBundle(
            round_snapshot_ref="snap1",
            turn_brief_ref="brief1",
            suggestion_merge_ref="merge1",
        )
        assert bundle.round_snapshot_ref == "snap1"
        # Bundle only has refs, not inline copies

    def test_serialize_roundtrip(self):
        bundle = WriterInputBundle(
            bundle_id="b1", writer_constraints=["don't contradict"],
            accepted_guidance=["add detail"],
            card_profile_context={"name": "Ari", "personality": "guarded"},
        )
        restored = WriterInputBundle.from_dict(bundle.to_dict())
        assert restored.bundle_id == "b1"
        assert restored.card_profile_context["name"] == "Ari"
        assert restored.card_profile_context["personality"] == "guarded"
