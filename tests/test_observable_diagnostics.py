"""可观察工作流管线数据回填测试。

PersistentTurnEngine 必须把以下管线数据回填到 FirstTurnDiagnostics，否则
AWPV2PersistentTurnObserver 的观察视图是空壳：

  * step_timings_ms      —— 每步耗时（execution_trace 时间线用）
  * agent_dispositions   —— 触发的 sub-agent role→summary（sub_agents 观察用）
  * memory_curation_reason —— 记忆治理原因（memory 观察用）
"""

from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
from awp_rp_runtime_v2.tests.test_long_session_v1 import (
    _close_db,
    _make_db,
    _make_snapshot,
    _seed_session,
)


def _run_engine(tmp_path, writer_output: str = "A grounded scene with sensory detail. " * 20):
    """跑一次 fake-profile 引擎，返回 diagnostics dict。"""
    db = _make_db(str(tmp_path))
    registry = SessionRuntimeStoreRegistry(db)
    _seed_session(registry)
    snapshot = _make_snapshot(registry, "c1", "s1")
    card_state = registry.card_state_store.load("c1", "s1")
    binding = registry.card_session_binding_store.load("s1")

    from awp_rp_runtime_v2.runtime import persistent_turn_engine as engine_module

    class _StubWriterAdapter:
        def __init__(self, text):
            self._text = text
            self.calls = 0

        def generate(self, bundle):
            self.calls += 1
            return self._text

    from awp_rp_runtime_v2.runtime.provider_adapter_factory import AdapterOutcome

    engine_module.WriterAdapterFactory.build = staticmethod(
        lambda profile_id, preset_text="": (
            _StubWriterAdapter(writer_output),
            AdapterOutcome(
                is_real=False, provider="fake", model="test-stub-writer",
                profile_id=profile_id, api_key_env="", built=True,
            ),
        )
    )

    engine = engine_module.PersistentTurnEngine(registry, profile="test")
    result = engine.execute(
        session_id="s1", player_input="hello", binding=binding, snapshot=snapshot,
        card_state=card_state, turn_id="t-obs", attempt_id="a-obs", request_id="r-obs",
        workflow_run_id="w-obs", trace_id="tc-obs",
        director_profile_id="fake-director", writer_profile_id="fake-writer",
        turn_kind="first",
    )
    _close_db(db)
    return result[2]


def test_engine_records_step_timings(tmp_path):
    """每步耗时必须回填到 diag.step_timings_ms，不得为空 dict。"""
    diag = _run_engine(tmp_path)
    timings = diag["step_timings_ms"]
    assert isinstance(timings, dict)
    assert len(timings) > 0, "step_timings_ms 不能为空——observer execution_trace 时间线会缺耗时"
    # 至少 director / writer 两步要有记录
    assert "director" in timings or any("director" in k for k in timings)
    assert "writer" in timings or any("writer" in k for k in timings)
    # 耗时是非负整数
    for v in timings.values():
        assert isinstance(v, int) and v >= 0


def test_engine_records_agent_dispositions(tmp_path):
    """触发的 sub-agent 必须回填到 diag.agent_dispositions（role→summary 映射）。"""
    diag = _run_engine(tmp_path)
    dispositions = diag["agent_dispositions"]
    assert isinstance(dispositions, dict)
    # fake director 会触发规则型 sub-agent；至少应记录被触发的 agent
    # 即使本轮无触发，也要是非空结构化的记录（记录"无触发"也算）
    assert dispositions != {} or diag["steps_completed"] == [], (
        "agent_dispositions 应记录本轮 sub-agent 调度结果，即使是空调度也要有结构化记录"
    )


def test_engine_records_agent_dispositions_when_triggered(monkeypatch, tmp_path):
    """当 sub-agent 真正触发时，agent_dispositions 必须是 role→summary 映射。"""
    from awp_rp_runtime_v2.runtime import persistent_turn_engine as engine_module
    from awp_rp_runtime_v2.contracts.agent_suggestion import (
        AgentSuggestion, SuggestionKind,
    )

    fake_suggestions = [
        AgentSuggestion(role="d1_history_recall", summary="召回上轮情绪线索",
                        kind=SuggestionKind.HISTORICAL_CONFLICT),
        AgentSuggestion(role="d2_opportunity", summary="发现对话推进机会",
                        kind=SuggestionKind.NARRATIVE_OPPORTUNITY),
    ]

    def _stub_triggers(self, snapshot, director_plan, binding, turn_id, trace_id,
                       requested_agents=None):
        return (
            list(fake_suggestions),
            ["d1_history_recall", "d2_opportunity"],
            [{"agent": "d1_history_recall", "should_trigger": True}],
        )

    monkeypatch.setattr(
        engine_module.PersistentTurnEngine, "_run_sub_agent_triggers", _stub_triggers,
    )

    diag = _run_engine(tmp_path)
    dispositions = diag["agent_dispositions"]
    assert dispositions == {
        "d1_history_recall": "召回上轮情绪线索",
        "d2_opportunity": "发现对话推进机会",
    }


def test_engine_records_memory_curation_reason(tmp_path):
    """记忆治理原因必须回填到 diag.memory_curation_reason，不得为空字符串。"""
    diag = _run_engine(tmp_path)
    assert diag["memory_curation_status"], "前置：本轮应有 memory_curation_status"
    reason = diag["memory_curation_reason"]
    assert isinstance(reason, str)
    assert reason.strip(), (
        f"memory_curation_reason 不能为空——observer memory 观察会缺原因（status={diag['memory_curation_status']!r}）"
    )
