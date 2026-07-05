"""LLM-driven analysis for triggered D1-D5 sub-agents.

Each sub-agent is a real agent: it receives a task from the Director,
uses tool calling to look up data from the snapshot, and produces
analysis based on what it actually retrieved.
"""

from __future__ import annotations

import json
from typing import Any

from ..adapters.llm.deepseek_adapter import DeepSeekAdapter


_FLASH_MODEL = "deepseek-v4-flash"
_EXTRA_DISABLE_THINKING = {"thinking": {"type": "disabled"}}
_MAX_TOOL_ROUNDS = 2


# ── Tool schemas (OpenAI function calling format) ──────────────────────

TOOL_ACCEPTED_TURN_LOOKUP = {
    "type": "function",
    "function": {
        "name": "accepted_turn_lookup",
        "description": "Read recent accepted player/writer turns. Returns full text of each turn.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max number of recent turns to return (default 5).",
                }
            },
        },
    },
}

TOOL_ACTIVE_MEMORY_LOOKUP = {
    "type": "function",
    "function": {
        "name": "active_memory_lookup",
        "description": "Read active high-priority memories (promises, secrets, relationship shifts).",
        "parameters": {"type": "object", "properties": {}},
    },
}

TOOL_RAG_MEMORY_LOOKUP = {
    "type": "function",
    "function": {
        "name": "rag_memory_lookup",
        "description": "Read recalled long-term memory snippets relevant to this turn.",
        "parameters": {"type": "object", "properties": {}},
    },
}

TOOL_WORLDBOOK_LOOKUP = {
    "type": "function",
    "function": {
        "name": "worldbook_lookup",
        "description": "Read active worldbook entries (character lore, settings, rules).",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Optional keyword to filter entries (e.g. character name, location).",
                }
            },
        },
    },
}

TOOL_SCENE_CONTEXT_LOOKUP = {
    "type": "function",
    "function": {
        "name": "scene_context_lookup",
        "description": "Read current scene: location, time of day, weather, active NPCs.",
        "parameters": {"type": "object", "properties": {}},
    },
}

TOOL_CHARACTER_PROFILE_LOOKUP = {
    "type": "function",
    "function": {
        "name": "character_profile_lookup",
        "description": "Read immutable character profile (name, description, personality, scenario).",
        "parameters": {"type": "object", "properties": {}},
    },
}

TOOL_RELATIONSHIP_CONTEXT_LOOKUP = {
    "type": "function",
    "function": {
        "name": "relationship_context_lookup",
        "description": "Read relationship and emotion cues from memories and recent turns.",
        "parameters": {"type": "object", "properties": {}},
    },
}

TOOL_MEMORY_RAG_LOOKUP = {
    "type": "function",
    "function": {
        "name": "memory_rag_lookup",
        "description": "Search long-term memories by keyword. Use for finding old promises, secrets, events, and facts that might be relevant to the current turn.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords to search for in memories (e.g. '蛤蜊油 手裂' or '承诺 镇上').",
                }
            },
            "required": ["query"],
        },
    },
}

# All available tools indexed by name
_ALL_TOOLS: dict[str, dict] = {
    "accepted_turn_lookup": TOOL_ACCEPTED_TURN_LOOKUP,
    "active_memory_lookup": TOOL_ACTIVE_MEMORY_LOOKUP,
    "rag_memory_lookup": TOOL_RAG_MEMORY_LOOKUP,
    "worldbook_lookup": TOOL_WORLDBOOK_LOOKUP,
    "scene_context_lookup": TOOL_SCENE_CONTEXT_LOOKUP,
    "character_profile_lookup": TOOL_CHARACTER_PROFILE_LOOKUP,
    "relationship_context_lookup": TOOL_RELATIONSHIP_CONTEXT_LOOKUP,
    "memory_rag_lookup": TOOL_MEMORY_RAG_LOOKUP,
}

