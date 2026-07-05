from types import SimpleNamespace

from awp_rp_runtime_v2.contracts.round_snapshot import RoundSnapshot
from awp_rp_runtime_v2.runtime.sub_agent_llm_runner import _execute_tool, run_sub_agent_llm


def test_character_profile_lookup_returns_profile():
    snapshot = RoundSnapshot(
        player_input="continue",
        card_profile_context={
            "name": "SUBAGENT_PROFILE_NAME",
            "description": "SUBAGENT_PROFILE_DESCRIPTION",
            "personality": "SUBAGENT_PROFILE_PERSONALITY",
        },
    )

    result = _execute_tool("character_profile_lookup", {}, snapshot)

    assert "SUBAGENT_PROFILE_NAME" in result
    assert "SUBAGENT_PROFILE_DESCRIPTION" in result
    assert "SUBAGENT_PROFILE_PERSONALITY" in result


def test_accepted_turn_lookup_returns_chronological_history():
    snapshot = RoundSnapshot(
        player_input="continue",
        recent_turn_records=[
            SimpleNamespace(turn_index=4, player_input="p4", writer_output="w4"),
            SimpleNamespace(turn_index=3, player_input="p3", writer_output="w3"),
            SimpleNamespace(turn_index=2, player_input="p2", writer_output="w2"),
        ],
    )

    result = _execute_tool("accepted_turn_lookup", {"limit": 5}, snapshot)

    assert result.index("Turn 2 Player") < result.index("Turn 3 Player")
    assert result.index("Turn 3 Player") < result.index("Turn 4 Player")


def test_accepted_turn_lookup_respects_limit():
    snapshot = RoundSnapshot(
        player_input="continue",
        recent_turn_records=[
            SimpleNamespace(turn_index=4, player_input="p4", writer_output="w4"),
            SimpleNamespace(turn_index=3, player_input="p3", writer_output="w3"),
            SimpleNamespace(turn_index=2, player_input="p2", writer_output="w2"),
        ],
    )

    result = _execute_tool("accepted_turn_lookup", {"limit": 2}, snapshot)

    # limit=2 returns the 2 most recent turns (3 and 4)
    assert "Turn 3 Player" in result
    assert "Turn 4 Player" in result
    assert "Turn 2" not in result


def test_scene_context_lookup_returns_scene():
    snapshot = RoundSnapshot(
        player_input="hello",
        card_state=SimpleNamespace(
            scene_state=SimpleNamespace(
                location="kitchen",
                time_of_day="evening",
                weather="clear",
                active_npcs=["Zhou Yuqing"],
            )
        ),
    )

    result = _execute_tool("scene_context_lookup", {}, snapshot)

    assert "kitchen" in result
    assert "evening" in result
    assert "Zhou Yuqing" in result


def test_worldbook_lookup_filters_by_keyword():
    snapshot = RoundSnapshot(
        player_input="hello",
        active_worldbook_entries=[
            {"title": "Character A", "content": "Details about A"},
            {"title": "Location B", "content": "Details about B"},
            {"title": "Character C", "content": "Something about C"},
        ],
    )

    result = _execute_tool("worldbook_lookup", {"keyword": "Character"}, snapshot)

    assert "Character A" in result
    assert "Character C" in result
    assert "Location B" not in result


def test_active_memory_lookup_returns_memories():
    snapshot = RoundSnapshot(
        player_input="hello",
        active_memories=[
            {"kind": "promise", "summary": "A promise was made"},
            {"kind": "secret", "summary": "A secret is hidden"},
        ],
    )

    result = _execute_tool("active_memory_lookup", {}, snapshot)

    assert "A promise was made" in result
    assert "A secret is hidden" in result
    assert "[promise]" in result


def test_run_sub_agent_llm_uses_tool_allowlist_for_agent_loop():
    snapshot = RoundSnapshot(
        player_input="continue",
        recent_turn_records=[
            SimpleNamespace(turn_index=1, player_input="p1", writer_output="w1"),
        ],
    )

    class MockMessage:
        content = "tool path"
        tool_calls = None

    class MockAdapter:
        def __init__(self):
            self.tool_names = []
            self.generate_called = False

        def call_with_tools(self, messages, tools, **kwargs):
            self.tool_names = [tool["function"]["name"] for tool in tools]
            return MockMessage(), SimpleNamespace(total_tokens=0)

        def generate_text(self, prompt, **kwargs):
            self.generate_called = True
            return "fallback path", SimpleNamespace(success=True)

    adapter = MockAdapter()

    text = run_sub_agent_llm(
        "opportunity",
        snapshot,
        adapter,
        tool_allowlist=["accepted_turn_lookup", "worldbook_lookup"],
    )

    assert text == "tool path"
    assert adapter.generate_called is False
    assert adapter.tool_names == ["accepted_turn_lookup", "worldbook_lookup"]


