"""Execution dispatcher for Python-direct and ComfyUI queued workflows."""

from __future__ import annotations

import json
import os
from typing import Any

from .default_model_profiles import profile_ids_from_env
from .persistent_turn_engine import _id
from .runtime_store_factory import RuntimeStoreFactory


DEFAULT_WORKFLOWS = {
    "turn": "send_turn",
    "first_turn": "first_turn",
    "continue": "continue_world",
}

WORKFLOW_ACTION_NODE_TYPES = {
    "turn": {"AWPV2PersistentContinuationTurn"},
    "first_turn": {"AWPV2PersistentFirstTurn"},
    "continue": {"AWPV2ContinueTurnP1", "AWPV2ContinueTurn"},
}

PIPELINE_STREAM_STEP_NAMES = [
    "round_snapshot",
    "director",
    "director_delegation",
    "sub_agents",
    "writer",
    "quality_gate",
    "turn_evolution_curator",
    "state_commit",
    "memory_curator",
]


def _global_mode() -> str:
    return os.environ.get("AWP_EXECUTION_MODE", "hybrid").strip().lower() or "hybrid"


def _python_profile_ids() -> tuple[str, str]:
    return profile_ids_from_env()


class ExecutionDispatcher:
    def __init__(self, registry: Any | None = None) -> None:
        self._registry = registry

    def _reg(self):
        if self._registry is None:
            self._registry = RuntimeStoreFactory.from_env().registry
        return self._registry

    def execute_turn(
        self,
        session_id: str,
        player_input: str,
        mode: str = "",
        workflow: str = "",
    ) -> dict[str, Any]:
        selected_mode = (mode or _global_mode()).strip().lower()
        if selected_mode == "python":
            return self._python_turn(session_id, player_input)
        return self._hybrid("turn", session_id, player_input, workflow)

    def execute_first_turn(
        self,
        session_id: str,
        player_input: str,
        mode: str = "",
        workflow: str = "",
    ) -> dict[str, Any]:
        selected_mode = (mode or _global_mode()).strip().lower()
        if selected_mode == "python":
            return self._python_first_turn(session_id, player_input)
        return self._hybrid("first_turn", session_id, player_input, workflow)

    def execute_continue(
        self,
        session_id: str,
        mode: str = "",
        workflow: str = "",
    ) -> dict[str, Any]:
        selected_mode = (mode or _global_mode()).strip().lower()
        if selected_mode == "python":
            return self._python_continue(session_id)
        return self._hybrid("continue", session_id, "", workflow)

    def _python_turn(self, session_id: str, player_input: str) -> dict[str, Any]:
        from ..nodes.persistent_continuation_turn_node import (
            AWPV2PersistentContinuationTurn,
        )

        director_profile_id, writer_profile_id = _python_profile_ids()
        result = AWPV2PersistentContinuationTurn().execute(
            session_id=session_id,
            player_input=player_input,
            director_profile_id=director_profile_id,
            writer_profile_id=writer_profile_id,
        )
        return self._extract_turn_result(result)

    def execute_turn_streaming(
        self,
        session_id: str,
        player_input: str,
        mode: str = "",
        workflow: str = "",
        on_started=None,
        on_step=None,
        on_writer_text=None,
        on_done=None,
    ) -> dict[str, Any]:
        selected_mode = (mode or "python").strip().lower()
        if selected_mode != "python":
            if on_started is not None:
                on_started("", ["queued_workflow"])
            result = self.execute_turn(session_id, player_input, mode=mode, workflow=workflow)
            if on_done is not None:
                on_done({
                    "success": result["success"],
                    "turn_id": result.get("turn_id", ""),
                    "turn_index": result.get("turn_index", 0),
                    **({"writer_output": result.get("writer_output", "")} if result["success"] else {
                        "error": result.get("diagnostics", {}).get("failure_message", "Turn failed"),
                        "failure_code": result.get("diagnostics", {}).get("failure_code", ""),
                    }),
                })
            return result

        from ..nodes.persistent_continuation_turn_node import (
            AWPV2PersistentContinuationTurn,
        )

        seed = f"{session_id}:{player_input}"
        request_id = _id("ctr", seed)
        workflow_run_id = _id("wfr", seed)
        trace_id = _id("trc", seed)
        turn_id = _id("turn", seed)
        attempt_id = _id("att", seed)
        director_profile_id, writer_profile_id = _python_profile_ids()

        if on_started is not None:
            on_started(turn_id, list(PIPELINE_STREAM_STEP_NAMES))

        def _on_writer_text(text: str) -> None:
            if on_writer_text is not None:
                on_writer_text(turn_id, text)

        result_tuple = AWPV2PersistentContinuationTurn().execute(
            session_id=session_id,
            player_input=player_input,
            workflow_run_id=workflow_run_id,
            trace_id=trace_id,
            turn_id=turn_id,
            attempt_id=attempt_id,
            request_id=request_id,
            director_profile_id=director_profile_id,
            writer_profile_id=writer_profile_id,
            on_step=on_step,
            on_writer_text=_on_writer_text,
        )
        result = self._extract_turn_result(result_tuple)
        done_payload: dict[str, Any] = {
            "success": result["success"],
            "turn_id": result.get("turn_id", ""),
            "turn_index": result.get("turn_index", 0),
        }
        if result["success"]:
            done_payload["writer_output"] = result.get("writer_output", "")
        else:
            diagnostics = result.get("diagnostics", {})
            done_payload["error"] = diagnostics.get("failure_message", "Turn failed")
            done_payload["failure_code"] = diagnostics.get("failure_code", "")
        if on_done is not None:
            on_done(done_payload)
        return result

    def _python_first_turn(self, session_id: str, player_input: str) -> dict[str, Any]:
        from ..nodes.persistent_first_turn_node import AWPV2PersistentFirstTurn

        director_profile_id, writer_profile_id = _python_profile_ids()
        result = AWPV2PersistentFirstTurn().execute(
            session_id=session_id,
            player_input=player_input,
            director_profile_id=director_profile_id,
            writer_profile_id=writer_profile_id,
        )
        return self._extract_turn_result(result)

    def _python_continue(self, session_id: str) -> dict[str, Any]:
        from ..nodes.continue_turn_execution_node import AWPV2ContinueTurn

        director_profile_id, writer_profile_id = _python_profile_ids()
        result = AWPV2ContinueTurn().execute(
            session_id=session_id,
            director_profile_id=director_profile_id,
            writer_profile_id=writer_profile_id,
        )
        return self._extract_turn_result(result)

    def _hybrid(
        self,
        action: str,
        session_id: str,
        player_input: str,
        workflow: str,
    ) -> dict[str, Any]:
        workflow_name = workflow or DEFAULT_WORKFLOWS[action]
        graph = self._load_workflow(workflow_name)
        self._validate_workflow_action(action, workflow_name, graph)
        self._fill_inputs(graph, session_id, player_input)
        return self._submit_and_wait(graph)

    def _load_workflow(self, name: str) -> dict[str, Any]:
        from ..testing.api_workflow_loader import APIWorkflowLoader

        return APIWorkflowLoader().load(name)

    def _validate_workflow_action(
        self,
        action: str,
        workflow_name: str,
        graph: dict[str, Any],
    ) -> None:
        expected = WORKFLOW_ACTION_NODE_TYPES.get(action, set())
        if not expected:
            return
        class_types = {
            str(node_def.get("class_type", ""))
            for node_def in graph.values()
            if isinstance(node_def, dict)
        }
        if class_types.intersection(expected):
            return
        expected_text = ", ".join(sorted(expected))
        actual_text = ", ".join(sorted(item for item in class_types if item)) or "(none)"
        raise ValueError(
            f"Workflow '{workflow_name}' is not valid for action '{action}'. "
            f"Expected one of: {expected_text}. Actual node types: {actual_text}"
        )

    def _fill_inputs(
        self,
        graph: dict[str, Any],
        session_id: str,
        player_input: str,
    ) -> None:
        for node_def in graph.values():
            if not isinstance(node_def, dict):
                continue
            inputs = node_def.get("inputs", {})
            if not isinstance(inputs, dict):
                continue
            if "session_id" in inputs:
                inputs["session_id"] = session_id
            if "player_input" in inputs and player_input:
                inputs["player_input"] = player_input

    def _submit_and_wait(self, graph: dict[str, Any]) -> dict[str, Any]:
        from ..testing.comfy_api_client import ComfyAPIClient

        client = ComfyAPIClient()
        if not client.is_available():
            raise RuntimeError("ComfyUI server not available for hybrid mode")
        queued = client.queue_prompt(graph)
        if not queued or "prompt_id" not in queued:
            raise RuntimeError("ComfyUI did not return a prompt_id")
        history = client.wait_for_completion(queued["prompt_id"], timeout_seconds=180)
        if not history:
            raise TimeoutError(f"ComfyUI prompt timed out: {queued['prompt_id']}")
        return self._extract_turn_result_from_history(history)

    def _extract_turn_result(self, result: tuple) -> dict[str, Any]:
        turn_record = result[4] if len(result) > 4 else {}
        diagnostics = result[2] if len(result) > 2 else {}
        if not isinstance(turn_record, dict):
            turn_record = {}
        if not isinstance(diagnostics, dict):
            diagnostics = {}
        return {
            "success": diagnostics.get("outcome") == "success",
            "turn_id": turn_record.get("turn_id", ""),
            "turn_index": turn_record.get("turn_index", 0),
            "writer_output": turn_record.get("writer_output", ""),
            "diagnostics": diagnostics,
        }

    def _extract_turn_result_from_history(self, history: dict[str, Any]) -> dict[str, Any]:
        outputs = self._history_outputs(history)
        writer_output = ""
        projection: dict[str, Any] = {}

        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            ui = node_output.get("ui", {})
            if isinstance(ui, dict):
                accepted = ui.get("awp_accepted_text")
                if isinstance(accepted, list) and accepted:
                    writer_output = str(accepted[0] or "")
                turn_results = ui.get("awp_turn_result_json")
                if isinstance(turn_results, list) and turn_results:
                    try:
                        projection = json.loads(str(turn_results[0] or "{}"))
                    except json.JSONDecodeError:
                        projection = {}
            accepted = node_output.get("awp_accepted_text")
            if isinstance(accepted, list) and accepted and not writer_output:
                writer_output = str(accepted[0] or "")
            turn_results = node_output.get("awp_turn_result_json")
            if isinstance(turn_results, list) and turn_results:
                try:
                    projection = json.loads(str(turn_results[0] or "{}"))
                except json.JSONDecodeError:
                    projection = {}
            if not writer_output and isinstance(node_output.get("text"), str):
                writer_output = node_output["text"]

        diagnostics = {
            "outcome": projection.get("diagnostic_status", "success"),
            "failure_code": projection.get("failure_code", ""),
            "failure_message": projection.get("failure_message", ""),
            "projection": projection,
        }
        return {
            "success": diagnostics["outcome"] == "success",
            "turn_id": projection.get("turn_id", ""),
            "turn_index": projection.get("turn_index", 0),
            "writer_output": writer_output,
            "diagnostics": diagnostics,
        }

    def _history_outputs(self, history: dict[str, Any]) -> dict[str, Any]:
        if "outputs" in history and isinstance(history["outputs"], dict):
            return history["outputs"]
        for value in history.values():
            if isinstance(value, dict) and isinstance(value.get("outputs"), dict):
                return value["outputs"]
        return {}
