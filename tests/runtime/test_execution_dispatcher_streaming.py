from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher


def test_streaming_dispatcher_respects_non_python_mode(monkeypatch):
    calls = {}

    def fake_execute_turn(self, session_id, player_input, mode="", workflow=""):
        calls["session_id"] = session_id
        calls["player_input"] = player_input
        calls["mode"] = mode
        calls["workflow"] = workflow
        return {
            "success": True,
            "turn_id": "turn-hybrid",
            "turn_index": 3,
            "writer_output": "accepted",
            "diagnostics": {},
        }

    monkeypatch.setattr(ExecutionDispatcher, "execute_turn", fake_execute_turn)
    events = []

    result = ExecutionDispatcher().execute_turn_streaming(
        "sess1",
        "hello",
        mode="hybrid",
        workflow="send_turn",
        on_started=lambda turn_id, steps: events.append(("started", turn_id, steps)),
        on_done=lambda payload: events.append(("done", payload)),
    )

    assert calls == {
        "session_id": "sess1",
        "player_input": "hello",
        "mode": "hybrid",
        "workflow": "send_turn",
    }
    assert events[0] == ("started", "", ["queued_workflow"])
    assert events[1] == ("done", {
        "success": True,
        "turn_id": "turn-hybrid",
        "turn_index": 3,
        "writer_output": "accepted",
    })
    assert result["turn_id"] == "turn-hybrid"