# Role → allowed tool names (Director's tool_allowlist maps here)
_ROLE_DEFAULT_TOOLS: dict[str, list[str]] = {
    "history_recall": [
        "accepted_turn_lookup", "active_memory_lookup", "memory_rag_lookup",
        "scene_context_lookup",
    ],
    "opportunity": [
        "accepted_turn_lookup", "active_memory_lookup", "memory_rag_lookup",
        "worldbook_lookup", "scene_context_lookup",
    ],
    "world_life": [
        "worldbook_lookup", "scene_context_lookup",
    ],
    "emotion_relationship": [
        "accepted_turn_lookup", "active_memory_lookup",
        "scene_context_lookup", "relationship_context_lookup",
    ],
    "continuity": [
        "accepted_turn_lookup", "active_memory_lookup", "memory_rag_lookup",
        "worldbook_lookup", "scene_context_lookup",
    ],
}


# ── Tool execution ─────────────────────────────────────────────────────

def _safe(text: Any, max_len: int | None = None) -> str:
    value = str(text or "")
    if max_len is None:
        return value
    return value[:max_len]


def _format_card_profile(profile: dict[str, Any]) -> str:
    if not isinstance(profile, dict) or not profile:
        return ""
    fields = (
        ("name", "Name"),
        ("description", "Description"),
        ("personality", "Personality"),
        ("scenario", "Scenario"),
        ("mes_example", "Example messages"),
        ("creator_notes", "Creator notes"),
    )
    lines: list[str] = []
    for key, label in fields:
        value = _safe(profile.get(key, ""))
        if value.strip():
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def _chronological_turns(turns: list[Any]) -> list[Any]:
    def key(turn: Any) -> tuple[int, str]:
        raw_index = getattr(turn, "turn_index", 0)
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            index = 0
        return (index, str(getattr(turn, "turn_id", "") or ""))

    return sorted(turns, key=key)