def test_run_sub_agent_llm_includes_director_task_purpose():
    snapshot = RoundSnapshot(player_input="continue")

    class MockMessage:
        content = "purpose path"
        tool_calls = None

    class MockAdapter:
        def __init__(self):
            self.messages = []

        def call_with_tools(self, messages, tools, **kwargs):
            self.messages = messages
            return MockMessage(), SimpleNamespace(total_tokens=0)

    adapter = MockAdapter()

    run_sub_agent_llm(
        "history_recall",
        snapshot,
        adapter,
        task_purpose="Director's goal: preserve the old promise.",
    )

    rendered = "\n".join(str(message.get("content", "")) for message in adapter.messages)
    assert "Director's goal: preserve the old promise." in rendered


def test_run_sub_agent_llm_does_not_preload_disallowed_tools():
    snapshot = RoundSnapshot(
        player_input="continue",
        active_memories=[{"kind": "secret", "summary": "DISALLOWED_MEMORY"}],
    )

    class MockMessage:
        content = "bounded path"
        tool_calls = None

    class MockAdapter:
        def __init__(self):
            self.messages = []

        def call_with_tools(self, messages, tools, **kwargs):
            self.messages = messages
            return MockMessage(), SimpleNamespace(total_tokens=0)

    adapter = MockAdapter()

    run_sub_agent_llm(
        "opportunity",
        snapshot,
        adapter,
        tool_allowlist=["scene_context_lookup"],
    )

    rendered = "\n".join(str(message.get("content", "")) for message in adapter.messages)
    assert "DISALLOWED_MEMORY" not in rendered


def test_run_sub_agent_llm_rejects_disallowed_tool_calls():
    snapshot = RoundSnapshot(
        player_input="continue",
        active_memories=[{"kind": "secret", "summary": "DISALLOWED_MEMORY"}],
    )

    class Function:
        name = "active_memory_lookup"
        arguments = "{}"

    class ToolCall:
        id = "tc_1"
        function = Function()

    class FirstMessage:
        content = ""
        tool_calls = [ToolCall()]

    class FinalMessage:
        content = "bounded final"
        tool_calls = None

    class MockAdapter:
        def __init__(self):
            self.calls = 0
            self.messages = []

        def call_with_tools(self, messages, tools, **kwargs):
            self.calls += 1
            self.messages = messages
            if self.calls == 1:
                return FirstMessage(), SimpleNamespace(total_tokens=0)
            return FinalMessage(), SimpleNamespace(total_tokens=0)

    adapter = MockAdapter()

    text = run_sub_agent_llm(
        "opportunity",
        snapshot,
        adapter,
        tool_allowlist=["scene_context_lookup"],
    )

    rendered = "\n".join(str(message.get("content", "")) for message in adapter.messages)
    assert text == "bounded final"
    assert "DISALLOWED_MEMORY" not in rendered
    assert "not allowed" in rendered


def _capture_messages(snapshot, role="opportunity", **kwargs):
    """Run a sub-agent with a capturing adapter; return (system_content, user_content)."""
    class MockMessage:
        content = "ok"
        tool_calls = None

    class CapturingAdapter:
        def __init__(self):
            self.messages = []

        def call_with_tools(self, messages, tools, **kw):
            self.messages = messages
            return MockMessage(), SimpleNamespace(total_tokens=0)

    adapter = CapturingAdapter()
    run_sub_agent_llm(role, snapshot, adapter, **kwargs)
    sys_msg = next((m for m in adapter.messages if m.get("role") == "system"), {})
    usr_msg = next((m for m in adapter.messages if m.get("role") == "user"), {})
    return str(sys_msg.get("content", "")), str(usr_msg.get("content", ""))


def test_sub_agent_system_prompt_is_chinese_and_requests_chinese_output():
    """子代理 system prompt 必须是中文，并显式要求用中文输出（解决英文输出问题）。"""
    snapshot = RoundSnapshot(player_input="玩家输入XYZ")
    system_content, _ = _capture_messages(snapshot)

    assert "用中文" in system_content
    # 角色指令示例已是中文，system 主体也应中文化
    assert "子代理" in system_content or "建议子代理" in system_content


