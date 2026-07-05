from __future__ import annotations

import asyncio
import importlib
import json
import sys
import threading
from types import SimpleNamespace

from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
from awp_rp_runtime_v2.storage.sqlite.database import Database
from awp_rp_runtime_v2.contracts.active_memory import ActiveMemoryRecord
from awp_rp_runtime_v2.contracts.execution_trace import ExecutionTrace, TraceEvent
from awp_rp_runtime_v2.contracts.rag_memory import RagMemoryRecord
from awp_rp_runtime_v2.tests.factories import (
    make_binding,
    make_card_definition,
    make_opening_record,
    make_turn_record,
)


class _Routes:
    def __init__(self) -> None:
        self.handlers = {}

    def get(self, path):
        return self._register("GET", path)

    def post(self, path):
        return self._register("POST", path)

    def delete(self, path):
        return self._register("DELETE", path)

    def _register(self, method, path):
        def deco(func):
            self.handlers[(method, path)] = func
            return func

        return deco


class _Request:
    def __init__(self, match_info=None, body=None, query=None) -> None:
        self.match_info = match_info or {}
        self._body = body or {}
        self.query = query or {}

    async def json(self):
        return self._body


def _load_api(monkeypatch):
    routes = _Routes()
    fake_server = SimpleNamespace(
        PromptServer=SimpleNamespace(instance=SimpleNamespace(routes=routes))
    )
    monkeypatch.setitem(sys.modules, "server", fake_server)
    module_name = "awp_rp_runtime_v2.runtime.management_api"
    if module_name in sys.modules:
        module = importlib.reload(sys.modules[module_name])
    else:
        module = importlib.import_module(module_name)
    return module, routes


def _registry(tmp_path):
    db = Database(tmp_path / "api.db")
    db.initialize()
    return SessionRuntimeStoreRegistry(db)


def _data(response):
    return json.loads(response.text)["data"]


def test_post_turn_endpoint_dispatches_player_input(tmp_path, monkeypatch):
    _module, routes = _load_api(monkeypatch)
    calls = {}

    from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher

    def fake_execute_turn(self, session_id, player_input, mode="", workflow=""):
        calls.update(
            {
                "session_id": session_id,
                "player_input": player_input,
                "mode": mode,
                "workflow": workflow,
            }
        )
        return {"success": True, "turn_id": "t1", "writer_output": "ok"}

    monkeypatch.setattr(ExecutionDispatcher, "execute_turn", fake_execute_turn)

    handler = routes.handlers[("POST", "/awp/api/v1/sessions/{session_id}/turn")]
    response = asyncio.run(
        handler(
            _Request(
                match_info={"session_id": "s1"},
                body={"player_input": "hello"},
                query={"mode": "python", "workflow": "send_turn"},
            )
        )
    )

    assert response.status == 200
    assert _data(response)["success"] is True
    assert calls == {
        "session_id": "s1",
        "player_input": "hello",
        "mode": "python",
        "workflow": "send_turn",
    }


def test_post_turn_dispatcher_runs_off_event_loop_thread(tmp_path, monkeypatch):
    _module, routes = _load_api(monkeypatch)
    calls = {}

    from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher

    def fake_execute_turn(self, session_id, player_input, mode="", workflow=""):
        calls["dispatcher_thread_id"] = threading.get_ident()
        return {"success": True, "turn_id": "t1", "writer_output": "ok"}

    monkeypatch.setattr(ExecutionDispatcher, "execute_turn", fake_execute_turn)

    handler = routes.handlers[("POST", "/awp/api/v1/sessions/{session_id}/turn")]

    async def invoke():
        calls["event_loop_thread_id"] = threading.get_ident()
        return await handler(
            _Request(
                match_info={"session_id": "s1"},
                body={"player_input": "hello"},
                query={"mode": "hybrid", "workflow": "send_turn"},
            )
        )

    response = asyncio.run(invoke())

    assert response.status == 200
    assert calls["dispatcher_thread_id"] != calls["event_loop_thread_id"]