def _execute_tool(name: str, arguments: dict[str, Any], snapshot: Any) -> str:
    """Execute a read-only tool against the snapshot. Returns text result."""
    if name == "accepted_turn_lookup":
        limit = int(arguments.get("limit", 5) or 5)
        recent = getattr(snapshot, "recent_turn_records", []) or []
        lines: list[str] = []
        for turn in _chronological_turns(recent[:limit]):
            idx = _safe(getattr(turn, "turn_index", "?"))
            player = _safe(getattr(turn, "player_input", ""))
            writer = _safe(getattr(turn, "writer_output", ""))
            lines.append(f"Turn {idx} Player: {player}")
            lines.append(f"Turn {idx} Writer: {writer}")
        return "\n".join(lines) if lines else "(no turns)"

    if name == "active_memory_lookup":
        memories = getattr(snapshot, "active_memories", []) or []
        lines = []
        for mem in memories:
            if isinstance(mem, dict):
                summary = _safe(mem.get("summary", "") or mem.get("content", ""))
                kind = _safe(mem.get("kind", ""))
                if summary:
                    lines.append(f"- [{kind}] {summary}")
        return "\n".join(lines) if lines else "(no active memories)"

    if name == "rag_memory_lookup":
        rag = getattr(snapshot, "rag_recall", []) or []
        lines = []
        for item in rag:
            if isinstance(item, dict):
                summary = _safe(item.get("summary", "") or item.get("content", ""))
                if summary:
                    lines.append(f"- {summary}")
        return "\n".join(lines) if lines else "(no RAG memories)"

    if name == "worldbook_lookup":
        keyword = str(arguments.get("keyword", "") or "").strip().lower()
        worldbook = getattr(snapshot, "active_worldbook_entries", []) or []
        lines = []
        for entry in worldbook:
            if not isinstance(entry, dict):
                continue
            title = _safe(entry.get("title", "") or entry.get("entry_id", ""))
            content = _safe(entry.get("content_excerpt", "") or entry.get("content", ""))
            if not title:
                continue
            # Filter by keyword if provided
            if keyword and keyword not in title.lower() and keyword not in content.lower():
                continue
            lines.append(f"- {title}: {content}")
        return "\n".join(lines) if lines else "(no matching worldbook entries)"

    if name == "scene_context_lookup":
        cs = getattr(snapshot, "card_state", None)
        scene = getattr(cs, "scene_state", None) if cs else None
        location = _safe(getattr(scene, "location", "") if scene else "")
        time_of_day = _safe(getattr(scene, "time_of_day", "") if scene else "")
        weather = _safe(getattr(scene, "weather", "") if scene else "")
        active_npcs = list(getattr(scene, "active_npcs", []) if scene else [])
        npc_str = ", ".join(str(n) for n in active_npcs) if active_npcs else "(none)"
        return (
            f"Scene: {location} | Time: {time_of_day} | Weather: {weather}\n"
            f"Active NPCs: {npc_str}"
        )

    if name == "character_profile_lookup":
        profile = getattr(snapshot, "card_profile_context", {}) or {}
        return _format_card_profile(profile) or "(no profile)"

    if name == "relationship_context_lookup":
        # Combine relationship info from memories + recent turns
        memories = getattr(snapshot, "active_memories", []) or []
        lines = []
        for mem in memories:
            if isinstance(mem, dict):
                kind = _safe(mem.get("kind", ""))
                if kind in ("relationship", "secret", "promise"):
                    summary = _safe(mem.get("summary", "") or mem.get("content", ""))
                    if summary:
                        lines.append(f"- [{kind}] {summary}")
        return "\n".join(lines) if lines else "(no relationship cues)"

    if name == "memory_rag_lookup":
        query = str(arguments.get("query", "") or "").strip()
        if not query:
            return "(no query provided)"
        # Search through RAG recall and active memories by keyword overlap
        query_keywords = [kw for kw in query.lower().split() if len(kw) >= 2]
        if not query_keywords:
            return "(query too short)"
        results: list[str] = []

        # Search RAG recall
        rag = getattr(snapshot, "rag_recall", []) or []
        for item in rag:
            if not isinstance(item, dict):
                continue
            content = _safe(item.get("content", "") or item.get("summary", ""))
            combined = content.lower()
            if any(kw in combined for kw in query_keywords):
                results.append(f"[RAG] {content[:300]}")

        # Search active memories
        memories = getattr(snapshot, "active_memories", []) or []
        for mem in memories:
            if not isinstance(mem, dict):
                continue
            summary = _safe(mem.get("summary", "") or mem.get("content", ""))
            combined = summary.lower()
            if any(kw in combined for kw in query_keywords):
                kind = _safe(mem.get("kind", ""))
                results.append(f"[active:{kind}] {summary[:300]}")

        return "\n".join(results[:5]) if results else f"(no memories matching '{query}')"

    return f"(unknown tool: {name})"


# ── System prompt ──────────────────────────────────────────────────────

_SYSTEM_PROMPT = """你是一个互动角色扮演运行时的创意建议子代理。
你的建议会被下游的写作代理（Writer）消费。你绝不写玩家可见的正文。

你的职责是给 Writer 提供它自己未必能想到的角度、点子和细节。
你是一个创意变量——不是检查者，也不是分析师。

=== 语言要求 ===
始终用中文输出你的所有分析、建议和证据。

=== 工具使用规则 ===
1. 在写建议前先调用工具收集证据。不要臆测。
2. 每回合最多调用 2-3 个工具。聚焦，不要穷举。
3. 当工具返回 "(none)" 或空时，这是有效的——记录下来并继续。
4. 收集证据后再写建议。写完建议后不要再调用工具。

=== 输出格式 ===
返回 1-3 条建议，严格使用以下结构（纯文本，不要 JSON）：

[SUGGESTION_1]
kind: 取值之一 (callback, opportunity, world_event, emotion, continuity_issue)
suggestion: 一句具体的话，说明 Writer 应该考虑写什么。
evidence: 来自工具结果的具体事实，用于支撑该建议。
[/SUGGESTION_1]

[SUGGESTION_2]
kind: ...
suggestion: ...
evidence: ...
[/SUGGESTION_2]

至少返回 1 条建议。如果没找到有用信息，返回一条 kind=opportunity 的建议，
说明场景稳定，Writer 应自然延续。

=== 规则 ===
- 不要编造工具结果中不存在的事实。
- 不要修改 CardState、记忆、文件、网络或数据库记录。
- 不要委托给其他代理。
- 不要写玩家可见的叙事、对话或正文。
- 每条建议都必须可操作——Writer 应知道如何使用它。"""