def test_sub_agent_player_input_not_in_system_prompt():
    """player_input 不得出现在 system prompt 中（会导致每轮 system 变化、前缀缓存全失效）。

    这是 flash 缓存未命中爆炸的根因：player_input 每轮必变，若拼在 system
    末尾，则跨轮次 system 前缀永远对不齐 → prompt_cache_hit=0。
    """
    snapshot = RoundSnapshot(player_input="UNIQUE_PLAYER_INPUT_MARKER")
    system_content, user_content = _capture_messages(snapshot)

    assert "UNIQUE_PLAYER_INPUT_MARKER" not in system_content
    # 但仍需传给模型（移到 user）
    assert "UNIQUE_PLAYER_INPUT_MARKER" in user_content


def test_sub_agent_director_task_not_in_system_prompt():
    """Director task（每轮变化）不得出现在 system prompt 中，应移到 user 的易变区。"""
    snapshot = RoundSnapshot(player_input="继续")
    system_content, user_content = _capture_messages(
        snapshot, task_purpose="UNIQUE_DIRECTOR_TASK_MARKER"
    )

    assert "UNIQUE_DIRECTOR_TASK_MARKER" not in system_content
    assert "UNIQUE_DIRECTOR_TASK_MARKER" in user_content


def test_sub_agent_stable_prefix_precedes_volatile_in_user():
    """user 内稳定内容（pre_results）应在前，易变内容（player_input）应在后，
    使跨轮次请求保留可命中的稳定前缀。"""
    snapshot = RoundSnapshot(
        player_input="VOLATILE_PLAYER_INPUT",
        active_memories=[
            {"kind": "promise", "summary": "STABLE_MEMORY_CONTENT"},
        ],
    )
    _, user_content = _capture_messages(snapshot, tool_allowlist=["active_memory_lookup"])

    stable_pos = user_content.find("STABLE_MEMORY_CONTENT")
    volatile_pos = user_content.find("VOLATILE_PLAYER_INPUT")
    assert stable_pos != -1, "稳定记忆内容应出现在 user 中"
    assert volatile_pos != -1, "player_input 应出现在 user 中"
    assert stable_pos < volatile_pos, "稳定内容必须排在易变内容之前"


def test_sub_agent_returns_raw_tool_results_not_llm_summary():
    """子代理调工具后，产出应该是 tool results 的原始内容，而不是 LLM 的建议摘要。

    改动前：run_sub_agent_llm 返回 LLM 的 final content（压缩建议）。
    改动后：run_sub_agent_llm 返回所有 tool results 的原始内容。
    """
    TOOL_RESULT_TEXT = "MEMORY_RAW: 周语晴答应给公公买蛤蜊油治手裂"

    class ToolCallMessage:
        """LLM 第一轮决定调工具。"""
        content = ""
        tool_calls = [SimpleNamespace(
            id="tc_1",
            function=SimpleNamespace(
                name="active_memory_lookup",
                arguments="{}",
            ),
        )]

    class FinalMessage:
        """LLM 第二轮不再调工具，返回建议文本（应该被忽略）。"""
        content = "建议：让周语晴提起蛤蜊油的事"
        tool_calls = None

    class MockAdapter:
        def __init__(self):
            self.call_count = 0

        def call_with_tools(self, messages, tools, **kwargs):
            self.call_count += 1
            if self.call_count == 1:
                return ToolCallMessage(), SimpleNamespace(total_tokens=0)
            return FinalMessage(), SimpleNamespace(total_tokens=0)

    snapshot = RoundSnapshot(
        player_input="continue",
        active_memories=[{"kind": "promise", "summary": "周语晴答应给公公买蛤蜊油治手裂"}],
    )
    adapter = MockAdapter()

    # Mock _execute_tool to return known content
    from awp_rp_runtime_v2.runtime import sub_agent_llm_runner as runner_module
    original_execute_tool = runner_module._execute_tool
    runner_module._execute_tool = lambda name, args, snap: TOOL_RESULT_TEXT

    try:
        result = run_sub_agent_llm(
            "opportunity",
            snapshot,
            adapter,
            tool_allowlist=["active_memory_lookup"],
        )

        # 产出应该包含 tool result 的原始内容
        assert TOOL_RESULT_TEXT in result, (
            f"子代理产出应包含 tool result 原始内容，实际产出: {result[:200]}"
        )
        # 产出不应该包含 LLM 的建议文本
        assert "建议" not in result or TOOL_RESULT_TEXT in result, (
            "子代理产出不应是 LLM 的压缩建议，应是原始 tool results"
        )
    finally:
        runner_module._execute_tool = original_execute_tool