def test_post_turn_stream_endpoint_writes_sse_events(monkeypatch):
    module, routes = _load_api(monkeypatch)

    class FakeStreamResponse:
        last = None

        def __init__(self, *, status=200, reason=None, headers=None):
            self.status = status
            self.reason = reason
            self.headers = headers or {}
            self.content_type = self.headers.get("Content-Type", "")
            self.writes: list[bytes] = []
            FakeStreamResponse.last = self

        async def prepare(self, request):
            return self

        async def drain(self):
            pass

        async def write(self, data: bytes):
            self.writes.append(data)

        async def write_eof(self):
            pass

    monkeypatch.setattr(module.web, "StreamResponse", FakeStreamResponse)

    from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher

    def fake_execute_turn_streaming(
        self,
        session_id,
        player_input,
        mode="",
        workflow="",
        on_started=None,
        on_step=None,
        on_writer_text=None,
        on_done=None,
    ):
        assert mode == "python"
        assert workflow == "send_turn"
        on_started("turn-1", ["round_snapshot", "director"])
        on_step("round_snapshot", {"duration_ms": 1, "snapshot_id": "snap-1"})
        on_writer_text("turn-1", "accepted text")
        on_done({"success": True, "turn_id": "turn-1", "turn_index": 2})
        return {"success": True, "turn_id": "turn-1", "turn_index": 2}

    monkeypatch.setattr(
        ExecutionDispatcher,
        "execute_turn_streaming",
        fake_execute_turn_streaming,
    )

    handler = routes.handlers[("POST", "/awp/api/v1/sessions/{session_id}/turn/stream")]

    async def invoke():
        return await handler(
            _Request(
                match_info={"session_id": "s1"},
                body={"player_input": "hello"},
                query={"mode": "python", "workflow": "send_turn"},
            )
        )

    response = asyncio.run(invoke())
    raw = b"".join(response.writes).decode("utf-8")

    assert response.content_type == "text/event-stream"
    assert "event: started\n" in raw
    assert '"turn_id": "turn-1"' in raw
    assert "event: step\n" in raw
    assert '"step": "round_snapshot"' in raw
    assert "event: writer_text\n" in raw
    assert '"writer_output": "accepted text"' in raw
    assert raw.rstrip().endswith(
        'data: {"success": true, "turn_id": "turn-1", "turn_index": 2}'
    )


def test_post_turn_stream_empty_input_returns_400(monkeypatch):
    _module, routes = _load_api(monkeypatch)

    handler = routes.handlers[("POST", "/awp/api/v1/sessions/{session_id}/turn/stream")]
    response = asyncio.run(
        handler(_Request(match_info={"session_id": "s1"}, body={"player_input": "  "}))
    )

    assert response.status == 400
    assert _data(response)["error"] == "player_input required"


def test_turn_pipeline_rejects_trace_from_other_session(tmp_path, monkeypatch):
    module, routes = _load_api(monkeypatch)
    reg = _registry(tmp_path)
    reg.card_session_binding_store.save(make_binding(session_id="s1", logical_card_id="c1"))
    reg.trace_store.save(ExecutionTrace(
        trace_id="trace-other",
        turn_id="turn-other",
        card_id="c2",
        session_id="s2",
    ))
    monkeypatch.setattr(module, "_factory", lambda: SimpleNamespace(registry=reg))

    handler = routes.handlers[("GET", "/awp/api/v1/sessions/{session_id}/turns/{turn_id}/pipeline")]
    response = asyncio.run(handler(_Request(match_info={"session_id": "s1", "turn_id": "turn-other"})))

    assert response.status == 404


def test_turn_pipeline_redacts_trace_output_preview(tmp_path, monkeypatch):
    module, routes = _load_api(monkeypatch)
    reg = _registry(tmp_path)
    reg.card_session_binding_store.save(make_binding(session_id="s1", logical_card_id="c1"))
    reg.turn_record_store.save(make_turn_record(
        session_id="s1",
        card_id="c1",
        turn_id="t1",
        player_input="Player input is session-owned",
        writer_output="Writer output is session-owned",
    ))
    reg.trace_store.save(ExecutionTrace(
        trace_id="trace-t1",
        turn_id="t1",
        card_id="c1",
        session_id="s1",
        events=[
            TraceEvent(
                event_type="writer",
                actor="writer",
                details={"output_preview": "RAW WRITER TEXT", "text_length": 15},
            )
        ],
    ))
    monkeypatch.setattr(module, "_factory", lambda: SimpleNamespace(registry=reg))

    handler = routes.handlers[("GET", "/awp/api/v1/sessions/{session_id}/turns/{turn_id}/pipeline")]
    response = asyncio.run(handler(_Request(match_info={"session_id": "s1", "turn_id": "t1"})))

    step = _data(response)["steps"][0]
    assert "output_preview" not in step["details"]
    assert step["details"]["text_length"] == 15


