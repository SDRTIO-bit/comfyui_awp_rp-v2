from awp_rp_runtime_v2.contracts.card_state import CardState, SceneState
from awp_rp_runtime_v2.contracts.quality_decision import QualityVerdict
from awp_rp_runtime_v2.contracts.quality_issue import IssueSeverity
from awp_rp_runtime_v2.contracts.round_snapshot import RoundSnapshot
from awp_rp_runtime_v2.contracts.writer_draft import WriterDraft
from awp_rp_runtime_v2.runtime.quality_pipeline_runtime import QualityPipelineRuntime, SceneGate


def _snapshot() -> RoundSnapshot:
    return RoundSnapshot(
        snapshot_id="snap_scene_gate",
        trace_id="trace_scene_gate",
        card_id="card1",
        session_id="sess1",
        card_state=CardState(scene_state=SceneState(location="Hidden Tavern")),
    )


def test_scene_gate_missing_literal_location_is_warning_not_error():
    draft = WriterDraft(
        draft_id="draft1",
        trace_id="trace_scene_gate",
        snapshot_id="snap_scene_gate",
        text="The candlelight trembled across the table while voices sank behind the door. " * 5,
    )

    result = SceneGate().check(draft, _snapshot())

    assert result.passed is True
    assert result.warning_count == 1
    assert result.issues[0].severity == IssueSeverity.WARNING


def test_quality_pipeline_accepts_scene_warning_without_revise():
    draft = WriterDraft(
        draft_id="draft1",
        trace_id="trace_scene_gate",
        snapshot_id="snap_scene_gate",
        text="The candlelight trembled across the table while voices sank behind the door. " * 5,
    )

    decision = QualityPipelineRuntime().check(draft, _snapshot())

    assert decision.verdict == QualityVerdict.ACCEPTED
    assert any("Hidden Tavern" in warning for warning in decision.warnings)
