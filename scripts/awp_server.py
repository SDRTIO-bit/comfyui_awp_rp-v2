"""AWP RP Runtime — 独立后端服务器

不依赖 ComfyUI，直接用 aiohttp 提供 API + 前端静态文件。

用法:
  python scripts/awp_server.py
  python scripts/awp_server.py --port 8189
  python scripts/awp_server.py --db-path ./my_data.db

前端访问: http://localhost:8188/awp/
API 前缀: http://localhost:8188/awp/api/v1/
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

# ── 路径设置 ──────────────────────────────────────────────────────────────
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, str(Path(_PROJECT_ROOT).parent))

from aiohttp import web

from awp_rp_runtime_v2.runtime.runtime_store_factory import RuntimeStoreFactory
from awp_rp_runtime_v2.runtime.management_api import (
    _resolve_static_asset_path,
    _mime_type,
    _MANAGEMENT_DIR,
)

# 复制 management_api 中在 try 块内定义的函数
import shlex as _shlex


def _console_result(command: str, output: str, data: Any = None, ok: bool = True) -> dict[str, Any]:
    return {"ok": ok, "command": command, "output": output, "data": data if data is not None else {}}


def _turn_to_console_dict(turn: Any) -> dict[str, Any]:
    return {
        "turn_id": turn.turn_id, "turn_index": turn.turn_index,
        "mode": turn.mode.value, "player_input": turn.player_input,
        "writer_output": turn.writer_output,
        "base_card_state_revision": turn.base_card_state_revision,
        "result_card_state_revision": turn.result_card_state_revision,
        "accepted_at": turn.accepted_at, "created_at": turn.created_at,
        "trace_id": turn.trace_id,
    }


def _run_console_command(command: str, session_id: str = "") -> dict[str, Any]:
    command = str(command or "").strip()[:500]
    session_id = str(session_id or "").strip()
    if not command:
        return _console_result(command, "No command.", ok=False)
    try:
        parts = _shlex.split(command)
    except ValueError as e:
        return _console_result(command, f"Command parse error: {e}", ok=False)
    name = parts[0].lower()
    args = parts[1:]
    allowed = ["help", "context", "cards", "sessions", "new", "session", "history",
               "turns", "transcript", "state", "send", "continue", "workflows", "presets", "echo", "clear"]
    if name == "help":
        return _console_result(command, "Available commands: " + ", ".join(allowed), {
            "commands": {
                "help": "Show safe console commands.", "context": "Return AI-readable session context.",
                "cards": "List imported cards.", "sessions": "List sessions.",
                "new <card_id> [greeting_id]": "Create a new session from a card.",
                "session": "Show current session metadata.", "history [n]": "Alias for turns [n].",
                "turns [n]": "Show latest n turns, default 5.",
                "transcript": "Print profile, opening, all turns, and state as terminal text.",
                "state": "Show current CardState.",
                "send <text>": "Send a player message to the current session using Python direct mode.",
                "continue": "Continue the current session using Python direct mode.",
                "workflows": "List API workflows.", "presets": "List writer presets.",
                "echo <text>": "Echo text for console checks.", "clear": "Cleared locally by the frontend.",
            }, "shell": False})
    if name == "clear":
        return _console_result(command, "Console cleared locally.", {"local_only": True})
    if name == "echo":
        return _console_result(command, " ".join(args), {"text": " ".join(args)})
    if name == "workflows":
        from awp_rp_runtime_v2.testing.api_workflow_loader import APIWorkflowLoader
        loader = APIWorkflowLoader()
        workflows = []
        for wn in loader.list_workflows():
            wf = loader.load(wn)
            ct = sorted({nd.get("class_type", "") for nd in wf.values() if isinstance(nd, dict)})
            workflows.append({"name": wn, "node_count": len(wf), "class_types": ct})
        return _console_result(command, f"{len(workflows)} workflows.", {"workflows": workflows})
    if name == "presets":
        from awp_rp_runtime_v2.presets.writer_preset_loader import WriterPresetLoader
        return _console_result(command, f"{len(WriterPresetLoader().list_presets())} writer presets.", {"presets": WriterPresetLoader().list_presets()})
    if name == "cards":
        factory = _factory()
        cards = []
        for card in factory.registry.card_definition_store.list_all():
            cards.append({"card_id": card.logical_card_id, "version": card.card_version,
                          "name": card.display_name or card.name or card.logical_card_id,
                          "status": card.status, "greeting_count": len(card.greetings or []),
                          "worldbook_count": len(card.worldbook_catalog or []), "created_at": card.created_at})
        return _console_result(command, f"{len(cards)} cards.", {"cards": cards})
    if name == "sessions":
        factory = _factory()
        registry = factory.registry
        sessions = []
        for binding in registry.card_session_binding_store.list_all():
            turns = registry.turn_record_store.list_by_session(binding.session_id)
            sessions.append({"session_id": binding.session_id, "logical_card_id": binding.logical_card_id,
                             "card_version": binding.card_version, "selected_greeting_id": binding.selected_greeting_id,
                             "status": binding.status, "turn_count": len(turns)})
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
            from awp_rp_runtime_v2.contracts.card_session_bootstrap_request import CardSessionBootstrapRequest
            from awp_rp_runtime_v2.runtime.card_session_bootstrap_pipeline import CardSessionBootstrapPipeline
            new_session_id = f"sess-{uuid.uuid4().hex[:12]}"
            request_id = f"req-{uuid.uuid4().hex[:12]}"
            bootstrap_request = CardSessionBootstrapRequest(
                request_id=request_id, workflow_run_id=f"wr-{request_id}", trace_id=f"tr-{request_id}",
                session_id=new_session_id, logical_card_id=card.logical_card_id, card_version=card.card_version,
                greeting_id=greeting_id, expected_source_hash=card.source_hash)
            pipeline = CardSessionBootstrapPipeline(
                definition_store=registry.card_definition_store, binding_store=registry.card_session_binding_store,
                opening_store=registry.opening_record_store, worldbook_store=registry.worldbook_binding_store,
                receipt_store=registry.bootstrap_receipt_store)
            receipt, failure, diagnostics = pipeline.bootstrap(bootstrap_request)
            if failure:
                return _console_result(command, failure.failure_message, ok=False)
            registry.card_state_store.initialize(card.logical_card_id, new_session_id)
            return _console_result(command, f"Created session {receipt.session_id if receipt else new_session_id}.",
                                   {"session_id": receipt.session_id if receipt else new_session_id,
                                    "card_id": card.logical_card_id, "greeting_id": greeting_id,
                                    "diagnostics": diagnostics.to_dict()})
        except Exception as e:
            return _console_result(command, f"Create session failed: {str(e)[:200]}", ok=False)
    if name not in {"context", "session", "history", "turns", "transcript", "state", "send", "continue"}:
        return _console_result(command, f"Unknown safe command: {name}. Type help.",
                               {"allowed_commands": allowed}, ok=False)
    if not session_id:
        return _console_result(command, "session_id is required for this command.", ok=False)
    factory = _factory()
    registry = factory.registry
    binding = registry.card_session_binding_store.load(session_id)
    if not binding:
        return _console_result(command, f"Session not found: {session_id}", ok=False)
    turns = registry.turn_record_store.list_by_session(session_id)
    session_data = {"session_id": binding.session_id, "logical_card_id": binding.logical_card_id,
                    "card_version": binding.card_version, "source_hash": binding.source_hash,
                    "selected_greeting_id": binding.selected_greeting_id, "status": binding.status,
                    "turn_count": len(turns)}
    if name == "session":
        return _console_result(command, f"Session {session_id}: {len(turns)} turns.", {"session": session_data})
    if name in {"history", "turns"}:
        try:
            limit = max(1, min(20, int(args[0]))) if args else 5
        except ValueError:
            limit = 5
        return _console_result(command, f"Latest {len(turns[-limit:])} turns.",
                               {"turns": [_turn_to_console_dict(t) for t in turns[-limit:]]})
    if name == "state":
        state = registry.card_state_store.load(binding.logical_card_id, session_id)
        return _console_result(command, "Current CardState.",
                               {"card_state": state.to_dict() if state else None})
    if name == "send":
        player_input = " ".join(args).strip()
        if not player_input:
            return _console_result(command, "Usage: send <player text>", ok=False)
        from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher
        result = ExecutionDispatcher().execute_turn(session_id, player_input, mode="python")
        return _console_result(command, "Turn executed." if result.get("success") else "Turn failed.",
                               {"result": result}, ok=bool(result.get("success")))
    if name == "continue":
        from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher
        result = ExecutionDispatcher().execute_continue(session_id, mode="python")
        return _console_result(command, "Continuation executed." if result.get("success") else "Continuation failed.",
                               {"result": result}, ok=bool(result.get("success")))
    state = registry.card_state_store.load(binding.logical_card_id, session_id)
    return _console_result(command, "AI-readable runtime context.",
                           {"session": session_data, "latest_turns": [_turn_to_console_dict(t) for t in turns[-5:]],
                            "card_state": state.to_dict() if state else None, "available_commands": allowed})


# ── 工厂 ──────────────────────────────────────────────────────────────────

def _factory() -> RuntimeStoreFactory:
    return RuntimeStoreFactory.from_env()


async def _run_blocking(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _json(data: Any, status: int = 200) -> web.Response:
    return web.json_response(
        {"data": data}, status=status,
        dumps=lambda o: json.dumps(o, ensure_ascii=False, default=str),
    )


# ── 路由注册 ──────────────────────────────────────────────────────────────

def create_app() -> web.Application:
    app = web.Application()

    # ── Sessions ───────────────────────────────────────────────────────
    app.router.add_get("/awp/api/v1/sessions", list_sessions)
    app.router.add_get("/awp/api/v1/sessions/{session_id}", get_session)
    app.router.add_get("/awp/api/v1/sessions/{session_id}/turns", list_turns)
    app.router.add_get("/awp/api/v1/sessions/{session_id}/opening", get_opening)
    app.router.add_get("/awp/api/v1/sessions/{session_id}/turns/{turn_id}/pipeline", get_turn_pipeline)
    app.router.add_post("/awp/api/v1/sessions/{session_id}/continue", continue_session)
    app.router.add_post("/awp/api/v1/sessions/{session_id}/turn", post_turn)
    app.router.add_post("/awp/api/v1/sessions/{session_id}/turn/stream", post_turn_stream)
    app.router.add_post("/awp/api/v1/sessions/{session_id}/first-turn", post_first_turn)
    app.router.add_post("/awp/api/v1/sessions", create_session)
    app.router.add_delete("/awp/api/v1/sessions/{session_id}", delete_session)

    # ── Cards ──────────────────────────────────────────────────────────
    app.router.add_get("/awp/api/v1/cards", list_cards)
    app.router.add_get("/awp/api/v1/cards/{card_id}/greetings", list_greetings)
    app.router.add_post("/awp/api/v1/cards/import", import_card)
    app.router.add_post("/awp/api/v1/cards/upload", upload_card)
    app.router.add_delete("/awp/api/v1/cards/{card_id}", delete_card)

    # ── Workflows / Presets / Console ──────────────────────────────────
    app.router.add_get("/awp/api/v1/workflows", list_workflows)
    app.router.add_get("/awp/api/v1/presets/writer", list_writer_presets)
    app.router.add_get("/awp/api/v1/presets/writer/{name}", get_writer_preset)
    app.router.add_post("/awp/api/v1/console/command", post_console_command)

    # ── SPA 静态文件 ──────────────────────────────────────────────────
    app.router.add_get("/awp", serve_spa_index)
    app.router.add_get("/awp/{tail:.*}", serve_spa_static)

    return app


# ── Handlers (复用 management_api 的逻辑) ─────────────────────────────────

async def list_sessions(request):
    factory = _factory()
    registry = factory.registry
    bindings = registry.card_session_binding_store.list_all()
    result = []
    for b in bindings:
        turns = registry.turn_record_store.list_by_session(b.session_id)
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
            "turn_count": len(turns),
            "last_turn_time": turns[-1].accepted_at if turns else b.created_at,
            "created_at": b.created_at,
            "status": b.status,
        })
    return _json(result)


async def get_session(request):
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


async def list_turns(request):
    session_id = request.match_info["session_id"]
    factory = _factory()
    registry = factory.registry
    binding = registry.card_session_binding_store.load(session_id)
    if not binding:
        return _json({"error": "Session not found"}, 404)
    turns = registry.turn_record_store.list_by_session(session_id)
    result = [{
        "turn_id": t.turn_id, "turn_index": t.turn_index, "mode": t.mode.value,
        "player_input": t.player_input, "writer_output": t.writer_output,
        "base_card_state_revision": t.base_card_state_revision,
        "result_card_state_revision": t.result_card_state_revision,
        "accepted_at": t.accepted_at, "created_at": t.created_at, "trace_id": t.trace_id,
    } for t in turns]
    return _json(result)


async def get_opening(request):
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


async def get_turn_pipeline(request):
    session_id = request.match_info["session_id"]
    turn_id = request.match_info["turn_id"]
    factory = _factory()
    registry = factory.registry
    binding = registry.card_session_binding_store.load(session_id)
    if not binding:
        return _json({"error": "Session not found"}, 404)
    trace = registry.trace_store.get_by_turn(turn_id)
    if not trace:
        return _json({"error": "Pipeline trace not found"}, 404)
    turn_record = None
    for t in registry.turn_record_store.list_by_session(session_id):
        if t.turn_id == turn_id:
            turn_record = t
            break
    active_memories = []
    rag_memories = []
    try:
        conn = registry.db.connect()
        rows = conn.execute(
            "SELECT memory_json FROM active_memory_records WHERE session_id=? AND memory_json LIKE ?",
            (session_id, f"%{turn_id}%"),
        ).fetchall()
        for row in rows:
            mem = json.loads(row["memory_json"])
            active_memories.append({
                "memory_id": mem.get("memory_id", ""), "kind": mem.get("kind", ""),
                "summary": mem.get("summary", ""), "importance": mem.get("importance", 0),
                "retention_reason": mem.get("retention_reason", ""),
            })
        rows = conn.execute(
            "SELECT memory_json FROM rag_memory_records WHERE session_id=? AND memory_json LIKE ?",
            (session_id, f"%{turn_id}%"),
        ).fetchall()
        for row in rows:
            mem = json.loads(row["memory_json"])
            rag_memories.append({
                "memory_id": mem.get("memory_id", ""), "content": mem.get("content", ""),
                "scope": mem.get("scope", ""), "importance": mem.get("importance", 0),
            })
    except Exception:
        pass
    trace_dict = trace.to_dict()
    steps = [{
        "event_type": evt.get("event_type", ""), "actor": evt.get("actor", ""),
        "duration_ms": evt.get("duration_ms", 0), "success": evt.get("success", True),
        "error": evt.get("error"), "details": evt.get("details", {}),
    } for evt in trace_dict.get("events", [])]
    return _json({
        "trace_id": trace.trace_id, "turn_id": trace.turn_id, "session_id": trace.session_id,
        "total_duration_ms": trace_dict.get("total_duration_ms", 0),
        "success": trace_dict.get("success", True), "steps": steps,
        "writer_output": turn_record.writer_output if turn_record else "",
        "player_input": turn_record.player_input if turn_record else "",
        "turn_index": turn_record.turn_index if turn_record else 0,
        "active_memories": active_memories, "rag_memories": rag_memories,
    })


async def continue_session(request):
    session_id = request.match_info["session_id"]
    mode = request.query.get("mode", "")
    workflow = request.query.get("workflow", "")
    factory = _factory()
    binding = factory.registry.card_session_binding_store.load(session_id)
    if not binding:
        return _json({"error": "Session not found"}, 404)
    try:
        from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher
        result = await _run_blocking(ExecutionDispatcher().execute_continue, session_id, mode=mode, workflow=workflow)
        return _json(result)
    except Exception as e:
        return _json({"error": f"Continue failed: {str(e)[:200]}"}, 500)


async def post_turn(request):
    session_id = request.match_info["session_id"]
    body = await request.json()
    player_input = body.get("player_input", "")
    mode = request.query.get("mode", "")
    workflow = request.query.get("workflow", "")
    if not player_input:
        return _json({"error": "player_input required"}, 400)
    try:
        from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher
        result = await _run_blocking(ExecutionDispatcher().execute_turn, session_id, player_input, mode=mode, workflow=workflow)
        return _json(result)
    except Exception as e:
        return _json({"error": f"Turn failed: {str(e)[:200]}"}, 500)


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

    def _run_streaming_turn() -> None:
        try:
            from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher
            ExecutionDispatcher().execute_turn_streaming(
                session_id, player_input, mode=mode, workflow=workflow,
                on_started=lambda tid, steps: _enqueue("started", {"turn_id": tid, "steps": steps}),
                on_step=lambda name, payload: _enqueue("step", {"step": name, "payload": payload, "duration_ms": payload.get("duration_ms", 0)}),
                on_writer_text=lambda tid, text: _enqueue("writer_text", {"turn_id": tid, "writer_output": text}),
                on_done=lambda result: _enqueue("done", result),
            )
        except Exception as e:
            _enqueue("done", {"success": False, "turn_id": "", "turn_index": 0,
                              "error": f"Turn failed: {str(e)[:200]}", "failure_code": "STREAM_EXECUTION_ERROR"})

    loop.run_in_executor(None, functools.partial(_run_streaming_turn))

    response = web.StreamResponse(
        status=200,
        headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache",
                 "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
    await response.prepare(request)
    await response.drain()

    while True:
        try:
            event_type, data = await asyncio.wait_for(queue.get(), timeout=180)
        except asyncio.TimeoutError:
            event_type = "done"
            data = {"success": False, "turn_id": "", "turn_index": 0,
                    "error": "timeout", "failure_code": "TIMEOUT"}
        chunk = (f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n").encode("utf-8")
        try:
            await response.write(chunk)
            await response.drain()
        except (ConnectionResetError, RuntimeError, asyncio.CancelledError):
            break
        if event_type == "done":
            break
    try:
        await response.write_eof()
    except (ConnectionResetError, RuntimeError, asyncio.CancelledError):
        pass
    return response


async def post_first_turn(request):
    session_id = request.match_info["session_id"]
    body = await request.json()
    player_input = body.get("player_input", "")
    mode = request.query.get("mode", "")
    workflow = request.query.get("workflow", "")
    try:
        from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher
        result = await _run_blocking(ExecutionDispatcher().execute_first_turn, session_id, player_input, mode=mode, workflow=workflow)
        return _json(result)
    except Exception as e:
        return _json({"error": f"First turn failed: {str(e)[:200]}"}, 500)


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
        from awp_rp_runtime_v2.contracts.card_session_bootstrap_request import CardSessionBootstrapRequest
        from awp_rp_runtime_v2.runtime.card_session_bootstrap_pipeline import CardSessionBootstrapPipeline
        session_id = body.get("session_id") or f"sess-{uuid.uuid4().hex[:12]}"
        request_id = body.get("request_id") or f"req-{uuid.uuid4().hex[:12]}"
        bootstrap_request = CardSessionBootstrapRequest(
            request_id=request_id, workflow_run_id=f"wr-{request_id}", trace_id=f"tr-{request_id}",
            session_id=session_id, logical_card_id=card.logical_card_id, card_version=card.card_version,
            greeting_id=greeting_id, expected_source_hash=card.source_hash,
        )
        pipeline = CardSessionBootstrapPipeline(
            definition_store=registry.card_definition_store, binding_store=registry.card_session_binding_store,
            opening_store=registry.opening_record_store, worldbook_store=registry.worldbook_binding_store,
            receipt_store=registry.bootstrap_receipt_store,
        )
        receipt, failure, diagnostics = pipeline.bootstrap(bootstrap_request)
        if failure:
            return _json({"error": failure.failure_message}, 400)
        registry.card_state_store.initialize(card.logical_card_id, session_id)
        return _json({
            "session_id": receipt.session_id if receipt else session_id,
            "card_id": card.logical_card_id, "greeting_id": greeting_id,
            "diagnostics": diagnostics.to_dict(),
        })
    except Exception as e:
        return _json({"error": f"Create session failed: {str(e)[:200]}"}, 500)


async def delete_session(request):
    session_id = request.match_info["session_id"]
    try:
        from awp_rp_runtime_v2.runtime.session_deletion_service import SessionDeletionService
        factory = _factory()
        SessionDeletionService(factory.registry).delete_session(session_id)
        return _json({"success": True})
    except Exception as e:
        return _json({"error": str(e)[:200]}, 500)


async def list_cards(request):
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
            "card_id": c.logical_card_id, "version": c.card_version,
            "name": c.display_name or c.name or c.logical_card_id, "status": c.status,
            "greeting_count": len(c.greetings) if c.greetings else 0,
            "worldbook_count": len(c.worldbook_catalog) if c.worldbook_catalog else 0,
            "created_at": c.created_at,
        })
    return _json(result)


async def list_greetings(request):
    card_id = request.match_info["card_id"]
    factory = _factory()
    card = factory.registry.card_definition_store.get_latest(card_id)
    if not card:
        return _json({"error": "Card not found"}, 404)
    greetings = []
    for g in card.greetings or []:
        content = g.get("safe_display_content", "") or g.get("content", "") or ""
        greetings.append({
            "greeting_id": g.get("greeting_id", ""), "label": g.get("label", ""),
            "is_default": bool(g.get("is_default", False)), "preview": content[:120],
        })
    return _json(greetings)


async def import_card(request):
    body = await request.json()
    source_path = body.get("source_path", "")
    if not source_path:
        return _json({"error": "source_path required"}, 400)
    try:
        from awp_rp_runtime_v2.nodes.persistent_bootstrap_node import AWPV2PersistentBootstrap
        session_id = body.get("session_id") or f"imp-{uuid.uuid4().hex[:12]}"
        binding, _opening, _worldbook, _receipt, diagnostics = AWPV2PersistentBootstrap().execute(
            source_path=source_path, session_id=session_id,
            greeting_id=body.get("greeting_id", "g0"),
            request_id=body.get("request_id", f"imp-{uuid.uuid4().hex[:12]}"),
        )
        return _json({
            "success": diagnostics.get("commit_status") == "success",
            "session_id": binding.get("session_id", ""), "card_id": binding.get("logical_card_id", ""),
            "diagnostics": diagnostics,
        })
    except Exception as e:
        return _json({"error": f"Import failed: {str(e)[:200]}"}, 500)


async def upload_card(request):
    """接收上传的角色卡文件（JSON/PNG），保存到临时目录后导入。"""
    reader = await request.multipart()
    field = await reader.next()
    if not field or field.name != "file":
        return _json({"error": "请上传文件"}, 400)

    filename = field.filename or "uploaded_card.json"
    suffix = Path(filename).suffix.lower()
    if suffix not in (".json", ".png"):
        return _json({"error": f"不支持的文件格式: {suffix}，仅支持 .json 和 .png"}, 400)

    # 保存到临时目录
    import tempfile
    tmp_dir = Path(tempfile.mkdtemp(prefix="awp_upload_"))
    tmp_path = tmp_dir / filename
    data = await field.read()
    tmp_path.write_bytes(data)

    try:
        from awp_rp_runtime_v2.nodes.persistent_bootstrap_node import AWPV2PersistentBootstrap
        greeting_id = request.query.get("greeting_id", "g0")
        session_id = f"imp-{uuid.uuid4().hex[:12]}"
        binding, _opening, _worldbook, _receipt, diagnostics = AWPV2PersistentBootstrap().execute(
            source_path=str(tmp_path), session_id=session_id,
            greeting_id=greeting_id,
            request_id=f"imp-{uuid.uuid4().hex[:12]}",
        )
        return _json({
            "success": diagnostics.get("commit_status") == "success",
            "session_id": binding.get("session_id", ""), "card_id": binding.get("logical_card_id", ""),
            "diagnostics": diagnostics,
        })
    except Exception as e:
        return _json({"error": f"导入失败: {str(e)[:200]}"}, 500)
    finally:
        # 清理临时文件
        try:
            tmp_path.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except Exception:
            pass


async def delete_card(request):
    card_id = request.match_info["card_id"]
    try:
        from awp_rp_runtime_v2.runtime.session_deletion_service import SessionDeletionService
        factory = _factory()
        SessionDeletionService(factory.registry).delete_card(card_id)
        return _json({"success": True})
    except Exception as e:
        return _json({"error": str(e)[:200]}, 500)


async def list_workflows(request):
    from awp_rp_runtime_v2.testing.api_workflow_loader import APIWorkflowLoader
    loader = APIWorkflowLoader()
    result = []
    for name in loader.list_workflows():
        workflow = loader.load(name)
        class_types = sorted({nd.get("class_type", "") for nd in workflow.values() if isinstance(nd, dict)})
        result.append({"name": name, "node_count": len(workflow), "class_types": class_types})
    return _json(result)


async def list_writer_presets(request):
    from awp_rp_runtime_v2.presets.writer_preset_loader import WriterPresetLoader
    return _json(WriterPresetLoader().list_presets())


async def get_writer_preset(request):
    from awp_rp_runtime_v2.presets.writer_preset_loader import WriterPresetLoader
    name = request.match_info["name"]
    loader = WriterPresetLoader()
    content = loader.load(name)
    path = loader.get_preset_path(name)
    if not content and not path:
        return _json({"error": "Preset not found"}, 404)
    return _json({"name": name, "content": content, "path": path})


async def post_console_command(request):
    body = await request.json()
    command = body.get("command", "")
    session_id = body.get("session_id", "")
    try:
        result = await _run_blocking(_run_console_command, command, session_id)
        return _json(result)
    except Exception as e:
        return _json(_console_result(str(command), str(e)[:300], ok=False), 500)


async def serve_spa_index(request):
    index_path = _MANAGEMENT_DIR / "index.html"
    if not index_path.exists():
        return web.Response(text="Management panel not built yet. Run: cd web && npm run build", content_type="text/plain")
    with open(str(index_path), "r", encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/html")


async def serve_spa_static(request):
    tail = request.match_info.get("tail", "")
    file_path = _resolve_static_asset_path(tail)
    if file_path and file_path.exists() and file_path.is_file():
        content_type = _mime_type(file_path.suffix)
        with open(str(file_path), "rb") as f:
            return web.Response(body=f.read(), content_type=content_type)
    index_path = _MANAGEMENT_DIR / "index.html"
    if index_path.exists():
        with open(str(index_path), "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="text/html")
    return web.Response(text="Not found", status=404)


# ── 启动 ──────────────────────────────────────────────────────────────────

def _find_db_path() -> str:
    """Auto-find the database by searching common locations."""
    # 1. 环境变量优先
    env_path = os.environ.get("AWP_RUNTIME_DB_PATH", "")
    if env_path and Path(env_path).exists():
        return env_path

    # 2. 当前目录
    if Path("awp_rp_runtime.db").exists():
        return str(Path("awp_rp_runtime.db").resolve())

    # 3. 向上搜索 ComfyUI 根目录
    here = Path(__file__).resolve().parent
    for ancestor in [here, *here.parents]:
        db = ancestor / "awp_rp_runtime.db"
        if db.exists():
            return str(db)

    # 4. 默认当前目录（会自动创建）
    return str(Path("awp_rp_runtime.db").resolve())


def main():
    parser = argparse.ArgumentParser(description="AWP RP Runtime standalone server")
    parser.add_argument("--port", type=int, default=8188)
    parser.add_argument("--host", default="127.0.0.1")  # 默认只绑本地
    parser.add_argument("--db-path", default="", help="Override database path")
    args = parser.parse_args()

    db_path = args.db_path or _find_db_path()
    os.environ["AWP_RUNTIME_DB_PATH"] = db_path

    app = create_app()
    print(f"AWP RP Runtime server starting on http://{args.host}:{args.port}")
    print(f"Database: {db_path}")
    print(f"Frontend: http://localhost:{args.port}/awp/")
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
