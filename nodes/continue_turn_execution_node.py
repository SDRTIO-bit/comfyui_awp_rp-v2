"""AWPV2ContinueTurn — formal Continue that advances the world.

P1 Continue semantics:
  - Creates a new logical turn (new request_id, turn_id)
  - Uses a controlled continue instruction, NOT just "continue"
  - Director can decide to push events, NPC actions, time, relationships
  - Still goes through the full canonical persistent path:
    Director → SubAgents → Writer → QualityGate → Curator → StateCommit
    → TurnRecordCommit → MemoryCommit
  - Still produces real state patches, real memory, real effects

The continue instruction tells the Director this is a world-advance turn:
  "The player wants the world to progress. Move time, advance events,
   have NPCs act, resolve tensions, or introduce new developments."
"""

from __future__ import annotations

import hashlib
from typing import Any

from ..contracts.first_turn_diagnostics import FirstTurnDiagnostics
from ..contracts.first_turn_receipt import FirstTurnReceipt
from ..runtime.default_model_profiles import (
    DEFAULT_DIRECTOR_PROFILE_ID,
    DEFAULT_WRITER_PROFILE_ID,
)
from ..runtime.persistent_turn_engine import PersistentTurnEngine, _id, _now
from ..runtime.runtime_store_factory import RuntimeStoreFactory
from ..runtime.session_runtime_load import SessionRuntimeLoad
from ..adapters.llm.model_profile_registry import ModelProfileRegistry


# The controlled continue instruction — NOT just "continue"
CONTINUE_INSTRUCTION = (
    "[Continue] The player has chosen to let the world advance. "
    "As the narrative director, you should consider: "
    "moving time forward, having NPCs take independent actions, "
    "advancing or resolving existing plot threads, "
    "introducing environmental changes or new developments, "
    "or shifting the scene naturally. "
    "The writer should produce a narrative that feels like the world "
    "is alive and progressing on its own, not just waiting for the player."
)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _continue_seed(
    session_id: str,
    request_id: str = "",
    turn_id: str = "",
    run_id: str = "",
    entropy: str = "",
) -> str:
    if request_id or turn_id or run_id:
        return f"{session_id}:continue:{request_id}:{turn_id}:{run_id}"
    if not entropy:
        import time as _time
        entropy = str(_time.time())
    return f"{session_id}:continue:{entropy}"


def _cache_identity(session_id: str) -> tuple[str, int, str, int, str]:
    try:
        factory = RuntimeStoreFactory.from_env()
        registry = factory.registry
        binding = registry.card_session_binding_store.load(session_id)
        if binding is None:
            return "", 0, "", 0, ""
        card_state = registry.card_state_store.load(binding.logical_card_id, session_id)
        latest_turn = registry.turn_record_store.get_recent(binding.logical_card_id, session_id, limit=1)
        latest_turn_id = latest_turn[0].turn_id if latest_turn else ""
        revision = card_state.revision if card_state is not None else 0
        return (
            binding.logical_card_id,
            int(binding.card_version),
            str(binding.source_hash or ""),
            int(revision),
            latest_turn_id,
        )
    except Exception:
        return "", 0, "", 0, ""


def _build_replayed_receipt(
    existing_record,
    request_id: str,
    workflow_run_id: str,
    session_id: str,
    binding: Any,
    now: str,
) -> FirstTurnReceipt:
    return FirstTurnReceipt(
        receipt_id=_id("continue_replay", request_id),
        request_id=request_id,
        workflow_run_id=workflow_run_id,
        trace_id=existing_record.trace_id,
        turn_id=existing_record.turn_id,
        attempt_id="",
        session_id=session_id,
        logical_card_id=binding.logical_card_id,
        card_version=binding.card_version,
        source_hash=binding.source_hash,
        accepted_text=existing_record.writer_output[:200] if existing_record.writer_output else "",
        quality_verdict="accept",
        base_card_state_revision=existing_record.base_card_state_revision,
        result_card_state_revision=existing_record.result_card_state_revision,
        card_state_commit_status="accepted",
        turn_record_id=existing_record.turn_id,
        turn_index=existing_record.turn_index,
        turn_record_commit_status="committed",
        memory_curation_status="noop",
        idempotency_status="replayed",
        created_at=now,
    )