def test_turn_pipeline_memory_lookup_uses_source_turn_ids(tmp_path, monkeypatch):
    module, routes = _load_api(monkeypatch)
    reg = _registry(tmp_path)
    reg.card_session_binding_store.save(make_binding(session_id="s1", logical_card_id="c1"))
    reg.turn_record_store.save(make_turn_record(session_id="s1", card_id="c1", turn_id="t1"))
    reg.trace_store.save(ExecutionTrace(
        trace_id="trace-t1",
        turn_id="t1",
        card_id="c1",
        session_id="s1",
    ))
    reg.active_memory_store.upsert("c1", "s1", ActiveMemoryRecord(
        memory_id="am-good",
        card_id="c1",
        session_id="s1",
        summary="Source-bound memory for this turn",
        source_turn_ids=["t1"],
    ))
    reg.active_memory_store.upsert("c1", "s1", ActiveMemoryRecord(
        memory_id="am-false-positive",
        card_id="c1",
        session_id="s1",
        summary="Mentions t1 in text but belongs elsewhere",
        source_turn_ids=["t2"],
    ))
    reg.rag_memory_store.save("c1", "s1", RagMemoryRecord(
        memory_id="rag-good",
        card_id="c1",
        session_id="s1",
        content="Long-term memory for this turn",
        source_turn_ids=["t1"],
    ))
    reg.rag_memory_store.save("c1", "s1", RagMemoryRecord(
        memory_id="rag-false-positive",
        card_id="c1",
        session_id="s1",
        content="Mentions t1 in content but belongs elsewhere",
        source_turn_ids=["t2"],
    ))
    monkeypatch.setattr(module, "_factory", lambda: SimpleNamespace(registry=reg))

    handler = routes.handlers[("GET", "/awp/api/v1/sessions/{session_id}/turns/{turn_id}/pipeline")]
    response = asyncio.run(handler(_Request(match_info={"session_id": "s1", "turn_id": "t1"})))

    data = _data(response)
    assert [m["memory_id"] for m in data["active_memories"]] == ["am-good"]
    assert [m["memory_id"] for m in data["rag_memories"]] == ["rag-good"]


def test_greetings_endpoint_lists_card_greetings(tmp_path, monkeypatch):
    module, routes = _load_api(monkeypatch)
    reg = _registry(tmp_path)
    card = make_card_definition("c1")
    reg.card_definition_store.save(card)
    monkeypatch.setattr(module, "_factory", lambda: SimpleNamespace(registry=reg))

    handler = routes.handlers[("GET", "/awp/api/v1/cards/{card_id}/greetings")]
    response = asyncio.run(handler(_Request(match_info={"card_id": "c1"})))

    assert response.status == 200
    greetings = _data(response)
    assert greetings[0]["greeting_id"] == "g0"
    assert greetings[0]["is_default"] is True


def test_create_session_from_existing_card(tmp_path, monkeypatch):
    module, routes = _load_api(monkeypatch)
    reg = _registry(tmp_path)
    reg.card_definition_store.save(make_card_definition("c1"))
    monkeypatch.setattr(module, "_factory", lambda: SimpleNamespace(registry=reg))

    handler = routes.handlers[("POST", "/awp/api/v1/sessions")]
    response = asyncio.run(
        handler(_Request(body={"card_id": "c1", "greeting_id": "g0", "session_id": "s-new"}))
    )

    assert response.status == 200
    data = _data(response)
    assert data["session_id"] == "s-new"
    assert reg.card_session_binding_store.load("s-new") is not None