def _role_instruction(role: str) -> str:
    instructions = {
        "history_recall": (
            "目标：找出可以被重新唤起的旧情节线——被遗忘的承诺、未解的张力、提到却未再提及的物件、悬而未决的对话。\n"
            "工具顺序：1) accepted_turn_lookup(limit=3) 查近期历史，"
            "2) active_memory_lookup 查承诺/秘密，"
            "3) memory_rag_lookup 查旧事实。\n"
            "产出：回调建议——Writer 可以引用的具体旧时刻。\n"
            "示例：kind=callback, suggestion='让周语晴提起她答应要买的蛤蜊油，表现出她记挂着、在意着', "
            "evidence='Turn 1: 她主动说要给他买来治手裂'"
        ),
        "opportunity": (
            "目标：找出戏剧机会——接下来可能发生什么出乎意料但合理的事？\n"
            "工具顺序：1) scene_context_lookup 查当前场景，"
            "2) worldbook_lookup 查叙事钩子，"
            "3) active_memory_lookup 查情感张力。\n"
            "产出：机会卡片——Writer 可以采取的具体剧情方向。\n"
            "示例：kind=opportunity, suggestion='一个邻居注意到周语晴身子的变化，在村里水井边窃窃私语，"
            "引入外部压力', evidence='worldbook: 打谷场是公共闲话中心，刘屠户爱管闲事'"
        ),
        "world_life": (
            "目标：主角视线之外的世界正在发生什么？环境、NPC 或天气能为场景贡献什么？\n"
            "工具顺序：1) scene_context_lookup 查当前地点/时间，"
            "2) worldbook_lookup 查环境与 NPC 细节。\n"
            "产出：world_event 建议——发生在角色周围、Writer 可作为背景质感提及的事。\n"
            "示例：kind=world_event, suggestion='大黄在门口挠门想出去——一个自然的打断，"
            "打破紧张', evidence='worldbook: 大黄是家里的狗，是令人安心的存在'"
        ),
        "emotion_relationship": (
            "目标：角色在感受什么但没说出口？哪些微动作透露了他们的内心——一个眼神、一次停顿、一个小动作、一种克制？\n"
            "工具顺序：1) active_memory_lookup 查关系记忆，"
            "2) accepted_turn_lookup(limit=2) 查近期情感节拍，"
            "3) relationship_context_lookup 查关系线索。\n"
            "产出：情绪建议——给 Writer 的具体身体/情感细节。\n"
            "示例：kind=emotion, suggestion='听到 检查 这个词时，周语晴的手不自觉地抚上小腹——"
            "她也在期待却不敢抱希望', evidence='memory: 上个月她买了验孕棒，结果落空了'"
        ),
        "continuity": (
            "目标：故事里有没有矛盾？名字错误、不可能的位置、时间线缺口、知识边界违规？\n"
            "工具顺序：1) accepted_turn_lookup(limit=3) 查近期事实，"
            "2) worldbook_lookup 查既定设定，"
            "3) active_memory_lookup 查承诺与约束。\n"
            "产出：continuity_issue 建议——带证据的具体问题。\n"
            "示例：kind=continuity_issue, suggestion='Turn 2 说周语晴在厨房，"
            "但 Turn 3 她在门口——需要一个过渡', "
            "evidence='Turn 2 writer: 厨房里传来哗哗的水声; Turn 3 writer: 她从厨房门框里探出半个身子'"
        ),
    }
    return instructions.get(role, f"请从 {role} 视角提供创意建议。")


# ── Structured output parser ──────────────────────────────────────────

import re as _re