class AWPV2ContinueTurn:
    """Execute a Continue turn using RuntimeStoreFactory + SQLite.

    Continue is NOT just returning a string. It creates a new turn
    that can advance the world, move time, trigger NPC actions,
    and evolve state.
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "session_id": ("STRING", {"default": ""}),
            },
            "optional": {
                "workflow_run_id": ("STRING", {"default": ""}),
                "trace_id": ("STRING", {"default": ""}),
                "turn_id": ("STRING", {"default": ""}),
                "attempt_id": ("STRING", {"default": ""}),
                "request_id": ("STRING", {"default": ""}),
                "run_id": ("STRING", {"default": ""}),
                "director_profile_id": ("STRING", {"default": DEFAULT_DIRECTOR_PROFILE_ID}),
                "writer_profile_id": ("STRING", {"default": DEFAULT_WRITER_PROFILE_ID}),
                "writer_preset_path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = (
        "FIRST_TURN_RECEIPT", "JSON", "FIRST_TURN_DIAGNOSTICS",
        "CARD_STATE", "TURN_RECORD", "ROUND_SNAPSHOT",
    )
    RETURN_NAMES = (
        "receipt", "continue_context", "diagnostics",
        "card_state", "turn_record", "round_snapshot",
    )
    FUNCTION = "execute"
    CATEGORY = "AWP V2/Persistent Runtime"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(
        cls,
        session_id: str,
        workflow_run_id: str = "",
        trace_id: str = "",
        turn_id: str = "",
        attempt_id: str = "",
        request_id: str = "",
        run_id: str = "",
        director_profile_id: str = DEFAULT_DIRECTOR_PROFILE_ID,
        writer_profile_id: str = DEFAULT_WRITER_PROFILE_ID,
        writer_preset_path: str = "",
    ):
        logical_card_id, card_version, source_hash, revision, latest_turn_id = _cache_identity(session_id)
        return (
            "continue",
            session_id,
            turn_id,
            request_id,
            "",  # No player_input hash for continue
            logical_card_id,
            card_version,
            source_hash,
            revision,
            latest_turn_id,
            director_profile_id,
            writer_profile_id,
            writer_preset_path,
        )

    def execute(
        self,
        session_id: str,
        workflow_run_id: str = "",
        trace_id: str = "",
        turn_id: str = "",
        attempt_id: str = "",
        request_id: str = "",
        run_id: str = "",
        director_profile_id: str = DEFAULT_DIRECTOR_PROFILE_ID,
        writer_profile_id: str = DEFAULT_WRITER_PROFILE_ID,
        writer_preset_path: str = "",
    ) -> tuple:
        now = _now()
        # Continue creates a new turn by default, but explicit request identity
        # must stay deterministic so idempotent replay can work.
        seed = _continue_seed(session_id, request_id, turn_id, run_id)

        if not request_id:
            request_id = _id("continue", seed)
        if not workflow_run_id:
            workflow_run_id = _id("wfr", seed)
        if not trace_id:
            trace_id = _id("trc", seed)
        if not turn_id:
            turn_id = _id("turn", seed)
        if not attempt_id:
            attempt_id = _id("att", seed)

        try:
            ModelProfileRegistry.resolve(director_profile_id)
            ModelProfileRegistry.resolve(writer_profile_id)
        except ValueError as e:
            diag = FirstTurnDiagnostics(
                diagnostics_id=_id("ctd", request_id),
                request_id=request_id,
                trace_id=trace_id,
                session_id=session_id,
                outcome="failure",
                failure_message=str(e),
                steps_failed=["model_profile_validation"],
                failure_code="UNKNOWN_PROFILE",
            )
            return ({}, {}, diag.to_dict(), {}, {}, {})

        factory = RuntimeStoreFactory.from_env()
        registry = factory.registry

        # Idempotent replay check
        existing_record = registry.turn_record_store.load(turn_id)
        if existing_record is not None:
            binding = registry.card_session_binding_store.load(session_id)
            if existing_record.session_id != session_id or binding is None:
                diag = FirstTurnDiagnostics(
                    diagnostics_id=_id("ctd", request_id),
                    request_id=request_id,
                    trace_id=trace_id,
                    session_id=session_id,
                    outcome="failure",
                    failure_message=f"Turn '{turn_id}' cannot be replayed for session '{session_id}'",
                    steps_failed=["session_binding_conflict"],
                    failure_code="SESSION_BINDING_CONFLICT",
                )
                return ({}, {}, diag.to_dict(), {}, {}, {})

            cs = registry.card_state_store.load(binding.logical_card_id, session_id)
            replayed_receipt = _build_replayed_receipt(
                existing_record, request_id, workflow_run_id, session_id, binding, now,
            )
            diag = FirstTurnDiagnostics(
                diagnostics_id=_id("ctd", request_id),
                request_id=request_id, trace_id=trace_id,
                session_id=session_id, outcome="success",
                steps_completed=["idempotent_replay"],
                agent_dispositions={"replay": "replayed"},
                turn_record_commit_status="replayed",
                card_state_commit_status="replayed",
                turn_record_id=existing_record.turn_id,
                trace_persisted=True,
            )
            ctx = {
                "turn_id": existing_record.turn_id,
                "turn_index": existing_record.turn_index,
                "turn_kind": "continue",
                "session_id": session_id,
                "logical_card_id": binding.logical_card_id,
                "idempotency_status": "replayed",
                "recoverable_accepted_text_ref": existing_record.turn_id,
                "created_at": now,
            }
            return (
                replayed_receipt.to_dict(), ctx, diag.to_dict(),
                cs.to_dict() if cs else {},
                existing_record.to_dict(), {},
            )

        # Load session state
        loader = SessionRuntimeLoad(registry)
        bundle = loader.load(
            session_id=session_id,
            player_input=CONTINUE_INSTRUCTION,
        )
        if not bundle.is_valid:
            diag = FirstTurnDiagnostics(
                diagnostics_id=_id("ctd", request_id),
                request_id=request_id, trace_id=trace_id,
                session_id=session_id, outcome="failure",
                failure_message="; ".join(bundle.load_errors),
                steps_failed=["session_load"],
                failure_code="SESSION_LOAD_FAILED",
            )
            return ({}, {}, diag.to_dict(), {}, {}, {})

        # Execute through the canonical persistent engine
        engine = PersistentTurnEngine(registry, profile=factory.profile)
        return engine.execute(
            session_id=session_id,
            player_input=CONTINUE_INSTRUCTION,
            binding=bundle.card_session_binding,
            snapshot=bundle.round_snapshot,
            card_state=bundle.card_state,
            turn_id=turn_id,
            attempt_id=attempt_id,
            request_id=request_id,
            workflow_run_id=workflow_run_id,
            trace_id=trace_id,
            director_profile_id=director_profile_id,
            writer_profile_id=writer_profile_id,
            turn_kind="continue",
            writer_preset_path=writer_preset_path,
            opening_context=bundle.opening_record.to_dict(),
            worldbook_context=bundle.worldbook_retrieval.get("activated_content", []),
        )


NODE_CLASS_MAPPINGS = {
    "AWPV2ContinueTurn": AWPV2ContinueTurn,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "AWPV2ContinueTurn": "AWP V2 Continue Turn (World Advance)",
}
