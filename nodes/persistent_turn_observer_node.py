"""Read-only observer for persistent turn execution outputs."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


class AWPV2PersistentTurnObserver:
    """Splits a persistent turn result into observable, side-effect-free views."""

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "receipt": ("FIRST_TURN_RECEIPT",),
                "context": ("JSON",),
                "diagnostics": ("FIRST_TURN_DIAGNOSTICS",),
                "card_state": ("CARD_STATE",),
                "turn_record": ("TURN_RECORD",),
                "round_snapshot": ("ROUND_SNAPSHOT",),
            },
        }

    RETURN_TYPES = (
        "EXECUTION_TRACE",
        "JSON",
        "JSON",
        "JSON",
        "JSON",
        "JSON",
        "JSON",
        "JSON",
    )
    RETURN_NAMES = (
        "execution_trace",
        "director_observation",
        "sub_agents_observation",
        "writer_observation",
        "quality_observation",
        "state_observation",
        "memory_observation",
        "full_observation",
    )
    FUNCTION = "execute"
    CATEGORY = "AWP V2/Observability"

    def execute(
        self,
        receipt: dict[str, Any],
        context: dict[str, Any],
        diagnostics: dict[str, Any],
        card_state: dict[str, Any],
        turn_record: dict[str, Any],
        round_snapshot: dict[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        receipt = _as_dict(receipt)
        context = _as_dict(context)
        diagnostics = _as_dict(diagnostics)
        card_state = _as_dict(card_state)
        turn_record = _as_dict(turn_record)
        round_snapshot = _as_dict(round_snapshot)

        effects = _as_dict(context.get("effects"))
        delegation = _as_dict(effects.get("delegation"))
        state_effects = _as_dict(effects.get("state_effects"))
        memory_effects = _as_dict(effects.get("memory_effects"))
        writer_output = str(turn_record.get("writer_output", "") or "")

        director = {
            "stage": "director",
            "profile_id": diagnostics.get("director_profile_id", ""),
            "provider_type": diagnostics.get("director_provider_type", ""),
            "model": diagnostics.get("director_model", ""),
            "call_success": bool(diagnostics.get("director_call_success", False)),
            "plan_ref": diagnostics.get("director_plan_ref", ""),
            "tool_use": delegation.get("director_tools", {}),
            "failure_code": diagnostics.get("director_failure_code", ""),
        }
        sub_agents = {
            "stage": "sub_agents",
            "source": delegation.get("source", ""),
            "plan_id": delegation.get("plan_id", ""),
            "director_requested": delegation.get("director_requested", []),
            "executed": delegation.get("executed", []),
            "parallelism": delegation.get("parallelism", 0),
            "trigger_diagnostics": delegation.get("trigger_diagnostics", []),
            "agent_dispositions": diagnostics.get("agent_dispositions", {}),
        }
        writer = {
            "stage": "writer",
            "profile_id": diagnostics.get("writer_profile_id", ""),
            "provider_type": diagnostics.get("writer_provider_type", ""),
            "model": diagnostics.get("writer_model", ""),
            "call_success": bool(diagnostics.get("writer_call_success", False)),
            "text_length": len(writer_output),
            "text_hash": _text_hash(writer_output),
            "turn_id": turn_record.get("turn_id", receipt.get("turn_id", "")),
            "failure_code": diagnostics.get("writer_failure_code", ""),
        }
        quality = {
            "stage": "quality",
            "verdict": diagnostics.get("quality_verdict", ""),
            "blocking_reasons": diagnostics.get("quality_blocking_reasons", []),
            "outcome": diagnostics.get("outcome", ""),
            "failure_code": diagnostics.get("failure_code", ""),
            "failure_message": diagnostics.get("failure_message", ""),
        }
        state = {
            "stage": "state",
            "commit_status": diagnostics.get("card_state_commit_status", ""),
            "revision_before": diagnostics.get("card_state_revision_before", 0),
            "revision_after": diagnostics.get("card_state_revision_after", 0),
            "current_revision": card_state.get("revision", 0),
            "effects": state_effects,
        }
        memory = {
            "stage": "memory",
            "curation_status": diagnostics.get("memory_curation_status", ""),
            "curation_reason": diagnostics.get("memory_curation_reason", ""),
            "commit_ids": diagnostics.get("memory_commit_ids", []),
            "active_memory_committed_ids": diagnostics.get("active_memory_committed_ids", []),
            "rag_memory_committed_ids": diagnostics.get("rag_memory_committed_ids", []),
            "effects": memory_effects,
        }

        trace = self._build_trace(diagnostics, receipt, round_snapshot, effects)
        full = {
            "schema_id": "awp.rp.persistent-turn-observation.v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "receipt": receipt,
            "context": context,
            "diagnostics": diagnostics,
            "director": director,
            "sub_agents": sub_agents,
            "writer": writer,
            "quality": quality,
            "state": state,
            "memory": memory,
        }

        return (trace, director, sub_agents, writer, quality, state, memory, full)

    def _build_trace(
        self,
        diagnostics: dict[str, Any],
        receipt: dict[str, Any],
        round_snapshot: dict[str, Any],
        effects: dict[str, Any],
    ) -> dict[str, Any]:
        timings = _as_dict(diagnostics.get("step_timings_ms"))
        steps = list(diagnostics.get("steps_completed", []) or [])
        failed = set(diagnostics.get("steps_failed", []) or [])
        events = []
        for index, step in enumerate(steps):
            events.append({
                "event_id": f"obs_{index:02d}_{step}",
                "event_type": step,
                "timestamp": receipt.get("created_at", ""),
                "actor": step.split(":", 1)[0],
                "duration_ms": int(timings.get(step, 0) or 0),
                "details": {"source": "persistent_turn_diagnostics"},
                "success": step not in failed,
                "error": diagnostics.get("failure_message", "") if step in failed else None,
            })
        director_tools = _as_dict(_as_dict(effects.get("delegation")).get("director_tools"))
        return {
            "schema_id": "awp.rp.execution-trace.v1",
            "schema_version": 1,
            "trace_id": diagnostics.get("trace_id", receipt.get("trace_id", "")),
            "turn_id": receipt.get("turn_id", ""),
            "card_id": round_snapshot.get("card_id", receipt.get("logical_card_id", "")),
            "session_id": diagnostics.get("session_id", receipt.get("session_id", "")),
            "events": events,
            "total_duration_ms": sum(int(v or 0) for v in timings.values()),
            "total_llm_calls": int(bool(diagnostics.get("director_call_success"))) + int(bool(diagnostics.get("writer_call_success"))),
            "total_tool_calls": len(director_tools.get("requested", []) or []),
            "success": diagnostics.get("outcome", "") == "success",
        }


NODE_CLASS_MAPPINGS = {
    "AWPV2PersistentTurnObserver": AWPV2PersistentTurnObserver,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AWPV2PersistentTurnObserver": "AWP V2 Persistent Turn Observer",
}