def test_delete_session_and_card_endpoints_cascade(tmp_path, monkeypatch):
    module, routes = _load_api(monkeypatch)
    reg = _registry(tmp_path)
    reg.card_definition_store.save(make_card_definition("c1"))
    reg.card_session_binding_store.save(make_binding(session_id="s1", logical_card_id="c1"))
    reg.turn_record_store.save(make_turn_record(session_id="s1", card_id="c1"))
    monkeypatch.setattr(module, "_factory", lambda: SimpleNamespace(registry=reg))

    delete_session = routes.handlers[("DELETE", "/awp/api/v1/sessions/{session_id}")]
    session_response = asyncio.run(delete_session(_Request(match_info={"session_id": "s1"})))

    assert session_response.status == 200
    assert reg.card_session_binding_store.load("s1") is None
    assert reg.turn_record_store.list_by_session("s1") == []

    reg.card_session_binding_store.save(make_binding(session_id="s2", logical_card_id="c1"))
    delete_card = routes.handlers[("DELETE", "/awp/api/v1/cards/{card_id}")]
    card_response = asyncio.run(delete_card(_Request(match_info={"card_id": "c1"})))

    assert card_response.status == 200
    assert reg.card_definition_store.get_latest("c1") is None
    assert reg.card_session_binding_store.list_by_card("c1") == []


def test_continue_endpoint_dispatches_mode_and_workflow(tmp_path, monkeypatch):
    module, routes = _load_api(monkeypatch)
    reg = _registry(tmp_path)
    reg.card_session_binding_store.save(make_binding(session_id="s1", logical_card_id="c1"))
    monkeypatch.setattr(module, "_factory", lambda: SimpleNamespace(registry=reg))

    calls = {}
    from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher

    def fake_execute_continue(self, session_id, mode="", workflow=""):
        calls["session_id"] = session_id
        calls["mode"] = mode
        calls["workflow"] = workflow
        return {"success": True, "writer_output": "continued"}

    monkeypatch.setattr(ExecutionDispatcher, "execute_continue", fake_execute_continue)

    handler = routes.handlers[("POST", "/awp/api/v1/sessions/{session_id}/continue")]
    response = asyncio.run(
        handler(
            _Request(
                match_info={"session_id": "s1"},
                query={"mode": "python", "workflow": "continue_world"},
            )
        )
    )

    assert response.status == 200
    assert _data(response)["writer_output"] == "continued"
    assert calls == {
        "session_id": "s1",
        "mode": "python",
        "workflow": "continue_world",
    }


def test_console_command_help(monkeypatch):
    _module, routes = _load_api(monkeypatch)

    handler = routes.handlers[("POST", "/awp/api/v1/console/command")]
    response = asyncio.run(handler(_Request(body={"command": "help"})))

    assert response.status == 200
    data = _data(response)
    assert data["ok"] is True
    assert "context" in data["data"]["commands"]
    assert data["data"]["shell"] is False


def test_console_command_context_uses_project_session(tmp_path, monkeypatch):
    module, routes = _load_api(monkeypatch)
    reg = _registry(tmp_path)
    reg.card_definition_store.save(make_card_definition("c1"))
    reg.card_session_binding_store.save(make_binding(session_id="s1", logical_card_id="c1"))
    reg.card_state_store.initialize("c1", "s1")
    reg.turn_record_store.save(make_turn_record(session_id="s1", card_id="c1"))
    monkeypatch.setattr(module, "_factory", lambda: SimpleNamespace(registry=reg))

    handler = routes.handlers[("POST", "/awp/api/v1/console/command")]
    response = asyncio.run(handler(_Request(body={"command": "context", "session_id": "s1"})))

    assert response.status == 200
    data = _data(response)
    assert data["ok"] is True
    assert data["data"]["session"]["session_id"] == "s1"
    assert len(data["data"]["latest_turns"]) == 1
    assert "available_commands" in data["data"]