def parse_sub_agent_output(text: str) -> list[dict[str, str]]:
    """Parse structured sub-agent output into suggestion dicts.

    Returns a list of dicts with keys: kind, suggestion, evidence.
    Falls back to a single suggestion if parsing fails.
    """
    if not text or not text.strip():
        return []

    # Try to parse structured blocks
    pattern = _re.compile(
        r'\[SUGGESTION_\d+\]\s*\n'
        r'kind:\s*(.+?)\s*\n'
        r'suggestion:\s*(.+?)\s*\n'
        r'evidence:\s*(.+?)\s*\n'
        r'\[/SUGGESTION_\d+\]',
        _re.DOTALL,
    )
    matches = pattern.findall(text)

    if matches:
        results = []
        for kind, suggestion, evidence in matches:
            results.append({
                "kind": kind.strip().lower().replace(" ", "_"),
                "suggestion": suggestion.strip(),
                "evidence": evidence.strip(),
            })
        return results

    # Fallback: try line-based parsing for [SUGGESTION_1] without closing tags
    block_pattern = _re.compile(
        r'\[SUGGESTION_\d+\]\s*\n(.*?)(?=\[SUGGESTION_\d+\]|\Z)',
        _re.DOTALL,
    )
    blocks = block_pattern.findall(text)
    if blocks:
        results = []
        for block in blocks:
            kind_match = _re.search(r'kind:\s*(.+)', block)
            sug_match = _re.search(r'suggestion:\s*(.+)', block)
            ev_match = _re.search(r'evidence:\s*(.+)', block)
            if sug_match:
                results.append({
                    "kind": (kind_match.group(1).strip().lower().replace(" ", "_") if kind_match else "opportunity"),
                    "suggestion": sug_match.group(1).strip(),
                    "evidence": (ev_match.group(1).strip() if ev_match else ""),
                })
        if results:
            return results

    # Final fallback: treat the whole text as one suggestion
    # Try to extract a summary from the first meaningful line
    lines = [l.strip() for l in text.strip().split("\n") if l.strip() and not l.strip().startswith("[")]
    summary = lines[0][:200] if lines else text[:200]

    # Guess kind from content
    text_lower = text.lower()
    if any(kw in text_lower for kw in ["contradiction", "conflict", "mismatch", "impossible"]):
        kind = "continuity_issue"
    elif any(kw in text_lower for kw in ["callback", "recall", "promise", "forgotten"]):
        kind = "callback"
    elif any(kw in text_lower for kw in ["emotion", "feel", "tension", "vulnerab"]):
        kind = "emotion"
    elif any(kw in text_lower for kw in ["world", "environment", "npc", "sound", "smell"]):
        kind = "world_event"
    else:
        kind = "opportunity"

    return [{
        "kind": kind,
        "suggestion": summary,
        "evidence": "",
    }]


# ── Pre-populate most relevant tools per role ─────────────────────────

# Each role gets 1-2 pre-loaded tool results to minimize LLM calls.
_ROLE_PRELOAD: dict[str, list[tuple[str, dict]]] = {
    "history_recall": [
        ("accepted_turn_lookup", {"limit": 3}),
        ("active_memory_lookup", {}),
    ],
    "opportunity": [
        ("scene_context_lookup", {}),
        ("active_memory_lookup", {}),
    ],
    "world_life": [
        ("scene_context_lookup", {}),
        ("worldbook_lookup", {}),  # Get all worldbook entries for environmental details
    ],
    "emotion_relationship": [
        ("active_memory_lookup", {}),
        ("accepted_turn_lookup", {"limit": 2}),
    ],
    "continuity": [
        ("accepted_turn_lookup", {"limit": 3}),
    ],
}


# ── 子代理输出策略 ─────────────────────────────────────────────────
# 完整信息类：直接传原始 tool results，零损失。
# 可精简类：LLM 把 tool results 精炼成关键事实摘要。
_FULL_INFO_ROLES: set[str] = {"history_recall", "opportunity"}
_ROLE_OUTPUT_TOKEN_LIMITS: dict[str, int] = {
    "history_recall": 3000,
    "opportunity": 3000,
    "world_life": 1500,
    "emotion_relationship": 1500,
    "continuity": 1500,
}


def _truncate_to_token_limit(text: str, max_tokens: int) -> str:
    """粗略截断：按字符数估算（1 中文字 ≈ 1.5 token），保留开头，末尾加截断标记。"""
    # 粗略估算：1 个中文字 ≈ 1.5 token，1 个英文单词 ≈ 1 token
    # 保守用 1.3 字符/token 的系数
    max_chars = int(max_tokens * 1.3)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...(截断)"


