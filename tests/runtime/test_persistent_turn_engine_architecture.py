from awp_rp_runtime_v2.contracts.agent_suggestion import AgentSuggestion, SuggestionKind
from awp_rp_runtime_v2.contracts.card_definition import CardDefinition
from awp_rp_runtime_v2.contracts.card_profile import CardProfile
from awp_rp_runtime_v2.contracts.final_turn_brief import FinalTurnBrief
from awp_rp_runtime_v2.contracts.round_snapshot import RoundSnapshot
from awp_rp_runtime_v2.runtime.persistent_turn_engine import (
    PersistentTurnEngine,
    _delegation_agent_name,
)
from awp_rp_runtime_v2.runtime.writer_input_bundle_v2_builder import WriterInputBundleV2Builder


def test_delegation_role_names_normalize_to_runtime_agent_names():
    assert _delegation_agent_name("history_recall") == "d1_history_recall"
    assert _delegation_agent_name("World Life") == "d3_world_life"
    assert _delegation_agent_name("D5 CONTINUITY") == "d5_continuity"
    assert _delegation_agent_name("emotion-relationship") == "d4_emotion_rel"


def test_persistent_engine_merges_subagent_suggestions_through_policy_merger():
    risky = AgentSuggestion(
        suggestion_id="s_risky",
        task_run_id="task_risky",
        role="continuity",
        kind=SuggestionKind.CONTINUITY_FACT_CONSTRAINT,
        priority=1.0,
        confidence=1.0,
        summary="Do a risky unsupported continuity correction",
        risk_flags=["risk_a", "risk_b"],
        evidence=[],
    )
    supported = AgentSuggestion(
        suggestion_id="s_supported",
        task_run_id="task_supported",
        role="history_recall",
        kind=SuggestionKind.IDENTITY_CLARIFICATION,
        priority=0.8,
        confidence=0.8,
        summary="Keep the established identity boundary",
        evidence=["accepted_turn:t1"],
    )

    merge = PersistentTurnEngine(None)._merge_agent_suggestions(
        snapshot=RoundSnapshot(snapshot_id="snap1", trace_id="trace1"),
        brief=FinalTurnBrief(brief_id="brief1", must_not_do=[]),
        agent_suggestions=[risky, supported],
        turn_id="turn1",
        delegation_plan=None,
    )

    assert merge is not None
    assert [item.suggestion_id for item in merge.adopted] == ["s_supported"]
    assert [item.suggestion_id for item in merge.ignored] == ["s_risky"]
    assert merge.writer_guidance == []


def test_writer_bundle_receives_only_adopted_subagent_suggestions():
    risky = AgentSuggestion(
        suggestion_id="s_risky",
        task_run_id="task_risky",
        role="continuity",
        kind=SuggestionKind.CONTINUITY_FACT_CONSTRAINT,
        priority=1.0,
        confidence=1.0,
        summary="Unsupported risky claim",
        risk_flags=["risk_a", "risk_b"],
        evidence=[],
    )
    supported = AgentSuggestion(
        suggestion_id="s_supported",
        task_run_id="task_supported",
        role="history_recall",
        kind=SuggestionKind.IDENTITY_CLARIFICATION,
        priority=0.8,
        confidence=0.8,
        summary="Supported identity boundary",
        evidence=["accepted_turn:t1"],
    )
    snapshot = RoundSnapshot(
        snapshot_id="snap1",
        trace_id="trace1",
        player_input="continue",
    )
    brief = FinalTurnBrief(brief_id="brief1", must_not_do=[])

    merge = PersistentTurnEngine(None)._merge_agent_suggestions(
        snapshot=snapshot,
        brief=brief,
        agent_suggestions=[risky, supported],
        turn_id="turn1",
        delegation_plan=None,
    )
    bundle = WriterInputBundleV2Builder().build(snapshot, brief, merge)

    assert "Supported identity boundary" in bundle.accepted_guidance
    assert "Unsupported risky claim" not in bundle.accepted_guidance


def test_curator_receives_only_adopted_subagent_suggestions():
    risky = AgentSuggestion(
        suggestion_id="s_risky",
        task_run_id="task_risky",
        role="continuity",
        kind=SuggestionKind.CONTINUITY_FACT_CONSTRAINT,
        priority=1.0,
        confidence=1.0,
        summary="Unsupported risky claim",
        risk_flags=["risk_a", "risk_b"],
        evidence=[],
    )
    supported = AgentSuggestion(
        suggestion_id="s_supported",
        task_run_id="task_supported",
        role="history_recall",
        kind=SuggestionKind.IDENTITY_CLARIFICATION,
        priority=0.8,
        confidence=0.8,
        summary="Supported identity boundary",
        evidence=["accepted_turn:t1"],
    )
    snapshot = RoundSnapshot(
        snapshot_id="snap1",
        trace_id="trace1",
        player_input="continue",
    )
    brief = FinalTurnBrief(brief_id="brief1", must_not_do=[])
    engine = PersistentTurnEngine(None)

    merge = engine._merge_agent_suggestions(
        snapshot=snapshot,
        brief=brief,
        agent_suggestions=[risky, supported],
        turn_id="turn1",
        delegation_plan=None,
    )
    curator_suggestions = engine._adopted_agent_suggestion_dicts(merge)

    summaries = [item["summary"] for item in curator_suggestions]
    assert summaries == ["Supported identity boundary"]
    assert "Unsupported risky claim" not in summaries


def test_writer_bundle_inherits_card_profile_from_round_snapshot():
    snapshot = RoundSnapshot(
        snapshot_id="snap1",
        trace_id="trace1",
        player_input="continue",
        card_profile_context={
            "name": "Ari",
            "description": "PROFILE_DESCRIPTION_MARKER",
        },
    )
    brief = FinalTurnBrief(brief_id="brief1")

    bundle = WriterInputBundleV2Builder().build(snapshot, brief)

    assert bundle.card_profile_context["name"] == "Ari"
    assert bundle.card_profile_context["description"] == "PROFILE_DESCRIPTION_MARKER"


def test_persistent_engine_loads_versioned_card_profile_for_writer_bundle():
    profile = CardProfile(
        name="Ari",
        description="PROFILE_DESCRIPTION_MARKER",
        personality="PROFILE_PERSONALITY_MARKER",
    ).to_dict()
    definition = CardDefinition(
        logical_card_id="card1",
        card_version=3,
        source_id="src",
        source_hash="hash",
        name="Fallback Name",
        profile=profile,
    )

    class Store:
        def __init__(self):
            self.loaded = None

        def load(self, logical_card_id, card_version):
            self.loaded = (logical_card_id, card_version)
            return definition

    class Registry:
        card_definition_store = Store()

    class Binding:
        logical_card_id = "card1"
        card_version = 3

    loaded = PersistentTurnEngine(Registry())._load_card_profile_context(Binding())

    assert Registry.card_definition_store.loaded == ("card1", 3)
    assert loaded["name"] == "Ari"
    assert loaded["description"] == "PROFILE_DESCRIPTION_MARKER"
    assert loaded["personality"] == "PROFILE_PERSONALITY_MARKER"
    assert loaded["logical_card_id"] == "card1"
    assert loaded["card_version"] == 3
