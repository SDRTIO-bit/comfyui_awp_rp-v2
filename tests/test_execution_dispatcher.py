import json
import sys
from pathlib import Path

from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher
from awp_rp_runtime_v2.testing.api_workflow_loader import APIWorkflowLoader


def _node_result(writer_output: str = "accepted text") -> tuple:
    return (
        {"turn_id": "turn-1"},
        {},
        {"outcome": "success"},
        {},
        {"turn_id": "turn-1", "turn_index": 2, "writer_output": writer_output},
        {},
    )


def test_python_mode_calls_node_directly(monkeypatch):
    calls = {}

    class FakeContinuationNode:
        def execute(self, session_id: str, player_input: str, **kwargs):
            calls["session_id"] = session_id
            calls["player_input"] = player_input
            calls["director_profile_id"] = kwargs.get("director_profile_id")
            calls["writer_profile_id"] = kwargs.get("writer_profile_id")
            return _node_result("direct python output")

    from awp_rp_runtime_v2.nodes import persistent_continuation_turn_node

    monkeypatch.setattr(
        persistent_continuation_turn_node,
        "AWPV2PersistentContinuationTurn",
        FakeContinuationNode,
    )

    result = ExecutionDispatcher().execute_turn(
        "session-1",
        "hello",
        mode="python",
    )

    assert calls == {
        "session_id": "session-1",
        "player_input": "hello",
        "director_profile_id": "deepseek-v4-flash-director",
        "writer_profile_id": "deepseek-v4-pro-writer",
    }
    assert result["success"] is True
    assert result["turn_id"] == "turn-1"
    assert result["writer_output"] == "direct python output"


def test_python_mode_profile_env_overrides(monkeypatch):
    calls = {}

    class FakeFirstTurnNode:
        def execute(self, session_id: str, player_input: str, **kwargs):
            calls["session_id"] = session_id
            calls["player_input"] = player_input
            calls["director_profile_id"] = kwargs.get("director_profile_id")
            calls["writer_profile_id"] = kwargs.get("writer_profile_id")
            return _node_result("direct python output")

    from awp_rp_runtime_v2.nodes import persistent_first_turn_node

    monkeypatch.setattr(
        persistent_first_turn_node,
        "AWPV2PersistentFirstTurn",
        FakeFirstTurnNode,
    )
    monkeypatch.setenv("AWP_DIRECTOR_PROFILE_ID", "fake-director")
    monkeypatch.setenv("AWP_WRITER_PROFILE_ID", "fake-writer")

    result = ExecutionDispatcher().execute_first_turn(
        "session-1",
        "hello",
        mode="python",
    )

    assert result["success"] is True
    assert calls == {
        "session_id": "session-1",
        "player_input": "hello",
        "director_profile_id": "fake-director",
        "writer_profile_id": "fake-writer",
    }


def test_python_continue_uses_real_profiles_by_default(monkeypatch):
    calls = {}

    class FakeContinueNode:
        def execute(self, session_id: str, **kwargs):
            calls["session_id"] = session_id
            calls["director_profile_id"] = kwargs.get("director_profile_id")
            calls["writer_profile_id"] = kwargs.get("writer_profile_id")
            return _node_result("direct python output")

    from awp_rp_runtime_v2.nodes import continue_turn_execution_node

    monkeypatch.setattr(
        continue_turn_execution_node,
        "AWPV2ContinueTurn",
        FakeContinueNode,
    )

    result = ExecutionDispatcher().execute_continue("session-1", mode="python")

    assert result["success"] is True
    assert calls == {
        "session_id": "session-1",
        "director_profile_id": "deepseek-v4-flash-director",
        "writer_profile_id": "deepseek-v4-pro-writer",
    }


def test_request_mode_overrides_global(monkeypatch):
    monkeypatch.setenv("AWP_EXECUTION_MODE", "python")
    calls = {}
    dispatcher = ExecutionDispatcher()

    def fake_hybrid(action, session_id, player_input, workflow):
        calls["action"] = action
        calls["session_id"] = session_id
        calls["player_input"] = player_input
        calls["workflow"] = workflow
        return {"success": True, "writer_output": "hybrid"}

    monkeypatch.setattr(dispatcher, "_hybrid", fake_hybrid)

    result = dispatcher.execute_turn(
        "session-1",
        "hello",
        mode="hybrid",
        workflow="custom_flow",
    )

    assert result["writer_output"] == "hybrid"
    assert calls == {
        "action": "turn",
        "session_id": "session-1",
        "player_input": "hello",
        "workflow": "custom_flow",
    }