def _extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
    """Extract meaningful Chinese keywords from text for RAG-style search.

    Splits on punctuation and whitespace, filters short/common words.
    """
    import re
    # Split on punctuation, whitespace, and common separators
    tokens = re.split(r'[\s，。！？、；：“”‘’（）\[\]【】\n\r\t]', text)
    # Filter: length >= 2, not pure numbers, not common stop words
    stop_words = {
        "的", "了", "是", "在", "我", "你", "他", "她", "它", "们",
        "这", "那", "有", "不", "就", "也", "都", "到", "说", "要",
        "和", "与", "或", "但", "而", "把", "被", "让", "给", "对",
        "从", "向", "往", "以", "为", "会", "能", "可以", "可能",
        "一个", "什么", "怎么", "那么", "这么", "没有", "还是",
    }
    keywords = []
    for token in tokens:
        token = token.strip()
        if len(token) >= 2 and not token.isdigit() and token not in stop_words:
            keywords.append(token)
    return keywords[:max_keywords]


def _worldbook_rag(player_input: str, snapshot: Any, top_k: int = 5) -> str:
    """RAG-style worldbook retrieval: extract keywords from player input,
    score entries by keyword overlap, return top-K most relevant entries.
    """
    worldbook = getattr(snapshot, "active_worldbook_entries", []) or []
    if not worldbook:
        return "(no worldbook entries)"

    keywords = _extract_keywords(player_input)
    if not keywords:
        # Fallback: return first few entries truncated
        lines = []
        for entry in worldbook[:top_k]:
            if isinstance(entry, dict):
                title = _safe(entry.get("title", "") or entry.get("entry_id", ""))
                content = _safe(entry.get("content_excerpt", "") or entry.get("content", ""), 200)
                if title:
                    lines.append(f"- {title}: {content}")
        return "\n".join(lines) if lines else "(no worldbook entries)"

    # Score each entry by keyword overlap
    scored: list[tuple[float, dict]] = []
    for entry in worldbook:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title", "") or "").lower()
        content = str(entry.get("content_excerpt", "") or entry.get("content", "") or "").lower()
        combined = title + " " + content
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scored.append((score, entry))

    # Sort by score descending, take top-K
    scored.sort(key=lambda x: -x[0])
    lines = []
    for _score, entry in scored[:top_k]:
        title = _safe(entry.get("title", "") or entry.get("entry_id", ""))
        content = _safe(entry.get("content_excerpt", "") or entry.get("content", ""), 200)
        if title:
            lines.append(f"- {title}: {content}")

    return "\n".join(lines) if lines else "(no matching worldbook entries)"


def _execute_tool_compact(
    name: str, arguments: dict[str, Any], snapshot: Any,
) -> str:
    """Compact version of tool execution for pre-population.

    Returns truncated results — writer output is summarized, not full text.
    The agent can call the full tool via tool calling if it needs more detail.
    """
    if name == "accepted_turn_lookup":
        limit = int(arguments.get("limit", 3) or 3)
        recent = getattr(snapshot, "recent_turn_records", []) or []
        lines: list[str] = []
        for turn in _chronological_turns(recent[:limit]):
            idx = _safe(getattr(turn, "turn_index", "?"))
            player = _safe(getattr(turn, "player_input", ""))
            # Summarize writer output to first 150 chars
            writer = _safe(getattr(turn, "writer_output", ""), 150)
            lines.append(f"Turn {idx} Player: {player}")
            lines.append(f"Turn {idx} Writer (excerpt): {writer}...")
        return "\n".join(lines) if lines else "(no turns)"

    if name == "worldbook_lookup":
        # Use RAG-style retrieval: extract keywords from player input,
        # find most relevant worldbook entries
        player_input = _safe(getattr(snapshot, "player_input", ""))
        return _worldbook_rag(player_input, snapshot, top_k=5)

    # Other tools are already compact
    return _execute_tool(name, arguments, snapshot)