def test_console_command_transcript_prints_full_session_text(tmp_path, monkeypatch):
    module, routes = _load_api(monkeypatch)
    reg = _registry(tmp_path)
    reg.card_definition_store.save(make_card_definition("c1"))
    reg.card_session_binding_store.save(make_binding(session_id="s1", logical_card_id="c1"))
    reg.opening_record_store.save(make_opening_record(session_id="s1", logical_card_id="c1", content="Opening text"))
    reg.card_state_store.initialize("c1", "s1")
    reg.turn_record_store.save(make_turn_record(
        session_id="s1",
        card_id="c1",
        player_input="Player says hello",
        writer_output="Writer answers",
    ))
    monkeypatch.setattr(module, "_factory", lambda: SimpleNamespace(registry=reg))

    handler = routes.handlers[("POST", "/awp/api/v1/console/command")]
    response = asyncio.run(handler(_Request(body={"command": "transcript", "session_id": "s1"})))

    data = _data(response)
    text = data["data"]["text"]
    assert data["ok"] is True
    assert "Opening text" in text
    assert "Player says hello" in text
    assert "Writer answers" in text
    assert "=== CardState ===" in text


def test_console_command_rejects_unknown_command(monkeypatch):
    _module, routes = _load_api(monkeypatch)

    handler = routes.handlers[("POST", "/awp/api/v1/console/command")]
    response = asyncio.run(handler(_Request(body={"command": "shell rm -rf ."})))

    assert response.status == 200
    data = _data(response)
    assert data["ok"] is False
    assert "Unknown safe command" in data["output"]


def test_console_command_lists_cards_and_sessions(tmp_path, monkeypatch):
    module, routes = _load_api(monkeypatch)
    reg = _registry(tmp_path)
    reg.card_definition_store.save(make_card_definition("c1"))
    reg.card_session_binding_store.save(make_binding(session_id="s1", logical_card_id="c1"))
    monkeypatch.setattr(module, "_factory", lambda: SimpleNamespace(registry=reg))

    handler = routes.handlers[("POST", "/awp/api/v1/console/command")]
    cards_response = asyncio.run(handler(_Request(body={"command": "cards"})))
    sessions_response = asyncio.run(handler(_Request(body={"command": "sessions"})))

    assert _data(cards_response)["data"]["cards"][0]["card_id"] == "c1"
    assert _data(sessions_response)["data"]["sessions"][0]["session_id"] == "s1"


def test_console_command_creates_new_session(tmp_path, monkeypatch):
    module, routes = _load_api(monkeypatch)
    reg = _registry(tmp_path)
    reg.card_definition_store.save(make_card_definition("c1"))
    monkeypatch.setattr(module, "_factory", lambda: SimpleNamespace(registry=reg))

    handler = routes.handlers[("POST", "/awp/api/v1/console/command")]
    response = asyncio.run(handler(_Request(body={"command": "new c1 g0"})))

    data = _data(response)
    assert data["ok"] is True
    session_id = data["data"]["session_id"]
    assert reg.card_session_binding_store.load(session_id) is not None


def test_console_command_send_dispatches_python_turn(tmp_path, monkeypatch):
    module, routes = _load_api(monkeypatch)
    reg = _registry(tmp_path)
    reg.card_session_binding_store.save(make_binding(session_id="s1", logical_card_id="c1"))
    monkeypatch.setattr(module, "_factory", lambda: SimpleNamespace(registry=reg))

    calls = {}
    from awp_rp_runtime_v2.runtime.execution_dispatcher import ExecutionDispatcher

    def fake_execute_turn(self, session_id, player_input, mode="", workflow=""):
        calls.update({
            "session_id": session_id,
            "player_input": player_input,
            "mode": mode,
            "workflow": workflow,
        })
        return {"success": True, "turn_id": "t1", "writer_output": "ok"}

    monkeypatch.setattr(ExecutionDispatcher, "execute_turn", fake_execute_turn)

    handler = routes.handlers[("POST", "/awp/api/v1/console/command")]
    response = asyncio.run(
        handler(_Request(body={"command": 'send "hello world"', "session_id": "s1"}))
    )

    assert _data(response)["ok"] is True
    assert calls == {
        "session_id": "s1",
        "player_input": "hello world",
        "mode": "python",
        "workflow": "",
    }


def test_static_asset_path_cannot_escape_management_dist(monkeypatch):
    module, _routes = _load_api(monkeypatch)

    assert module._resolve_static_asset_path("assets/app.js").name == "app.js"
    assert module._resolve_static_asset_path("../README.md") is None
    assert module._resolve_static_asset_path("..\\README.md") is None
    assert module._resolve_static_asset_path(str(module._MANAGEMENT_DIR.parent / "README.md")) is None
