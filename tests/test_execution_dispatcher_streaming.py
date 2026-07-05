from __future__ import annotations

from awp_rp_runtime_v2.runtime import execution_dispatcher
from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher


def test_execute_turn_streaming_calls_callbacks_in_order(monkeypatch):
    events: list[tuple[str, object]] = []

    class FakeContinuationNode:
        def execute(self, session_id: str, player_input: str, **kwargs):
            assert session_id == "session-1"
            assert player_input == "hello"
            assert kwargs["turn_id"] == "turn-fixed"
            kwargs["on_step"]("round_snapshot", {"duration_ms": 1})
            kwargs["on_writer_text"]("accepted text")
            return (
                {"turn_id": "turn-fixed"},
                {},
                {"outcome": "success"},
                {},
                {
                    "turn_id": "turn-fixed",
                    "turn_index": 3,
                    "writer_output": "accepted text",
                },
                {},
            )

    from awp_rp_runtime_v2.nodes import persistent_continuation_turn_node

    monkeypatch.setattr(
        persistent_continuation_turn_node,
        "AWPV2PersistentContinuationTurn",
        FakeContinuationNode,
    )
    monkeypatch.setattr(
        "awp_rp_runtime_v2.runtime.execution_dispatcher._id",
        lambda prefix, seed: f"{prefix}-fixed",
    )

    result = ExecutionDispatcher().execute_turn_streaming(
        "session-1",
        "hello",
        on_started=lambda turn_id, steps: events.append(("started", (turn_id, steps))),
        on_step=lambda name, payload: events.append(("step", (name, payload))),
        on_writer_text=lambda turn_id, text: events.append(("writer_text", (turn_id, text))),
        on_done=lambda payload: events.append(("done", payload)),
    )

    assert result["success"] is True
    assert events == [
        ("started", ("turn-fixed", execution_dispatcher.PIPELINE_STREAM_STEP_NAMES)),
        ("step", ("round_snapshot", {"duration_ms": 1})),
        ("writer_text", ("turn-fixed", "accepted text")),
        (
            "done",
            {
                "success": True,
                "turn_id": "turn-fixed",
                "turn_index": 3,
                "writer_output": "accepted text",
            },
        ),
    ]


def test_execute_turn_streaming_done_reports_failure(monkeypatch):
    events: list[tuple[str, object]] = []

    class FakeContinuationNode:
        def execute(self, **kwargs):
            kwargs["on_step"](
                "director",
                {"duration_ms": 0, "call_success": False, "failure_code": "NO_KEY"},
            )
            return (
                {},
                {},
                {
                    "outcome": "failure",
                    "failure_code": "DIRECTOR_NO_KEY",
                    "failure_message": "missing key",
                },
                {},
                {},
                {},
            )

    from awp_rp_runtime_v2.nodes import persistent_continuation_turn_node

    monkeypatch.setattr(
        persistent_continuation_turn_node,
        "AWPV2PersistentContinuationTurn",
        FakeContinuationNode,
    )

    result = ExecutionDispatcher().execute_turn_streaming(
        "session-1",
        "hello",
        on_started=None,
        on_step=lambda name, payload: events.append(("step", (name, payload))),
        on_writer_text=lambda turn_id, text: events.append(("writer_text", (turn_id, text))),
        on_done=lambda payload: events.append(("done", payload)),
    )

    assert result["success"] is False
    assert events == [
        (
            "step",
            (
                "director",
                {"duration_ms": 0, "call_success": False, "failure_code": "NO_KEY"},
            ),
        ),
        (
            "done",
            {
                "success": False,
                "turn_id": "",
                "turn_index": 0,
                "error": "missing key",
                "failure_code": "DIRECTOR_NO_KEY",
            },
        ),
    ]
