"""Shared test fixtures."""

import sys
import types
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ComfyUI runtime module `comfy_execution.validation` is only available inside a
# running ComfyUI process. Several node/workflow tests exercise its
# `validate_node_input` to check link type compatibility. Provide a faithful
# offline stub when the real module is absent so these tests run under plain
# pytest. The stub honours the AnyType("*") wildcard declared by
# AWPV2TraceDisplay (accepts any received type) and otherwise falls back to
# exact match or membership for union (list/tuple) input declarations.
try:  # pragma: no cover - exercised only inside ComfyUI
    import comfy_execution.validation  # noqa: F401
except ModuleNotFoundError:
    _stub = types.ModuleType("comfy_execution")
    _stub_validation = types.ModuleType("comfy_execution.validation")

    def validate_node_input(received, expected, *args, **kwargs):
        if str(expected) == "*":
            return True
        if isinstance(expected, (list, tuple, set)):
            return any(str(e) == "*" or e == received for e in expected)
        return expected == received

    _stub_validation.validate_node_input = validate_node_input
    _stub.validation = _stub_validation
    sys.modules["comfy_execution"] = _stub
    sys.modules["comfy_execution.validation"] = _stub_validation

import pytest
from awp_rp_runtime_v2.testing.fakes import (
    FakeCardStateStore, FakeTurnRecordStore, FakeActiveMemoryStore,
    FakeRagMemoryStore, FakeTraceStore, FakeLLMProvider,
)
from awp_rp_runtime_v2.contracts.card_state import CardState, VariableEntry, SceneState


@pytest.fixture
def fake_card_state_store():
    return FakeCardStateStore()

@pytest.fixture
def fake_turn_record_store():
    return FakeTurnRecordStore()

@pytest.fixture
def fake_active_memory_store():
    return FakeActiveMemoryStore()

@pytest.fixture
def fake_rag_memory_store():
    return FakeRagMemoryStore()

@pytest.fixture
def fake_trace_store():
    return FakeTraceStore()

@pytest.fixture
def fake_llm():
    return FakeLLMProvider()
