from awp_rp_runtime_v2.contracts.card_state import CardState, SceneState
from awp_rp_runtime_v2.contracts.round_snapshot import RoundSnapshot
from awp_rp_runtime_v2.runtime.continuity_runtime import ContinuityRuntime
from awp_rp_runtime_v2.runtime.continuity_trigger_policy import ContinuityTriggerResult
from awp_rp_runtime_v2.runtime.emotion_relationship_runtime import EmotionRelationshipRuntime
from awp_rp_runtime_v2.runtime.emotion_relationship_trigger_policy import (
    EmotionRelationshipTriggerResult,
)
from awp_rp_runtime_v2.runtime.history_recall_runtime import HistoryRecallRuntime
from awp_rp_runtime_v2.runtime.history_recall_trigger_policy import TriggerResult
from awp_rp_runtime_v2.runtime.world_life_runtime import WorldLifeRuntime
from awp_rp_runtime_v2.runtime.world_life_trigger_policy import WorldLifeTriggerResult


def _snapshot_with_worldbook() -> RoundSnapshot:
    return RoundSnapshot(
        snapshot_id="snap_worldbook_compat",
        trace_id="trace_worldbook_compat",
        card_id="card1",
        session_id="sess1",
        player_input="continue",
        card_state=CardState(scene_state=SceneState(location="room")),
        active_worldbook_entries=[{
            "entry_id": "wb1",
            "title": "Worldbook Entry",
            "content_excerpt": "CRITICAL_WORLDBOOK_EXCERPT",
        }],
    )


def test_history_recall_reads_worldbook_content_excerpt():
    evidence = HistoryRecallRuntime()._collect_evidence_from_snapshot(
        _snapshot_with_worldbook(),
        TriggerResult(should_trigger=True),
    )

    assert any(ev.excerpt == "CRITICAL_WORLDBOOK_EXCERPT" for ev in evidence)


def test_world_life_reads_worldbook_content_excerpt():
    evidence = WorldLifeRuntime()._collect_evidence_from_snapshot(
        _snapshot_with_worldbook(),
        WorldLifeTriggerResult(should_trigger=True),
    )

    assert any(ev.excerpt == "CRITICAL_WORLDBOOK_EXCERPT" for ev in evidence)


def test_emotion_relationship_reads_worldbook_content_excerpt():
    evidence = EmotionRelationshipRuntime()._collect_evidence_from_snapshot(
        _snapshot_with_worldbook(),
        EmotionRelationshipTriggerResult(should_trigger=True),
    )

    assert any(ev.excerpt == "CRITICAL_WORLDBOOK_EXCERPT" for ev in evidence)


def test_continuity_reads_worldbook_content_excerpt():
    evidence = ContinuityRuntime()._collect_evidence_from_snapshot(
        _snapshot_with_worldbook(),
        ContinuityTriggerResult(should_trigger=True),
    )

    assert any(ev.excerpt == "CRITICAL_WORLDBOOK_EXCERPT" for ev in evidence)
