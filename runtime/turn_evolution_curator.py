"""TurnEvolutionCurator — LLM-driven state evolution + memory curation.

Replaces the deterministic fake state patch (empty operations + revision bump)
with real, evidence-driven state proposals.

The curator is a SINGLE structured LLM call that produces:
  - StateUpdateProposalV2 (patch operations against CardState)
  - Memory candidates (active + RAG)
  - Event summaries
  - Relationship summaries

Cost model: 1 curator call per accepted turn (replaces the fake D6 path).
The curator uses the same provider infrastructure as Director/Writer.

Rules:
  - Runs ONLY after Writer text passes QualityGate
  - Cannot write to any store directly
  - Output is validated through Patch Validator before CardStateCommitRuntime
  - If no legitimate state change → returns is_no_state_change=True
    → revision does NOT increment
  - If patch validation fails → state_update_rejected diagnostics
    → accepted text is preserved, but no state/memory side effects
  - Model cannot write arbitrary CardState paths
  - Model cannot override CardState variable types
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ..contracts.curator_request import CuratorRequest
from ..contracts.turn_evolution_proposal import (
    TurnEvolutionProposal,
    StateUpdateProposalV2,
    MemoryCandidate,
)
from ..contracts.card_state_patch import (
    CardStatePatch, CardStatePatchOperation, PatchOpType,
    validate_patch_operations,
)
from ..contracts.card_state import CardState
from ..contracts.execution_trace import ExecutionTrace, TraceEvent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── Allowed patch operations for the curator ─────────────────────────────
# The curator may only propose these op types. Any other op type is rejected.
CURATOR_ALLOWED_OPS = frozenset({
    "set",             # variables.* — set a value
    "increment",       # variables.* — numeric delta
    "set_flag",        # event_flags.* — mark event as fired
    "set_scene_field", # scene_state.* — update scene property
})


class TurnEvolutionCurator:
    """Produces real state evolution proposals from accepted turn data.

    Uses a structured LLM call (or deterministic fallback for fake profiles)
    to generate TurnEvolutionProposal.
    """

    def __init__(self, llm_adapter: Any = None):
        """Initialize with an optional LLM adapter.

        If llm_adapter is None, uses deterministic fallback (for fake profiles).
        If provided, must implement generate_structured(prompt, schema) -> dict.
        """
        self._llm = llm_adapter

    def curate(
        self,
        request: CuratorRequest,
        trace: ExecutionTrace | None = None,
    ) -> TurnEvolutionProposal:
        """Run curation. Returns a TurnEvolutionProposal.

        This is the main entry point. It:
        1. Builds a structured prompt from the request
        2. Calls LLM (or deterministic fallback)
        3. Parses the response into TurnEvolutionProposal
        4. Validates the state proposal operations against CardState
        5. Returns the validated proposal
        """
        if trace:
            trace.add_event(TraceEvent(
                event_id=f"evt_{uuid.uuid4().hex[:8]}",
                event_type="turn_evolution_curator_start",
                actor="turn_evolution_curator",
                details={"turn_id": request.turn_id, "has_llm": self._llm is not None},
                success=True,
            ))

        if self._llm is not None:
            proposal = self._curate_with_llm(request)
        else:
            proposal = self._curate_deterministic(request)

        # Validate the proposal's state operations
        proposal = self._validate_proposal(proposal, request.pre_turn_card_state)

        if trace:
            trace.add_event(TraceEvent(
                event_id=f"evt_{uuid.uuid4().hex[:8]}",
                event_type="turn_evolution_curator_complete",
                actor="turn_evolution_curator",
                details={
                    "turn_id": request.turn_id,
                    "is_no_state_change": proposal.is_no_state_change,
                    "op_count": len(proposal.state_update_proposal.operations),
                    "active_candidates": len(proposal.memory_candidates_active),
                    "rag_candidates": len(proposal.memory_candidates_rag),
                },
                success=True,
            ))

        return proposal

    # ── LLM-backed curation ─────────────────────────────────────────────

    def _curate_with_llm(self, request: CuratorRequest) -> TurnEvolutionProposal:
        """Run curation with a real LLM adapter.

        Uses generate_text (not generate_structured, which hardcodes Director schema).
        Parses JSON response manually with fallback.
        """
        prompt = self._build_curator_prompt(request)

        try:
            raw = self._llm.generate_text(prompt, provider_role="curator")
            # generate_text returns (text, receipt) tuple
            if isinstance(raw, tuple):
                text = raw[0] if raw[0] else ""
            else:
                text = str(raw)

            # Parse JSON from response (handle markdown code blocks)
            text = text.strip()
            if text.startswith("```"):
                # Remove markdown code block
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            parsed = json.loads(text)
        except Exception as e:
            # LLM failure → no_state_change (fail safe)
            return TurnEvolutionProposal(
                proposal_id=f"tep_{uuid.uuid4().hex[:8]}",
                turn_id=request.turn_id,
                session_id=request.session_id,
                is_no_state_change=True,
                curator_confidence=0.0,
                curator_reasoning=f"LLM call failed: {str(e)[:200]}",
            )

        return self._parse_llm_response(parsed, request)

    def _build_curator_prompt(self, request: CuratorRequest) -> str:
        """Build a structured prompt for the curator LLM call."""
        # Extract key context
        cs = request.pre_turn_card_state
        variables = cs.get("variables", {})
        event_flags = cs.get("event_flags", {})
        scene = cs.get("scene_state", {})
        current_revision = cs.get("revision", 0)

        # Format recent turns
        recent_lines = []
        for tr in request.recent_turns[:5]:
            idx = tr.get("turn_index", "?")
            pi = str(tr.get("player_input", ""))
            wo = str(tr.get("writer_output", ""))
            recent_lines.append(f"[Turn {idx}] Player: {pi}")
            recent_lines.append(f"[Turn {idx}] Writer: {wo}")

        # Format active memory
        mem_lines = []
        for mem in request.active_memory:
            kind = mem.get("kind", "?")
            summary = str(mem.get("summary", "") or mem.get("content", ""))
            mem_lines.append(f"- [{kind}] {summary}")

        # Format worldbook context
        wb_lines = []
        for entry in request.resolved_worldbook_context:
            title = str(entry.get("title", "") or entry.get("entry_id", ""))
            content = str(entry.get("content_excerpt", "") or entry.get("content", ""))
            wb_lines.append(f"- {title}: {content}")

        # Format agent suggestions
        sug_lines = []
        for sug in request.agent_suggestions:
            role = sug.get("role", "?")
            summary = str(sug.get("summary", "") or sug.get("content", ""))
            sug_lines.append(f"- [{role}] {summary}")

        brief = request.final_turn_brief
        turn_goal = str(brief.get("turn_goal", ""))

        prompt = (
            "你是一个角色扮演会话的状态策展器(Curator)。\n"
            "分析已接受的 Writer 输出，判断世界状态发生了什么变化，以及需要保存什么记忆。\n\n"
            "=== 规则 ===\n"
            "- 只提议文本中明确证据支持的状态变化。\n"
            "- 如果没有有意义的变化，返回 is_no_state_change=true。\n"
            "- 不要提议与当前 CardState 矛盾的变化。\n"
            "- operations 中每项必须有 op 和 path 字段。\n"
            "- op 只能是: set, increment, set_flag, set_scene_field\n"
            "- path 格式: variables.KEY, event_flags.KEY, scene_state.FIELD\n"
            "  例如: {\"op\": \"increment\", \"path\": \"variables.trust\", \"value\": 1}\n"
            "- memory_candidates 中 content 必须 30-80 字。\n"
            "- 只保存真正重要的承诺、冲突、秘密、关系变化、目标。\n"
            "- 必须返回 memory_candidates_active 和 memory_candidates_rag；即使没有候选也必须返回空数组。\n"
            "- active 记忆用于未来几轮立即影响角色反应；rag 记忆用于长期检索。\n\n"
            "=== 当前状态 ===\n"
            f"revision: {current_revision}\n"
            f"variables: {json.dumps(variables, ensure_ascii=False)}\n"
            f"event_flags: {json.dumps(event_flags, ensure_ascii=False)}\n"
            f"scene: {json.dumps(scene, ensure_ascii=False)}\n\n"
            "=== 回合目标 ===\n"
            f"{turn_goal}\n\n"
            "=== 最近回合 ===\n"
            + ("\n".join(recent_lines) if recent_lines else "(无)") + "\n\n"
            "=== 玩家输入 ===\n"
            f"{request.player_input}\n\n"
            "=== 已接受 Writer 输出 ===\n"
            f"{request.accepted_writer_output}\n\n"
            "=== 活跃记忆 ===\n"
            + ("\n".join(mem_lines) if mem_lines else "(无)") + "\n\n"
            "=== 世界书上下文 ===\n"
            + ("\n".join(wb_lines) if wb_lines else "(无)") + "\n\n"
            "=== Agent 建议 ===\n"
            + ("\n".join(sug_lines) if sug_lines else "(无)") + "\n\n"
            "用 JSON 回答。如果不需要状态变化，设 is_no_state_change=true。\n"
            "如果需要变化，在 state_update_proposal.operations 中列出。\n"
            "每项 operation 格式: {\"op\": \"...\", \"path\": \"...\", \"value\": ..., \"reason\": \"...\"}\n"
            "必须使用这个顶层结构：\n"
            "{\n"
            "  \"is_no_state_change\": false,\n"
            "  \"state_update_proposal\": {\"operations\": [], \"reasoning_summary\": \"...\"},\n"
            "  \"memory_candidates_active\": [\n"
            "    {\"kind\": \"promise|conflict|secret|relationship|goal\", \"content\": \"30-80字重要记忆\", \"importance\": 0.7, \"entity_refs\": [\"角色名\"], \"tags\": [\"tag\"], \"reason\": \"保存原因\"}\n"
            "  ],\n"
            "  \"memory_candidates_rag\": [\n"
            "    {\"content\": \"适合长期检索的本回合事实摘要\", \"importance\": 0.5, \"tags\": [\"turn\"], \"reason\": \"保存原因\"}\n"
            "  ]\n"
            "}\n"
            "没有对应记忆时，memory_candidates_active 和 memory_candidates_rag 必须是 []。"
        )

        return prompt

    def _build_output_schema(self) -> dict[str, Any]:
        """Build the JSON schema for curator structured output."""
        return {
            "type": "object",
            "required": [
                "is_no_state_change",
                "state_update_proposal",
                "memory_candidates_active",
                "memory_candidates_rag",
                "event_summary",
                "relationship_summary",
            ],
            "properties": {
                "is_no_state_change": {"type": "boolean"},
                "curator_confidence": {"type": "number"},
                "curator_reasoning": {"type": "string"},
                "state_update_proposal": {
                    "type": "object",
                    "properties": {
                        "reasoning_summary": {"type": "string"},
                        "operations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["op", "path"],
                                "properties": {
                                    "op": {
                                        "type": "string",
                                        "enum": ["set", "increment",
                                                 "set_flag", "set_scene_field"],
                                    },
                                    "path": {"type": "string"},
                                    "value": {},
                                    "reason": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "memory_candidates_active": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["kind", "content"],
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": [
                                    "promise", "secret", "conflict",
                                    "relationship_shift", "player_goal",
                                    "scene_pressure", "unresolved_thread",
                                    "emotional_trend", "future_hook",
                                    "persistent_fact_reference",
                                ],
                            },
                            "content": {"type": "string"},
                            "importance": {"type": "number"},
                            "entity_refs": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "reason": {"type": "string"},
                        },
                    },
                },
                "memory_candidates_rag": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["content"],
                        "properties": {
                            "content": {"type": "string"},
                            "importance": {"type": "number"},
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "reason": {"type": "string"},
                        },
                    },
                },
                "event_summary": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "event_id": {"type": "string"},
                            "description": {"type": "string"},
                            "significance": {"type": "string"},
                        },
                    },
                },
                "relationship_summary": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "subject": {"type": "string"},
                            "target": {"type": "string"},
                            "field": {"type": "string"},
                            "delta": {},
                            "description": {"type": "string"},
                        },
                    },
                },
            },
        }

    def _parse_llm_response(
        self, parsed: dict[str, Any], request: CuratorRequest,
    ) -> TurnEvolutionProposal:
        """Parse LLM response into TurnEvolutionProposal."""
        is_no_change = parsed.get("is_no_state_change", False)

        # Parse state proposal
        raw_proposal = parsed.get("state_update_proposal", {}) or {}
        operations = []
        for op in raw_proposal.get("operations", []):
            # Normalize field names: LLM may return type/key instead of op/path
            op_type = op.get("op", "") or op.get("type", "")
            path = op.get("path", "") or op.get("key", "")
            value = op.get("value")
            reason = op.get("reason", "")

            # Normalize op names from Chinese/alternative formats
            op_map = {
                "set_variable": "set", "increment_variable": "increment",
                "set_event_flag": "set_flag", "set_scene": "set_scene_field",
            }
            op_type = op_map.get(op_type, op_type)

            # Normalize path: if it doesn't have a prefix, try to infer
            if path and "." not in path:
                # If the path looks like a variable name, prefix with variables.
                if op_type in ("set", "increment"):
                    path = f"variables.{path}"
                elif op_type == "set_flag":
                    path = f"event_flags.{path}"

            if op_type not in CURATOR_ALLOWED_OPS:
                continue  # Skip disallowed ops silently
            operations.append({
                "op": op_type,
                "path": path,
                "value": value,
                "reason": reason,
            })

        state_proposal = StateUpdateProposalV2(
            expected_revision=request.base_card_state_revision,
            operations=operations,
            reasoning_summary=raw_proposal.get("reasoning_summary", ""),
        )

        # Parse active memory candidates
        active_candidates = []
        for mc in (parsed.get("memory_candidates_active", []) or []):
            content = str(mc.get("content", ""))[:80]
            if not content:
                continue
            active_candidates.append(MemoryCandidate(
                layer="active",
                kind=mc.get("kind", ""),
                content=content,
                importance=float(mc.get("importance", 0.5)),
                entity_refs=list(mc.get("entity_refs", [])),
                tags=list(mc.get("tags", [])),
                source_hash=_hash_text(request.accepted_writer_output),
                reason=mc.get("reason", ""),
            ))

        # Parse RAG candidates
        rag_candidates = []
        for rc in (parsed.get("memory_candidates_rag", []) or []):
            content = str(rc.get("content", ""))[:200]
            if not content:
                continue
            rag_candidates.append(MemoryCandidate(
                layer="rag",
                kind="turn_record",
                content=content,
                importance=float(rc.get("importance", 0.5)),
                tags=list(rc.get("tags", [])),
                source_hash=_hash_text(request.accepted_writer_output),
                reason=rc.get("reason", ""),
            ))

        return TurnEvolutionProposal(
            proposal_id=f"tep_{uuid.uuid4().hex[:8]}",
            turn_id=request.turn_id,
            session_id=request.session_id,
            state_update_proposal=state_proposal,
            memory_candidates_active=active_candidates,
            memory_candidates_rag=rag_candidates,
            event_summary=list(parsed.get("event_summary", [])),
            relationship_summary=list(parsed.get("relationship_summary", [])),
            curator_confidence=float(parsed.get("curator_confidence", 0.7)),
            curator_reasoning=str(parsed.get("curator_reasoning", "")),
            is_no_state_change=is_no_change or len(operations) == 0,
        )

    # ── Deterministic fallback (fake profiles) ───────────────────────────

    def _curate_deterministic(
        self, request: CuratorRequest,
    ) -> TurnEvolutionProposal:
        """Deterministic curation for offline/fake profile testing.

        Does NOT call any LLM. Produces proposals by analyzing the
        accepted writer output with simple rules.

        This replaces the old FakeMemoryCandidateGenerator + empty patch.
        """
        output = request.accepted_writer_output or ""
        player_input = request.player_input or ""
        combined = f"{player_input} {output}"
        cs = request.pre_turn_card_state
        current_variables = cs.get("variables", {})
        current_scene = cs.get("scene_state", {})
        current_revision = cs.get("revision", 0)

        operations: list[dict[str, Any]] = []
        active_candidates: list[MemoryCandidate] = []
        rag_candidates: list[MemoryCandidate] = []
        events: list[dict[str, Any]] = []

        # ── Scene change detection ───────────────────────────────────────
        # Simple keyword heuristics for scene transitions
        scene_keywords = {
            "街道": ("scene_state.location", "城市街道"),
            "森林": ("scene_state.location", "森林"),
            "酒馆": ("scene_state.location", "酒馆"),
            "房间": ("scene_state.location", "房间"),
            "night": ("scene_state.time_of_day", "night"),
            "夜晚": ("scene_state.time_of_day", "夜晚"),
            "morning": ("scene_state.time_of_day", "morning"),
            "清晨": ("scene_state.time_of_day", "清晨"),
            "雨": ("scene_state.weather", "下雨"),
            "rain": ("scene_state.weather", "rainy"),
            "snow": ("scene_state.weather", "snowy"),
            "雪": ("scene_state.weather", "下雪"),
        }
        for keyword, (path, value) in scene_keywords.items():
            if keyword in combined:
                current_value = current_scene.get(path.split(".")[-1], "")
                if current_value != value:
                    operations.append({
                        "op": "set_scene_field",
                        "path": path,
                        "value": value,
                        "reason": f"scene_keyword:{keyword}",
                    })
                    break  # Only one scene change per turn

        # ── Event flag detection ─────────────────────────────────────────
        event_patterns = [
            ("到达", "event_arrived", "玩家到达新地点"),
            ("离开", "event_departed", "玩家离开当前地点"),
            ("战斗", "event_combat", "发生战斗"),
            ("交易", "event_trade", "进行交易"),
            ("对话", "event_dialogue", "深入对话"),
        ]
        for keyword, flag_id, description in event_patterns:
            if keyword in combined:
                existing = cs.get("event_flags", {})
                if flag_id not in existing:
                    operations.append({
                        "op": "set_flag",
                        "path": f"event_flags.{flag_id}",
                        "value": {},
                        "reason": f"event_keyword:{keyword}",
                    })
                    events.append({
                        "event_id": flag_id,
                        "description": description,
                        "significance": "minor",
                    })

        # ── Relationship / variable heuristics ───────────────────────────
        trust_keywords = ["信任", "信任度", "好感", "喜欢"]
        for kw in trust_keywords:
            if kw in combined:
                if "trust" not in current_variables:
                    operations.append({
                        "op": "set",
                        "path": "variables.trust",
                        "value": 1,
                        "reason": f"trust_keyword:{kw}",
                    })
                else:
                    operations.append({
                        "op": "increment",
                        "path": "variables.trust",
                        "value": 1,
                        "reason": f"trust_keyword:{kw}",
                    })
                active_candidates.append(MemoryCandidate(
                    layer="active",
                    kind="relationship_shift",
                    content=f"信任度变化: {kw}出现在对话中",
                    importance=0.6,
                    entity_refs=["player"],
                    tags=["relationship", "trust"],
                    source_hash=_hash_text(output),
                    reason="trust_keyword_detected",
                ))
                break

        # ── Memory candidate generation from keywords ────────────────────
        # Active memory: promises, secrets, conflicts
        memory_patterns = [
            ("承诺", "promise", 0.7, "检测到承诺相关内容"),
            ("秘密", "secret", 0.8, "检测到秘密相关内容"),
            ("冲突", "conflict", 0.7, "检测到冲突相关内容"),
            ("目标", "player_goal", 0.6, "检测到目标相关内容"),
            ("危险", "scene_pressure", 0.6, "检测到危险相关内容"),
        ]
        for keyword, kind, importance, reason in memory_patterns:
            if keyword in combined:
                content = combined[:80].strip()
                if content:
                    active_candidates.append(MemoryCandidate(
                        layer="active",
                        kind=kind,
                        content=content,
                        importance=importance,
                        tags=[kind],
                        source_hash=_hash_text(output),
                        reason=reason,
                    ))

        # RAG: always create a record for the accepted turn
        if output.strip():
            rag_candidates.append(MemoryCandidate(
                layer="rag",
                kind="turn_record",
                content=output[:80],
                importance=0.5,
                tags=["accepted_turn"],
                source_hash=_hash_text(output),
                reason="accepted_turn_record",
            ))

        is_no_change = len(operations) == 0

        return TurnEvolutionProposal(
            proposal_id=f"tep_{uuid.uuid4().hex[:8]}",
            turn_id=request.turn_id,
            session_id=request.session_id,
            state_update_proposal=StateUpdateProposalV2(
                expected_revision=current_revision,
                operations=operations,
                reasoning_summary="deterministic_heuristic",
            ),
            memory_candidates_active=active_candidates,
            memory_candidates_rag=rag_candidates,
            event_summary=events,
            relationship_summary=[],
            curator_confidence=0.5,
            curator_reasoning="deterministic_fallback",
            is_no_state_change=is_no_change,
        )

    # ── Proposal validation ──────────────────────────────────────────────

    def _validate_proposal(
        self,
        proposal: TurnEvolutionProposal,
        card_state_dict: dict[str, Any],
    ) -> TurnEvolutionProposal:
        """Validate the proposal's state operations against CardState.

        If validation fails, the proposal is marked as no_state_change.
        Accepted text is preserved; state side effects are blocked.
        """
        if proposal.is_no_state_change:
            return proposal

        ops = proposal.state_update_proposal.operations
        if not ops:
            proposal.is_no_state_change = True
            return proposal

        # Convert raw operation dicts to CardStatePatchOperation for validation
        patch_ops = []
        for op in ops:
            try:
                op_type = PatchOpType(op["op"])
            except (ValueError, KeyError):
                proposal.is_no_state_change = True
                proposal.curator_reasoning += " | INVALID_OP_TYPE"
                proposal.state_update_proposal.operations = []
                return proposal

            patch_ops.append(CardStatePatchOperation(
                op=op_type,
                path=op.get("path", ""),
                value=op.get("value"),
                reason=op.get("reason", ""),
            ))

        # Extract current state sets for validation
        current_variables = set(card_state_dict.get("variables", {}).keys())
        current_event_flags = set(card_state_dict.get("event_flags", {}).keys())
        current_stages = list(card_state_dict.get("active_stage_ids", []))

        errors = validate_patch_operations(
            patch_ops, current_variables, current_event_flags, current_stages,
        )

        if errors:
            # Validation failed: reject the entire patch
            proposal.is_no_state_change = True
            error_msgs = [str(e) for e in errors]
            proposal.curator_reasoning += (
                f" | PATCH_VALIDATION_FAILED: {'; '.join(error_msgs[:3])}"
            )
            proposal.state_update_proposal.operations = []
            return proposal

        return proposal
