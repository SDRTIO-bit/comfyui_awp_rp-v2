"""Management API — REST endpoints for the AWP RP management panel.

Provides session listing, turn history, card browsing, and session
continuation via HTTP. Designed for the React SPA frontend.

All routes are prefixed with /awp/api/v1/.
The SPA static files are served at /awp/.
"""

from __future__ import annotations

import asyncio
import functools
import json
import shlex
import uuid
from pathlib import Path
from typing import Any

from ..runtime.runtime_store_factory import RuntimeStoreFactory

# ── Helpers ──────────────────────────────────────────────────────────────────

_MANAGEMENT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def _resolve_static_asset_path(tail: str) -> Path | None:
    """Resolve an SPA asset path without allowing traversal outside dist."""
    if not tail:
        return None
    root = _MANAGEMENT_DIR.resolve()
    candidate = (root / tail).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _mime_type(suffix: str) -> str:
    return {
        ".html": "text/html",
        ".js": "application/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
    }.get(suffix, "application/octet-stream")


# ── API Routes (only register inside ComfyUI) ────────────────────────────────

try:
    import server
    from aiohttp import web

    def _json(data: Any, status: int = 200) -> web.Response:
        return web.json_response(
            {"data": data}, status=status,
            dumps=lambda o: json.dumps(o, ensure_ascii=False, default=str),
        )

    def _factory() -> RuntimeStoreFactory:
        return RuntimeStoreFactory.from_env()

    def _redact_pipeline_details(details: Any) -> dict[str, Any]:
        """Remove raw text previews from trace details returned by the API."""
        if not isinstance(details, dict):
            return {}
        redacted = dict(details)
        for key in ("output_preview", "candidate_text", "raw_text", "prompt", "system_prompt"):
            redacted.pop(key, None)
        return redacted

    async def _run_blocking(func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    def _console_result(
        command: str,
        output: str,
        data: Any = None,
        ok: bool = True,
    ) -> dict[str, Any]:
        return {
            "ok": ok,
            "command": command,
            "output": output,
            "data": data if data is not None else {},
        }

    def _turn_to_console_dict(turn: Any) -> dict[str, Any]:
        return {
            "turn_id": turn.turn_id,
            "turn_index": turn.turn_index,
            "mode": turn.mode.value,
            "player_input": turn.player_input,
            "writer_output": turn.writer_output,
            "base_card_state_revision": turn.base_card_state_revision,
            "result_card_state_revision": turn.result_card_state_revision,
            "accepted_at": turn.accepted_at,
            "created_at": turn.created_at,
            "trace_id": turn.trace_id,
        }

    def _run_console_command(command: str, session_id: str = "") -> dict[str, Any]:
        command = str(command or "").strip()[:500]
        session_id = str(session_id or "").strip()
        if not command:
            return _console_result(command, "No command.", ok=False)

        try:
            parts = shlex.split(command)
        except ValueError as e:
            return _console_result(command, f"Command parse error: {e}", ok=False)
        name = parts[0].lower()
        args = parts[1:]
        allowed = [
            "help", "context", "cards", "sessions", "new", "session",
            "history", "turns", "transcript", "state", "send", "continue",
            "workflows", "presets", "echo", "clear",
        ]

        if name == "help":
            return _console_result(
                command,
                "Available commands: " + ", ".join(allowed),
                {
                    "commands": {
                        "help": "Show safe console commands.",
                        "context": "Return AI-readable session context.",
                        "cards": "List imported cards.",
                        "sessions": "List sessions.",
                        "new <card_id> [greeting_id]": "Create a new session from a card.",
                        "session": "Show current session metadata.",
                        "history [n]": "Alias for turns [n].",
                        "turns [n]": "Show latest n turns, default 5.",
                        "transcript": "Print profile, opening, all turns, and state as terminal text.",
                        "state": "Show current CardState.",
                        "send <text>": "Send a player message to the current session using Python direct mode.",
                        "continue": "Continue the current session using Python direct mode.",
                        "workflows": "List API workflows.",
                        "presets": "List writer presets.",
                        "echo <text>": "Echo text for console checks.",
                        "clear": "Cleared locally by the frontend.",
                    },
                    "shell": False,
                },
            )

        if name == "clear":
            return _console_result(command, "Console cleared locally.", {"local_only": True})

        if name == "echo":
            return _console_result(command, " ".join(args), {"text": " ".join(args)})

        if name == "workflows":
            from ..testing.api_workflow_loader import APIWorkflowLoader

            loader = APIWorkflowLoader()
            workflows = []
            for workflow_name in loader.list_workflows():
                workflow = loader.load(workflow_name)
                class_types = sorted({
                    node_def.get("class_type", "")
                    for node_def in workflow.values()
                    if isinstance(node_def, dict)
                })
                workflows.append({
                    "name": workflow_name,
                    "node_count": len(workflow),
                    "class_types": class_types,
                })
            return _console_result(command, f"{len(workflows)} workflows.", {"workflows": workflows})

        if name == "presets":
            from ..presets.writer_preset_loader import WriterPresetLoader

            presets = WriterPresetLoader().list_presets()
            return _console_result(command, f"{len(presets)} writer presets.", {"presets": presets})

        if name == "cards":
            factory = _factory()
            cards = []
            for card in factory.registry.card_definition_store.list_all():
                cards.append({
                    "card_id": card.logical_card_id,
                    "version": card.card_version,
                    "name": card.display_name or card.name or card.logical_card_id,
                    "status": card.status,
                    "greeting_count": len(card.greetings or []),
                    "worldbook_count": len(card.worldbook_catalog or []),
                    "created_at": card.created_at,
                })
            return _console_result(command, f"{len(cards)} cards.", {"cards": cards})

        if name == "sessions":
            factory = _factory()
            registry = factory.registry
            sessions = []
            for binding in registry.card_session_binding_store.list_all():
                turns_for_session = registry.turn_record_store.list_by_session(binding.session_id)
                sessions.append({
                    "session_id": binding.session_id,
                    "logical_card_id": binding.logical_card_id,
                    "card_version": binding.card_version,
                    "selected_greeting_id": binding.selected_greeting_id,
                    "status": binding.status,
                    "turn_count": len(turns_for_session),
                })
            return _console_result(command, f"{len(sessions)} sessions.", {"sessions": sessions})

        if name == "new":
            if not args:
                return _console_result(command, "Usage: new <card_id> [greeting_id]", ok=False)
            card_id = args[0]
            greeting_id = args[1] if len(args) > 1 else "g0"
            factory = _factory()
            registry = factory.registry
            card = registry.card_definition_store.get_latest(card_id)
            if not card:
                return _console_result(command, f"Card not found: {card_id}", ok=False)
            try:
                from ..contracts.card_session_bootstrap_request import CardSessionBootstrapRequest
                from ..runtime.card_session_bootstrap_pipeline import CardSessionBootstrapPipeline

                new_session_id = f"sess-{uuid.uuid4().hex[:12]}"
                request_id = f"req-{uuid.uuid4().hex[:12]}"
                bootstrap_request = CardSessionBootstrapRequest(
                    request_id=request_id,
                    workflow_run_id=f"wr-{request_id}",
                    trace_id=f"tr-{request_id}",
                    session_id=new_session_id,
                    logical_card_id=card.logical_card_id,
                    card_version=card.card_version,
                    greeting_id=greeting_id,
                    expected_source_hash=card.source_hash,
                )
                pipeline = CardSessionBootstrapPipeline(
                    definition_store=registry.card_definition_store,
                    binding_store=registry.card_session_binding_store,
                    opening_store=registry.opening_record_store,
                    worldbook_store=registry.worldbook_binding_store,
                    receipt_store=registry.bootstrap_receipt_store,
                )
                receipt, failure, diagnostics = pipeline.bootstrap(bootstrap_request)
                if failure:
                    return _console_result(command, failure.failure_message, ok=False)
                registry.card_state_store.initialize(card.logical_card_id, new_session_id)
                data = {
                    "session_id": receipt.session_id if receipt else new_session_id,
                    "card_id": card.logical_card_id,
                    "greeting_id": greeting_id,
                    "diagnostics": diagnostics.to_dict(),
                }
                return _console_result(command, f"Created session {data['session_id']}.", data)
            except Exception as e:
                return _console_result(command, f"Create session failed: {str(e)[:200]}", ok=False)

        if name not in {
            "context", "session", "history", "turns", "transcript",
            "state", "send", "continue",
        }:
            return _console_result(
                command,
                f"Unknown safe command: {name}. Type help.",
                {"allowed_commands": allowed},
                ok=False,
            )

        if not session_id:
            return _console_result(command, "session_id is required for this command.", ok=False)

        factory = _factory()
        registry = factory.registry
        binding = registry.card_session_binding_store.load(session_id)
        if not binding:
            return _console_result(command, f"Session not found: {session_id}", ok=False)

        turns = registry.turn_record_store.list_by_session(session_id)
        session_data = {
            "session_id": binding.session_id,
            "logical_card_id": binding.logical_card_id,
            "card_version": binding.card_version,
            "source_hash": binding.source_hash,
            "selected_greeting_id": binding.selected_greeting_id,
            "status": binding.status,
            "turn_count": len(turns),
        }

        if name == "session":
            return _console_result(command, f"Session {session_id}: {len(turns)} turns.", {"session": session_data})

        if name == "transcript":
            card = registry.card_definition_store.load(
                binding.logical_card_id,
                binding.card_version,
            )
            if card is None:
                card = registry.card_definition_store.get_latest(binding.logical_card_id)
            opening = registry.opening_record_store.get_by_session(session_id)
            state = registry.card_state_store.load(binding.logical_card_id, session_id)
            profile = dict(getattr(card, "profile", {}) or {}) if card else {}
            lines = [
                f"Session: {session_id}",
                f"Card: {binding.logical_card_id} v{binding.card_version}",
                "",
                "=== Character Profile ===",
            ]
            if card:
                lines.append(f"Name: {profile.get('name') or card.display_name or card.name}")
            for key in ("description", "personality", "scenario", "mes_example", "creator_notes"):
                value = str(profile.get(key, "") or "").strip()
                if value:
                    lines.extend([f"{key}:", value, ""])
            lines.extend([
                "=== Opening ===",
                opening.safe_display_content if opening else "(none)",
                "",
                "=== Turns ===",
            ])
            if turns:
                for turn in turns:
                    lines.extend([
                        f"[Turn {turn.turn_index}]",
                        "Player:",
                        turn.player_input or "",
                        "Writer:",
                        turn.writer_output or "",
                        "",
                    ])
            else:
                lines.append("(none)")
            lines.extend([
                "=== CardState ===",
                json.dumps(state.to_dict() if state else None, ensure_ascii=False, indent=2, default=str),
            ])
            text = "\n".join(lines).strip()
            return _console_result(
                command,
                text,
                {
                    "text": text,
                    "session": session_data,
                    "profile": profile,
                    "opening": opening.safe_display_content if opening else "",
                    "turns": [_turn_to_console_dict(turn) for turn in turns],
                    "card_state": state.to_dict() if state else None,
                },
            )

        if name in {"history", "turns"}:
            try:
                limit = max(1, min(20, int(args[0]))) if args else 5
            except ValueError:
                limit = 5
            selected = turns[-limit:]
            return _console_result(
                command,
                f"Latest {len(selected)} turns.",
                {"turns": [_turn_to_console_dict(turn) for turn in selected]},
            )

        if name == "state":
            state = registry.card_state_store.load(binding.logical_card_id, session_id)
            return _console_result(
                command,
                "Current CardState.",
                {"card_state": state.to_dict() if state else None},
            )

        if name == "send":
            player_input = " ".join(args).strip()
            if not player_input:
                return _console_result(command, "Usage: send <player text>", ok=False)
            from .execution_dispatcher import ExecutionDispatcher

            result = ExecutionDispatcher().execute_turn(
                session_id,
                player_input,
                mode="python",
            )
            return _console_result(
                command,
                "Turn executed." if result.get("success") else "Turn failed.",
                {"result": result},
                ok=bool(result.get("success")),
            )

        if name == "continue":
            from .execution_dispatcher import ExecutionDispatcher

            result = ExecutionDispatcher().execute_continue(session_id, mode="python")
            return _console_result(
                command,
                "Continuation executed." if result.get("success") else "Continuation failed.",
                {"result": result},
                ok=bool(result.get("success")),
            )

        state = registry.card_state_store.load(binding.logical_card_id, session_id)
        latest_turns = turns[-5:]
        return _console_result(
            command,
            "AI-readable runtime context.",
            {
                "session": session_data,
                "latest_turns": [_turn_to_console_dict(turn) for turn in latest_turns],
                "card_state": state.to_dict() if state else None,
                "available_commands": allowed,
                "notes": [
                    "This console is project-scoped and does not execute shell commands.",
                    "Use this JSON as diagnostic context for human or AI review.",
                ],
            },
        )

    @server.PromptServer.instance.routes.get("/awp/api/v1/sessions")
    async def list_sessions(request):
        """List all sessions with card name, turn count, last activity."""
        factory = _factory()
        registry = factory.registry
        bindings = registry.card_session_binding_store.list_all()

        result = []
        for b in bindings:
            turns = registry.turn_record_store.list_by_session(b.session_id)
            turn_count = len(turns)
            last_turn = turns[-1] if turns else None

            card_name = b.logical_card_id
            try:
                card = registry.card_definition_store.get_latest(b.logical_card_id)
                if card:
                    card_name = card.display_name or card.name or b.logical_card_id
            except Exception:
                pass

            result.append({
                "session_id": b.session_id,
                "card_id": b.logical_card_id,
                "card_name": card_name,
                "greeting_id": b.selected_greeting_id,
                "turn_count": turn_count,
                "last_turn_time": last_turn.accepted_at if last_turn else b.created_at,
                "created_at": b.created_at,
                "status": b.status,
            })

        return _json(result)

    @server.PromptServer.instance.routes.get("/awp/api/v1/sessions/{session_id}")
    async def get_session(request):
        """Get a single session's details."""
        session_id = request.match_info["session_id"]
        factory = _factory()
        registry = factory.registry

        binding = registry.card_session_binding_store.load(session_id)
        if not binding:
            return _json({"error": "Session not found"}, 404)

        turns = registry.turn_record_store.list_by_session(session_id)
        opening = None
        try:
            opening = registry.opening_record_store.get_by_session(session_id)
        except Exception:
            pass

        card_name = binding.logical_card_id
        try:
            card = registry.card_definition_store.get_latest(binding.logical_card_id)
            if card:
                card_name = card.display_name or card.name or binding.logical_card_id
        except Exception:
            pass

        return _json({
            "session_id": binding.session_id,
            "card_id": binding.logical_card_id,
            "card_name": card_name,
            "greeting_id": binding.selected_greeting_id,
            "status": binding.status,
            "created_at": binding.created_at,
            "turn_count": len(turns),
            "opening_content": opening.safe_display_content if opening else "",
        })

    @server.PromptServer.instance.routes.get("/awp/api/v1/sessions/{session_id}/turns")
    async def list_turns(request):
        """List all turns for a session."""
        session_id = request.match_info["session_id"]
        factory = _factory()
        registry = factory.registry

        binding = registry.card_session_binding_store.load(session_id)
        if not binding:
            return _json({"error": "Session not found"}, 404)

        turns = registry.turn_record_store.list_by_session(session_id)

        result = []
        for t in turns:
            result.append({
                "turn_id": t.turn_id,
                "turn_index": t.turn_index,
                "mode": t.mode.value,
                "player_input": t.player_input,
                "writer_output": t.writer_output,
                "base_card_state_revision": t.base_card_state_revision,
                "result_card_state_revision": t.result_card_state_revision,
                "accepted_at": t.accepted_at,
                "created_at": t.created_at,
                "trace_id": t.trace_id,
            })

        return _json(result)

    @server.PromptServer.instance.routes.get("/awp/api/v1/sessions/{session_id}/turns/{turn_id}/pipeline")
    async def get_turn_pipeline(request):
        """Get the full pipeline trace for a turn — all steps with detailed content."""
        session_id = request.match_info["session_id"]
        turn_id = request.match_info["turn_id"]
        factory = _factory()
        registry = factory.registry

        binding = registry.card_session_binding_store.load(session_id)
        if not binding:
            return _json({"error": "Session not found"}, 404)

        # Load trace
        trace = registry.trace_store.get_by_turn(turn_id)
        if not trace:
            return _json({"error": "Pipeline trace not found"}, 404)
        if trace.session_id != session_id:
            return _json({"error": "Pipeline trace not found"}, 404)

        # Load turn record for writer output
        turn_record = None
        for t in registry.turn_record_store.list_by_session(session_id):
            if t.turn_id == turn_id:
                turn_record = t
                break
        if turn_record and turn_record.session_id != session_id:
            return _json({"error": "Turn not found"}, 404)

        # Load memory commits for this turn
        active_memories = []
        rag_memories = []
        try:
            conn = registry.db.connect()
            rows = conn.execute(
                "SELECT memory_json FROM active_memory_records "
                "WHERE session_id=? AND source_turn_ids_json LIKE ? "
                "ORDER BY importance DESC, updated_at DESC",
                (session_id, f'%"{turn_id}"%'),
            ).fetchall()
            for row in rows:
                import json as _json_mod
                mem = _json_mod.loads(row["memory_json"])
                active_memories.append({
                    "memory_id": mem.get("memory_id", ""),
                    "kind": mem.get("kind", ""),
                    "summary": mem.get("summary", ""),
                    "importance": mem.get("importance", 0),
                    "retention_reason": mem.get("retention_reason", ""),
                })
            rows = conn.execute(
                "SELECT memory_json FROM rag_memory_records "
                "WHERE session_id=? AND source_turn_ids_json LIKE ? "
                "ORDER BY importance DESC, updated_at DESC",
                (session_id, f'%"{turn_id}"%'),
            ).fetchall()
            for row in rows:
                mem = _json_mod.loads(row["memory_json"])
                rag_memories.append({
                    "memory_id": mem.get("memory_id", ""),
                    "content": mem.get("content", ""),
                    "scope": mem.get("scope", ""),
                    "importance": mem.get("importance", 0),
                })
        except Exception:
            pass

        # Build pipeline steps from trace events
        trace_dict = trace.to_dict()
        steps = []
        for evt in trace_dict.get("events", []):
            step = {
                "event_type": evt.get("event_type", ""),
                "actor": evt.get("actor", ""),
                "duration_ms": evt.get("duration_ms", 0),
                "success": evt.get("success", True),
                "error": evt.get("error"),
                "details": _redact_pipeline_details(evt.get("details", {})),
            }
            steps.append(step)

        result = {
            "trace_id": trace.trace_id,
            "turn_id": trace.turn_id,
            "session_id": trace.session_id,
            "total_duration_ms": trace_dict.get("total_duration_ms", 0),
            "success": trace_dict.get("success", True),
            "steps": steps,
            "writer_output": turn_record.writer_output if turn_record else "",
            "player_input": turn_record.player_input if turn_record else "",
            "turn_index": turn_record.turn_index if turn_record else 0,
            "active_memories": active_memories,
            "rag_memories": rag_memories,
        }

        return _json(result)

    @server.PromptServer.instance.routes.get("/awp/api/v1/sessions/{session_id}/opening")
    async def get_opening(request):
        """Get the opening/greeting content for a session."""
        session_id = request.match_info["session_id"]
        factory = _factory()
        registry = factory.registry

        try:
            opening = registry.opening_record_store.get_by_session(session_id)
        except Exception:
            return _json({"error": "Opening not found"}, 404)

        if not opening:
            return _json({"error": "Opening not found"}, 404)

        return _json({
            "opening_record_id": opening.opening_record_id,
            "greeting_id": opening.greeting_id,
            "content": opening.safe_display_content,
            "created_at": opening.created_at,
        })

    @server.PromptServer.instance.routes.get("/awp/api/v1/cards")
    async def list_cards(request):
        """List all imported cards with stats."""
        factory = _factory()
        registry = factory.registry

        try:
            cards = registry.card_definition_store.list_all()
        except Exception:
            cards = []

        result = []
        seen = set()
        for c in cards:
            if c.logical_card_id in seen:
                continue
            seen.add(c.logical_card_id)
            result.append({
                "card_id": c.logical_card_id,
                "version": c.card_version,
                "name": c.display_name or c.name or c.logical_card_id,
                "status": c.status,
                "greeting_count": len(c.greetings) if c.greetings else 0,
                "worldbook_count": len(c.worldbook_catalog) if c.worldbook_catalog else 0,
                "created_at": c.created_at,
            })

        return _json(result)

    @server.PromptServer.instance.routes.post("/awp/api/v1/sessions/{session_id}/continue")
    async def continue_session(request):
        """Continue a session — triggers AWPV2ContinueTurn."""
        session_id = request.match_info["session_id"]
        mode = request.query.get("mode", "")
        workflow = request.query.get("workflow", "")
        factory = _factory()
        registry = factory.registry

        binding = registry.card_session_binding_store.load(session_id)
        if not binding:
            return _json({"error": "Session not found"}, 404)

        try:
            from .execution_dispatcher import ExecutionDispatcher

            result = await _run_blocking(
                ExecutionDispatcher().execute_continue,
                session_id,
                mode=mode,
                workflow=workflow,
            )
            return _json(result)
        except Exception as e:
            return _json({"error": f"Continue failed: {str(e)[:200]}"}, 500)

    # ── SPA static file serving ──────────────────────────────────────────

    @server.PromptServer.instance.routes.post("/awp/api/v1/sessions/{session_id}/turn")
    async def post_turn(request):
        session_id = request.match_info["session_id"]
        body = await request.json()
        player_input = body.get("player_input", "")
        mode = request.query.get("mode", "")
        workflow = request.query.get("workflow", "")
        if not player_input:
            return _json({"error": "player_input required"}, 400)

        try:
            from .execution_dispatcher import ExecutionDispatcher

            result = await _run_blocking(
                ExecutionDispatcher().execute_turn,
                session_id,
                player_input,
                mode=mode,
                workflow=workflow,
            )
            return _json(result)
        except Exception as e:
            return _json({"error": f"Turn failed: {str(e)[:200]}"}, 500)

    @server.PromptServer.instance.routes.post("/awp/api/v1/sessions/{session_id}/turn/stream")
    async def post_turn_stream(request):
        session_id = request.match_info["session_id"]
        body = await request.json()
        player_input = str(body.get("player_input", "") or "").strip()
        if not player_input:
            return _json({"error": "player_input required"}, 400)
        mode = request.query.get("mode", "")
        workflow = request.query.get("workflow", "")

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

        def _enqueue(event_type: str, data: dict[str, Any]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, (event_type, data))

        def _on_started(turn_id: str, steps: list[str]) -> None:
            _enqueue("started", {"turn_id": turn_id, "steps": steps})

        def _on_step(name: str, payload: dict[str, Any]) -> None:
            _enqueue("step", {
                "step": name,
                "payload": payload,
                "duration_ms": payload.get("duration_ms", 0),
            })

        def _on_writer_text(turn_id: str, text: str) -> None:
            _enqueue("writer_text", {"turn_id": turn_id, "writer_output": text})

        def _on_done(result: dict[str, Any]) -> None:
            _enqueue("done", result)

        def _run_streaming_turn() -> None:
            try:
                from .execution_dispatcher import ExecutionDispatcher

                ExecutionDispatcher().execute_turn_streaming(
                    session_id,
                    player_input,
                    mode=mode,
                    workflow=workflow,
                    on_started=_on_started,
                    on_step=_on_step,
                    on_writer_text=_on_writer_text,
                    on_done=_on_done,
                )
            except Exception as e:
                _enqueue("done", {
                    "success": False,
                    "turn_id": "",
                    "turn_index": 0,
                    "error": f"Turn failed: {str(e)[:200]}",
                    "failure_code": "STREAM_EXECUTION_ERROR",
                })

        loop.run_in_executor(None, functools.partial(_run_streaming_turn))

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
        await response.prepare(request)
        await response.drain()

        while True:
            try:
                event_type, data = await asyncio.wait_for(queue.get(), timeout=180)
            except asyncio.TimeoutError:
                event_type = "done"
                data = {
                    "success": False,
                    "turn_id": "",
                    "turn_index": 0,
                    "error": "timeout",
                    "failure_code": "TIMEOUT",
                }

            chunk = (
                f"event: {event_type}\n"
                f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
            ).encode("utf-8")
            try:
                await response.write(chunk)
            except (ConnectionResetError, RuntimeError, asyncio.CancelledError):
                break
            if event_type == "done":
                break

        try:
            await response.write_eof()
        except (ConnectionResetError, RuntimeError, asyncio.CancelledError):
            pass
        return response

    @server.PromptServer.instance.routes.post("/awp/api/v1/sessions/{session_id}/first-turn")
    async def post_first_turn(request):
        session_id = request.match_info["session_id"]
        body = await request.json()
        player_input = body.get("player_input", "")
        mode = request.query.get("mode", "")
        workflow = request.query.get("workflow", "")

        try:
            from .execution_dispatcher import ExecutionDispatcher

            result = await _run_blocking(
                ExecutionDispatcher().execute_first_turn,
                session_id,
                player_input,
                mode=mode,
                workflow=workflow,
            )
            return _json(result)
        except Exception as e:
            return _json({"error": f"First turn failed: {str(e)[:200]}"}, 500)

    @server.PromptServer.instance.routes.post("/awp/api/v1/cards/import")
    async def import_card(request):
        body = await request.json()
        source_path = body.get("source_path", "")
        if not source_path:
            return _json({"error": "source_path required"}, 400)

        try:
            from ..nodes.persistent_bootstrap_node import AWPV2PersistentBootstrap

            session_id = body.get("session_id") or f"imp-{uuid.uuid4().hex[:12]}"
            binding, _opening, _worldbook, _receipt, diagnostics = (
                AWPV2PersistentBootstrap().execute(
                    source_path=source_path,
                    session_id=session_id,
                    greeting_id=body.get("greeting_id", "g0"),
                    request_id=body.get("request_id", f"imp-{uuid.uuid4().hex[:12]}"),
                )
            )
            return _json({
                "success": diagnostics.get("commit_status") == "success",
                "session_id": binding.get("session_id", ""),
                "card_id": binding.get("logical_card_id", ""),
                "diagnostics": diagnostics,
            })
        except Exception as e:
            return _json({"error": f"Import failed: {str(e)[:200]}"}, 500)

    @server.PromptServer.instance.routes.get("/awp/api/v1/cards/{card_id}/greetings")
    async def list_greetings(request):
        card_id = request.match_info["card_id"]
        factory = _factory()
        card = factory.registry.card_definition_store.get_latest(card_id)
        if not card:
            return _json({"error": "Card not found"}, 404)

        greetings = []
        for greeting in card.greetings or []:
            content = (
                greeting.get("safe_display_content", "")
                or greeting.get("content", "")
                or ""
            )
            greetings.append({
                "greeting_id": greeting.get("greeting_id", ""),
                "label": greeting.get("label", ""),
                "is_default": bool(greeting.get("is_default", False)),
                "preview": content[:120],
            })
        return _json(greetings)

    @server.PromptServer.instance.routes.post("/awp/api/v1/sessions")
    async def create_session(request):
        body = await request.json()
        card_id = body.get("card_id", "")
        greeting_id = body.get("greeting_id", "")
        if not card_id:
            return _json({"error": "card_id required"}, 400)
        if not greeting_id:
            return _json({"error": "greeting_id required"}, 400)

        factory = _factory()
        registry = factory.registry
        card = registry.card_definition_store.get_latest(card_id)
        if not card:
            return _json({"error": "Card not found"}, 404)

        try:
            from ..contracts.card_session_bootstrap_request import (
                CardSessionBootstrapRequest,
            )
            from ..runtime.card_session_bootstrap_pipeline import (
                CardSessionBootstrapPipeline,
            )

            session_id = body.get("session_id") or f"sess-{uuid.uuid4().hex[:12]}"
            request_id = body.get("request_id") or f"req-{uuid.uuid4().hex[:12]}"
            bootstrap_request = CardSessionBootstrapRequest(
                request_id=request_id,
                workflow_run_id=f"wr-{request_id}",
                trace_id=f"tr-{request_id}",
                session_id=session_id,
                logical_card_id=card.logical_card_id,
                card_version=card.card_version,
                greeting_id=greeting_id,
                expected_source_hash=card.source_hash,
            )
            pipeline = CardSessionBootstrapPipeline(
                definition_store=registry.card_definition_store,
                binding_store=registry.card_session_binding_store,
                opening_store=registry.opening_record_store,
                worldbook_store=registry.worldbook_binding_store,
                receipt_store=registry.bootstrap_receipt_store,
            )
            receipt, failure, diagnostics = pipeline.bootstrap(bootstrap_request)
            if failure:
                return _json({"error": failure.failure_message}, 400)

            registry.card_state_store.initialize(card.logical_card_id, session_id)
            return _json({
                "session_id": receipt.session_id if receipt else session_id,
                "card_id": card.logical_card_id,
                "greeting_id": greeting_id,
                "diagnostics": diagnostics.to_dict(),
            })
        except Exception as e:
            return _json({"error": f"Create session failed: {str(e)[:200]}"}, 500)

    @server.PromptServer.instance.routes.delete("/awp/api/v1/cards/{card_id}")
    async def delete_card(request):
        card_id = request.match_info["card_id"]
        try:
            from .session_deletion_service import SessionDeletionService

            factory = _factory()
            SessionDeletionService(factory.registry).delete_card(card_id)
            return _json({"success": True})
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.delete("/awp/api/v1/sessions/{session_id}")
    async def delete_session(request):
        session_id = request.match_info["session_id"]
        try:
            from .session_deletion_service import SessionDeletionService

            factory = _factory()
            SessionDeletionService(factory.registry).delete_session(session_id)
            return _json({"success": True})
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.get("/awp/api/v1/workflows")
    async def list_workflows(request):
        from ..testing.api_workflow_loader import APIWorkflowLoader

        loader = APIWorkflowLoader()
        result = []
        for name in loader.list_workflows():
            workflow = loader.load(name)
            class_types = sorted({
                node_def.get("class_type", "")
                for node_def in workflow.values()
                if isinstance(node_def, dict)
            })
            result.append({
                "name": name,
                "node_count": len(workflow),
                "class_types": class_types,
            })
        return _json(result)

    @server.PromptServer.instance.routes.post("/awp/api/v1/console/command")
    async def post_console_command(request):
        body = await request.json()
        command = body.get("command", "")
        session_id = body.get("session_id", "")
        try:
            result = await _run_blocking(_run_console_command, command, session_id)
            return _json(result)
        except Exception as e:
            return _json(_console_result(str(command), str(e)[:300], ok=False), 500)

    @server.PromptServer.instance.routes.get("/awp/api/v1/presets/writer")
    async def list_writer_presets(request):
        from ..presets.writer_preset_loader import WriterPresetLoader

        return _json(WriterPresetLoader().list_presets())

    @server.PromptServer.instance.routes.get("/awp/api/v1/presets/writer/{name}")
    async def get_writer_preset(request):
        from ..presets.writer_preset_loader import WriterPresetLoader

        name = request.match_info["name"]
        loader = WriterPresetLoader()
        content = loader.load(name)
        path = loader.get_preset_path(name)
        if not content and not path:
            return _json({"error": "Preset not found"}, 404)
        return _json({"name": name, "content": content, "path": path})

    # ── Novel Mode API ────────────────────────────────────────────────────────

    @server.PromptServer.instance.routes.post("/awp/api/v1/novels")
    async def create_novel_project(request):
        """Create a novel project."""
        from ..contracts.novel_project import NovelProject
        body = await request.json()
        project_id = body.get("project_id", f"novel-{uuid.uuid4().hex[:8]}")
        project = NovelProject(
            project_id=project_id,
            title=body.get("title", ""),
            genre=body.get("genre", ""),
            target_platform=body.get("target_platform", ""),
            target_reader=body.get("target_reader", ""),
            core_emotion=body.get("core_emotion", ""),
            one_sentence_pitch=body.get("one_sentence_pitch", ""),
            status="planning",
        )
        try:
            factory = _factory()
            factory.registry.novel_project_store.create(project)
            return _json(project.to_dict())
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.get("/awp/api/v1/novels")
    async def list_novel_projects(request):
        """List all novel projects."""
        try:
            factory = _factory()
            projects = factory.registry.novel_project_store.list_all()
            return _json([p.to_dict() for p in projects])
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.get("/awp/api/v1/novels/{project_id}")
    async def get_novel_project(request):
        """Get novel project details."""
        project_id = request.match_info["project_id"]
        try:
            factory = _factory()
            project = factory.registry.novel_project_store.load(project_id)
            if not project:
                return _json({"error": "Project not found"}, 404)
            return _json(project.to_dict())
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.delete("/awp/api/v1/novels/{project_id}")
    async def delete_novel_project(request):
        """Delete a novel project."""
        project_id = request.match_info["project_id"]
        try:
            factory = _factory()
            factory.registry.novel_project_store.delete(project_id)
            return _json({"success": True})
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.get("/awp/api/v1/novels/{project_id}/chapters")
    async def list_novel_chapters(request):
        """List chapter plans for a novel project."""
        project_id = request.match_info["project_id"]
        try:
            factory = _factory()
            plans = factory.registry.novel_chapter_plan_store.list_by_project(project_id)
            return _json([p.to_dict() for p in plans])
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.post("/awp/api/v1/novels/{project_id}/chapters/plan")
    async def plan_novel_chapter(request):
        """Plan a chapter using Architect."""
        project_id = request.match_info["project_id"]
        body = await request.json()
        chapter_index = body.get("chapter_index", 1)
        task_description = body.get("task_description", "")
        if chapter_index < 1:
            return _json({"error": "chapter_index must be >= 1"}, 400)
        try:
            from .novel_engine import NovelEngine
            factory = _factory()
            engine = NovelEngine(factory.registry)
            plan = await _run_blocking(
                engine.plan_chapter,
                project_id=project_id,
                chapter_index=chapter_index,
                task_description=task_description,
            )
            return _json(plan.to_dict())
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    def _parse_chapter_idx(idx_str: str) -> int | None:
        """Parse chapter index from URL path, return None if invalid."""
        try:
            idx = int(idx_str)
            return idx if idx >= 1 else None
        except (ValueError, TypeError):
            return None

    @server.PromptServer.instance.routes.get("/awp/api/v1/novels/{project_id}/chapters/{idx}/plan")
    async def get_novel_chapter_plan(request):
        """Get chapter plan by index."""
        project_id = request.match_info["project_id"]
        idx = _parse_chapter_idx(request.match_info["idx"])
        if idx is None:
            return _json({"error": "Invalid chapter index"}, 400)
        try:
            factory = _factory()
            plan = factory.registry.novel_chapter_plan_store.load_by_index(project_id, idx)
            if not plan:
                return _json({"error": "Plan not found"}, 404)
            return _json(plan.to_dict())
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.post("/awp/api/v1/novels/{project_id}/chapters/{idx}/write")
    async def write_novel_chapter(request):
        """Write a chapter using Writer."""
        project_id = request.match_info["project_id"]
        idx = _parse_chapter_idx(request.match_info["idx"])
        if idx is None:
            return _json({"error": "Invalid chapter index"}, 400)
        try:
            from .novel_engine import NovelEngine
            factory = _factory()
            engine = NovelEngine(factory.registry)
            draft = await _run_blocking(
                engine.write_chapter,
                project_id=project_id, chapter_index=idx,
            )
            return _json(draft.to_dict())
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.get("/awp/api/v1/novels/{project_id}/chapters/{idx}/drafts")
    async def list_novel_drafts(request):
        """List drafts for a chapter."""
        project_id = request.match_info["project_id"]
        idx = _parse_chapter_idx(request.match_info["idx"])
        if idx is None:
            return _json({"error": "Invalid chapter index"}, 400)
        try:
            factory = _factory()
            plan = factory.registry.novel_chapter_plan_store.load_by_index(project_id, idx)
            if not plan:
                return _json({"error": "Chapter not found"}, 404)
            drafts = factory.registry.novel_chapter_draft_store.list_by_chapter(plan.chapter_id)
            return _json([d.to_dict() for d in drafts])
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.post("/awp/api/v1/novels/{project_id}/chapters/{idx}/revise")
    async def revise_novel_chapter(request):
        """Revise a chapter."""
        project_id = request.match_info["project_id"]
        idx = _parse_chapter_idx(request.match_info["idx"])
        if idx is None:
            return _json({"error": "Invalid chapter index"}, 400)
        body = await request.json()
        feedback = body.get("feedback", "")
        try:
            from .novel_engine import NovelEngine
            factory = _factory()
            engine = NovelEngine(factory.registry)
            draft = await _run_blocking(
                engine.revise_chapter,
                project_id=project_id, chapter_index=idx, feedback=feedback,
            )
            return _json(draft.to_dict())
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.post("/awp/api/v1/novels/{project_id}/batch-write")
    async def batch_write_novel(request):
        """Batch write multiple chapters."""
        project_id = request.match_info["project_id"]
        body = await request.json()
        chapter_start = body.get("chapter_start", 1)
        chapter_end = body.get("chapter_end", 3)
        if chapter_start < 1 or chapter_end < chapter_start:
            return _json({"error": "Invalid chapter range"}, 400)
        try:
            from .novel_engine import NovelEngine
            factory = _factory()
            engine = NovelEngine(factory.registry)
            drafts = await _run_blocking(
                engine.batch_write,
                project_id=project_id,
                chapter_start=chapter_start,
                chapter_end=chapter_end,
            )
            return _json({
                "drafts": [d.to_dict() for d in drafts],
                "count": len(drafts),
            })
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.get("/awp/api/v1/novels/{project_id}/ledger")
    async def list_novel_ledger(request):
        """List ledger items for a novel project."""
        project_id = request.match_info["project_id"]
        section = request.query.get("section", "")
        try:
            factory = _factory()
            items = factory.registry.novel_ledger_store.list_by_project(project_id, section)
            return _json([i.to_dict() for i in items])
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.get("/awp/api/v1/novels/{project_id}/characters")
    async def list_novel_characters(request):
        """List characters for a novel project."""
        project_id = request.match_info["project_id"]
        try:
            factory = _factory()
            chars = factory.registry.novel_character_store.list_by_project(project_id)
            return _json([c.to_dict() for c in chars])
        except Exception as e:
            return _json({"error": str(e)[:200]}, 500)

    @server.PromptServer.instance.routes.post("/awp/api/v1/novels/plan")
    async def plan_novel_from_concept(request):
        """Generate a full novel plan from a brief concept.

        Body: {
            "concept": "一句话思路",
            "title": "可选书名",
            "genre": "可选题材",
            "target_platform": "可选平台",
            "additional_requirements": "可选额外要求"
        }
        Returns: NovelPlan JSON (core_outline, world_setting, characters, volumes, chapters)
        """
        body = await request.json()
        concept = body.get("concept", "")
        if not concept:
            return _json({"error": "concept is required"}, 400)

        try:
            factory = _factory()
            from .novel_planner_adapter import NovelPlannerAdapter
            planner = NovelPlannerAdapter(factory.registry)
            plan = planner.plan_novel(
                concept=concept,
                title=body.get("title", ""),
                genre=body.get("genre", ""),
                target_platform=body.get("target_platform", ""),
                additional_requirements=body.get("additional_requirements", ""),
            )
            return _json(plan.to_dict())
        except Exception as e:
            import traceback
            return _json({"error": str(e)[:500], "trace": traceback.format_exc()[-500:]}, 500)

    @server.PromptServer.instance.routes.get("/awp")
    async def serve_spa_index(request):
        """Serve the SPA index.html."""
        index_path = _MANAGEMENT_DIR / "index.html"
        if not index_path.exists():
            return web.Response(
                text="Management panel not built yet. Run: cd web && npm run build",
                content_type="text/plain",
            )
        with open(str(index_path), "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="text/html")

    @server.PromptServer.instance.routes.get("/awp/{tail:.*}")
    async def serve_spa_static(request):
        """Serve static files or fall back to index.html for SPA routing."""
        tail = request.match_info.get("tail", "")
        file_path = _resolve_static_asset_path(tail)

        if file_path and file_path.exists() and file_path.is_file():
            content_type = _mime_type(file_path.suffix)
            with open(str(file_path), "rb") as f:
                return web.Response(body=f.read(), content_type=content_type)

        # SPA fallback
        index_path = _MANAGEMENT_DIR / "index.html"
        if index_path.exists():
            with open(str(index_path), "r", encoding="utf-8") as f:
                return web.Response(text=f.read(), content_type="text/html")

        return web.Response(text="Not found", status=404)

except ImportError:
    pass  # Running outside ComfyUI — API routes are not registered