def test_workflow_param_selects_workflow(monkeypatch):
    dispatcher = ExecutionDispatcher()
    loaded = []
    submitted = {}

    def fake_load_workflow(name):
        loaded.append(name)
        return {
            "1": {
                "class_type": "AWPV2PersistentContinuationTurn",
                "inputs": {"session_id": "", "player_input": ""},
            }
        }

    def fake_submit_and_wait(graph):
        submitted.update(graph["1"]["inputs"])
        return {"success": True}

    monkeypatch.setattr(dispatcher, "_load_workflow", fake_load_workflow)
    monkeypatch.setattr(dispatcher, "_submit_and_wait", fake_submit_and_wait)

    result = dispatcher.execute_turn(
        "session-1",
        "hello",
        mode="hybrid",
        workflow="custom_flow",
    )

    assert result["success"] is True
    assert loaded == ["custom_flow"]
    assert submitted == {"session_id": "session-1", "player_input": "hello"}


def test_hybrid_rejects_workflow_for_wrong_action(monkeypatch):
    dispatcher = ExecutionDispatcher()

    def fake_load_workflow(name):
        return {
            "1": {
                "class_type": "AWPV2PersistentContinuationTurn",
                "inputs": {"session_id": "", "player_input": ""},
            }
        }

    monkeypatch.setattr(dispatcher, "_load_workflow", fake_load_workflow)

    try:
        dispatcher.execute_continue("session-1", mode="hybrid", workflow="send_turn")
    except ValueError as exc:
        assert "not valid for action 'continue'" in str(exc)
    else:
        raise AssertionError("Expected mismatched workflow to be rejected")


def test_load_workflow_works_when_package_loaded_from_custom_nodes(monkeypatch, tmp_path):
    package_root = Path(__file__).resolve().parents[1]
    custom_nodes_root = package_root.parent
    cleaned_path = [
        path
        for path in sys.path
        if Path(path or ".").resolve() != package_root
    ]
    monkeypatch.setattr(sys, "path", [str(custom_nodes_root), *cleaned_path])
    monkeypatch.chdir(tmp_path)
    monkeypatch.delitem(sys.modules, "testing", raising=False)

    graph = ExecutionDispatcher()._load_workflow("send_turn")

    assert graph


def test_api_workflow_loader_default_path_is_package_relative(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    workflows = APIWorkflowLoader().list_workflows()

    assert workflows == ["continue_world", "first_turn", "send_turn"]


def test_extract_turn_result_from_comfy_history_ui_payload():
    projection = {
        "turn_id": "turn-9",
        "turn_index": 4,
        "diagnostic_status": "success",
    }
    history = {
        "outputs": {
            "10": {"ui": {"awp_accepted_text": ["full accepted text"]}},
            "11": {"ui": {"awp_turn_result_json": [json.dumps(projection)]}},
        }
    }

    result = ExecutionDispatcher()._extract_turn_result_from_history(history)

    assert result["success"] is True
    assert result["turn_id"] == "turn-9"
    assert result["turn_index"] == 4
    assert result["writer_output"] == "full accepted text"


def test_extract_turn_result_from_comfy_history_top_level_failure_payload():
    projection = {
        "turn_id": "",
        "turn_index": 0,
        "diagnostic_status": "failure",
        "failure_code": "SESSION_LOAD_FAILED",
        "failure_message": "No CardSessionBinding",
    }
    history = {
        "outputs": {
            "10": {"awp_accepted_text": [""]},
            "11": {"awp_turn_result_json": [json.dumps(projection)]},
        }
    }

    result = ExecutionDispatcher()._extract_turn_result_from_history(history)

    assert result["success"] is False
    assert result["diagnostics"]["failure_code"] == "SESSION_LOAD_FAILED"
    assert result["diagnostics"]["failure_message"] == "No CardSessionBinding"