def _pre_populate_tools(
    role: str,
    snapshot: Any,
    allowed_tool_names: set[str] | None = None,
) -> str:
    """Pre-load the most relevant tool results for this role.

    Uses compact/truncated results so the agent can often produce analysis
    in a single call without needing to call tools for more detail.
    """
    preload = _ROLE_PRELOAD.get(role, [])
    if not preload:
        return ""

    parts: list[str] = []
    for tool_name, args in preload:
        if allowed_tool_names is not None and tool_name not in allowed_tool_names:
            continue
        result = _execute_tool_compact(tool_name, args, snapshot)
        parts.append(f"{tool_name}:\n{result}")
    return "\n\n".join(parts)


# ── Agent loop ─────────────────────────────────────────────────────────

def run_sub_agent_llm(
    role: str,
    snapshot: Any,
    adapter: DeepSeekAdapter,
    trace_id: str = "",
    turn_id: str = "",
    attempt_id: str = "",
    allowlist: list[str] | None = None,
    tool_allowlist: list[str] | None = None,
    task_purpose: str = "",
) -> str:
    """Run one sub-agent as a real agent with tool calling.

    The agent receives a task description, calls tools to gather evidence,
    then produces its analysis. It is not a context assembler.
    """
    player_input = _safe(getattr(snapshot, "player_input", ""))

    # Determine which tools this role can use. `allowlist` is retained only
    # for old callers; production callers should pass `tool_allowlist`.
    role_tool_names = _ROLE_DEFAULT_TOOLS.get(role, [])
    explicit_tool_allowlist = tool_allowlist if tool_allowlist is not None else allowlist
    if explicit_tool_allowlist:
        allowed = {t for t in explicit_tool_allowlist if t in _ALL_TOOLS}
        tool_names = [t for t in role_tool_names if t in allowed]
    else:
        tool_names = role_tool_names
    allowed_tool_names = set(tool_names)
    tools = [_ALL_TOOLS[n] for n in tool_names if n in _ALL_TOOLS]

    if not tools:
        # Fallback: no tools available, do a single-shot analysis
        return _fallback_single_shot(role, snapshot, adapter, player_input,
                                     trace_id=trace_id, turn_id=turn_id,
                                     attempt_id=attempt_id)

    # Pre-populate the most relevant tool results so the agent can often
    # produce analysis in a single call without needing to call tools.
    pre_results = _pre_populate_tools(role, snapshot, allowed_tool_names)

    # system prompt 必须保持常量（跨轮次稳定），不能包含 player_input / task_purpose
    # 等每轮变化的内容——否则 DeepSeek 前缀缓存的 system 段每轮都对不齐，
    # 导致 prompt_cache_hit_tokens 始终为 0（即"flash 缓存全未命中"现象）。
    # 易变内容一律放到 user 消息，且稳定前缀（pre_results）在前、易变段在后。
    system_prompt = (
        f"{_SYSTEM_PROMPT}\n\n"
        f"=== YOUR ROLE: {role} ===\n"
        f"{_role_instruction(role)}"
    )

    # user 消息布局：稳定前缀 → 易变轮次包。稳定前缀跨轮次可复用，提升缓存命中。
    stable_prefix = ""
    if pre_results:
        stable_prefix = (
            "=== 预加载工具结果（稳定；跨轮次可复用） ===\n"
            "这些结果已为效率预加载。若证据足够，请直接产出分析。"
            "仅在需要额外数据时才调用工具。\n\n"
            f"{pre_results}\n\n"
        )

    volatile_packet_parts = [f"请作为 {role} 分析本回合。"]
    if _safe(task_purpose):
        volatile_packet_parts.append(
            f"=== 总控任务（易变） ===\n{_safe(task_purpose)}"
        )
    volatile_packet_parts.append(
        f"=== 玩家输入（易变） ===\n{player_input}\n\n"
        "请用中文按上述输出格式产出你的分析。"
    )
    volatile_packet = "\n\n".join(volatile_packet_parts)

    user_content = stable_prefix + "=== 轮次包（易变；每回合变化） ===\n\n" + volatile_packet

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    # 收集所有 tool results 的原始内容，作为子代理的产出。
    # 子代理的角色是"检索者"：用 LLM 思考查什么工具，但不压缩结果，
    # 直接把检索到的原始信息传给 Writer。
    collected_tool_results: list[str] = []
    final_text = ""

    for round_idx in range(_MAX_TOOL_ROUNDS):
        message, _usage = adapter.call_with_tools(
            messages,
            tools=tools,
            model=_FLASH_MODEL,
            max_tokens=500,
            temperature=0.3,
            extra_body=_EXTRA_DISABLE_THINKING,
        )

        if message is None:
            break

        # Collect any text content
        content = getattr(message, "content", None) or ""
        if content:
            final_text = content

        # Check for tool calls
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            # No tool calls → agent is done
            break

        # Append the assistant message (with tool_calls) to history
        messages.append({
            "role": "assistant",
            "content": content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ],
        })

        # Execute each tool call and append results
        for tc in tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                fn_args = {}

            if fn_name not in allowed_tool_names:
                result = f"(tool not allowed: {fn_name})"
            else:
                result = _execute_tool(fn_name, fn_args, snapshot)
            # 收集有效 tool result 原始内容（跳过 not allowed）
            if not result.startswith("(tool not allowed:"):
                collected_tool_results.append(f"[{fn_name}]\n{result}")
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    # ── 产出策略 ─────────────────────────────────────────────────────
    # 完整信息类（history_recall, opportunity）：直接传原始 tool results，零损失。
    # 可精简类（world_life, emotion_relationship, continuity）：让 LLM 把 tool results
    #   精炼成关键事实摘要，Writer 看到的是提炼后的精简信息。
    if role in _FULL_INFO_ROLES:
        # 完整信息类：直接返回 tool results
        if collected_tool_results:
            raw_output = "\n\n".join(collected_tool_results).strip()
            limit = _ROLE_OUTPUT_TOKEN_LIMITS.get(role, 3000)
            return _truncate_to_token_limit(raw_output, limit)
        return final_text.strip()
    else:
        # 可精简类：让 LLM 把检索到的信息提炼成精简摘要
        if collected_tool_results:
            messages.append({
                "role": "user",
                "content": (
                    "你刚才已经检索到了以下信息。请用中文把这些信息提炼成 3-5 条关键事实，"
                    "每条一行，保留对 Writer 最有用的具体细节（人名、地点、情绪、时间、矛盾点）。"
                    "不要写建议，只写事实。\n\n"
                    "=== 检索结果 ===\n"
                    + "\n\n".join(collected_tool_results)
                ),
            })
            message, _usage = adapter.call_with_tools(
                messages,
                tools=tools,
                model=_FLASH_MODEL,
                max_tokens=300,
                temperature=0.3,
                extra_body=_EXTRA_DISABLE_THINKING,
            )
            if message is not None:
                summary = getattr(message, "content", None) or ""
                if summary.strip():
                    return summary.strip()
        return final_text.strip()


def _fallback_single_shot(
    role: str,
    snapshot: Any,
    adapter: DeepSeekAdapter,
    player_input: str,
    trace_id: str = "",
    turn_id: str = "",
    attempt_id: str = "",
) -> str:
    """Fallback when no tools are available — single-shot text generation.

    保持 system（常量）与 user（含 player_input，易变）分离，使前缀缓存仍可命中 system 段。
    """
    system_prompt = (
        f"{_SYSTEM_PROMPT}\n\n"
        f"=== YOUR ROLE: {role} ===\n"
        f"{_role_instruction(role)}"
    )
    user_prompt = (
        "=== 玩家输入（易变） ===\n"
        f"{player_input}\n\n"
        "无工具可用。请仅依据角色指令进行分析。"
        "请用中文按上述输出格式产出你的分析。"
    )
    text, _receipt = adapter.generate_text(
        user_prompt,
        max_tokens=500,
        provider_role=f"sub_agent_{role}",
        model=_FLASH_MODEL,
        extra_body=_EXTRA_DISABLE_THINKING,
        trace_id=trace_id,
        turn_id=turn_id,
        system_prompt=system_prompt,
    )
    return text.strip()
