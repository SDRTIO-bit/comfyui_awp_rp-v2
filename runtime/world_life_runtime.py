"""WorldLifeRuntime — orchestrates the World-Life Agent.

Flow:
  RoundSnapshot + DelegationTask + TriggerResult
  → build WorldLifeRequest
  → plan queries via WorldLifeQueryPlanner
  → collect evidence from snapshot
  → generate candidates via WorldLifeCandidateGenerator
  → validate via WorldLifeValidator
  → rank via WorldLifeRanker
  → produce WorldLifeResult

The runtime does NOT:
- Write to CardState, TurnRecord, ActiveMemory, RAG
- Access SQLite/Store directly
- Delegate to sub-agents
- Generate player-visible final text
- Access environment variables, files, or network
"""
from __future__ import annotations

import uuid
import time
from datetime import datetime, timezone
from typing import Any

from ..contracts.round_snapshot import RoundSnapshot
from ..contracts.delegation_plan import DelegationTask
from ..contracts.world_life_request import WorldLifeRequest
from ..contracts.world_life_evidence import WorldLifeEvidence
from ..contracts.world_life_candidate import WorldLifeCandidate
from ..contracts.world_life_result import WorldLifeResult, WorldLifeStatus, RejectedWorldLifeCandidate
from ..contracts.world_life_trigger_diagnostics import WorldLifeTriggerDiagnostics
from ..contracts.world_life_risk import WorldLifeRisk, WorldLifeRiskLevel
from .world_life_trigger_policy import WorldLifeTriggerResult
from .world_life_query_planner import WorldLifeQueryPlanner
from .world_life_candidate_generator import WorldLifeCandidateGenerator
from .world_life_validator import WorldLifeValidator
from .world_life_ranker import WorldLifeRanker
from .snapshot_content import worldbook_entry_excerpt


class WorldLifeRuntime:
    """Orchestrates the World-Life Agent execution.

    This runtime processes the trigger result and snapshot data to produce
    a structured WorldLifeResult with candidates and recommendations.
    """

    def __init__(self):
        self.query_planner = WorldLifeQueryPlanner()
        self.candidate_generator = WorldLifeCandidateGenerator()
        self.validator = WorldLifeValidator()
        self.ranker = WorldLifeRanker()

    def run(
        self,
        snapshot: RoundSnapshot,
        task: DelegationTask,
        trigger_result: WorldLifeTriggerResult,
        envelope: Any = None,
    ) -> WorldLifeResult:
        """Run the World-Life Agent.

        Args:
            snapshot: The current round snapshot
            task: The delegation task
            trigger_result: The trigger policy result
            envelope: Optional AgentTaskEnvelope (unused in fake mode)

        Returns:
            WorldLifeResult with candidates and recommendations
        """
        now = datetime.now(timezone.utc).isoformat()
        start_time = time.time()
        result_id = f"wlr_{uuid.uuid4().hex[:12]}"

        # If no trigger, return immediately
        if not trigger_result.should_trigger:
            return WorldLifeResult(
                result_id=result_id,
                trace_id=snapshot.trace_id,
                snapshot_id=snapshot.snapshot_id,
                task_run_id=task.task_id,
                status=WorldLifeStatus.NO_TRIGGER,
                created_at=now,
            )

        # Build request
        request = self._build_request(snapshot, task, trigger_result)

        # Collect evidence from snapshot data
        evidence = self._collect_evidence_from_snapshot(snapshot, trigger_result)

        # Generate candidates
        raw_candidates = self.candidate_generator.generate(
            snapshot=snapshot,
            trigger_result=trigger_result,
            evidence=evidence,
            max_candidates=request.max_candidates,
        )

        # Validate candidates
        valid_candidates, rejected_with_reasons = self.validator.validate_batch(
            raw_candidates, snapshot
        )

        # Build rejected candidate records
        rejected_candidates = []
        for candidate, errors in rejected_with_reasons:
            for error in errors:
                violated_policy = "unknown"
                if "证据" in error:
                    violated_policy = "missing_evidence"
                elif "事件断言" in error:
                    violated_policy = "event_assertion"
                elif "状态修改" in error:
                    violated_policy = "state_modification"
                elif "玩家代理权" in error:
                    violated_policy = "player_agency"
                elif "mustNotAssertAsFact" in error:
                    violated_policy = "assertion_violation"
                elif "mustNotCommitState" in error:
                    violated_policy = "state_commit"
                elif "自动推进" in error:
                    violated_policy = "auto_advance"
                elif "MemoryCommit" in error:
                    violated_policy = "memory_commit"

                rejected_candidates.append(RejectedWorldLifeCandidate(
                    candidate_id=candidate.candidate_id,
                    reason=error,
                    violated_policy=violated_policy,
                    evidence_refs=candidate.evidence_refs,
                ))

        # Rank valid candidates
        accepted_candidates, outranked = self.ranker.rank(
            valid_candidates, max_accepted=trigger_result.max_candidate_count
        )

        # Add outranked candidates to rejected
        for c in outranked:
            rejected_candidates.append(RejectedWorldLifeCandidate(
                candidate_id=c.candidate_id,
                reason="被更高优先级候选淘汰",
                violated_policy="outranked",
                evidence_refs=c.evidence_refs,
            ))

        # Determine status
        status = WorldLifeStatus.SUCCESS
        degraded_reasons = []
        if not accepted_candidates and raw_candidates:
            status = WorldLifeStatus.DEGRADED
            degraded_reasons.append("所有候选均被验证拒绝或淘汰")
        elif not accepted_candidates:
            status = WorldLifeStatus.DEGRADED
            degraded_reasons.append("无有效候选")

        # Build recommended IDs
        recommended_ids = [c.candidate_id for c in accepted_candidates]

        duration_ms = int((time.time() - start_time) * 1000)

        # Build diagnostics
        diagnostics = WorldLifeTriggerDiagnostics(
            diagnostics_id=f"wld_{uuid.uuid4().hex[:8]}",
            trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id,
            task_run_id=task.task_id,
            should_trigger=trigger_result.should_trigger,
            trigger_reasons=trigger_result.trigger_reasons,
            world_life_domains=trigger_result.world_life_domains,
            focus_entities=trigger_result.focus_entities,
            focus_locations=trigger_result.focus_locations,
            focus_event_stages=trigger_result.focus_event_stages,
            risk_level=trigger_result.risk_level,
            max_candidate_count=trigger_result.max_candidate_count,
            tool_calls_made=0,  # No actual tool calls in snapshot mode
            candidates_generated=len(raw_candidates),
            candidates_accepted=len(accepted_candidates),
            candidates_rejected=len(rejected_candidates),
            total_duration_ms=duration_ms,
            degraded=(status == WorldLifeStatus.DEGRADED),
            degraded_reasons=degraded_reasons,
            created_at=now,
        )

        # Build result
        result = WorldLifeResult(
            result_id=result_id,
            trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id,
            task_run_id=task.task_id,
            status=status,
            candidates=accepted_candidates,
            rejected_candidates=rejected_candidates,
            degraded_reasons=degraded_reasons,
            recommended_candidate_ids=recommended_ids,
            created_at=now,
        )

        return result

    def _build_request(
        self,
        snapshot: RoundSnapshot,
        task: DelegationTask,
        trigger_result: WorldLifeTriggerResult,
    ) -> WorldLifeRequest:
        """Build WorldLifeRequest from trigger result."""
        scene_location = snapshot.card_state.scene_state.location if snapshot.card_state.scene_state else ""
        return WorldLifeRequest(
            request_id=f"wlr_{uuid.uuid4().hex[:8]}",
            trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id,
            task_run_id=task.task_id,
            card_id=snapshot.card_id,
            session_id=snapshot.session_id,
            focus_entities=trigger_result.focus_entities,
            focus_locations=trigger_result.focus_locations,
            focus_event_stages=trigger_result.focus_event_stages,
            current_scene_summary=f"地点: {scene_location}",
            player_intent=snapshot.player_input[:100],
            max_candidates=5,
            required_evidence=True,
            must_not_create_facts=True,
            must_not_advance_timeline=True,
            must_not_modify_card_state=True,
            budget=task.max_tokens or 1000,
        )

    def _collect_evidence_from_snapshot(
        self,
        snapshot: RoundSnapshot,
        trigger_result: WorldLifeTriggerResult,
    ) -> list[WorldLifeEvidence]:
        """Collect evidence from snapshot data."""
        evidence: list[WorldLifeEvidence] = []
        now = datetime.now(timezone.utc).isoformat()
        entities = set(trigger_result.focus_entities)
        scene_location = snapshot.card_state.scene_state.location if snapshot.card_state.scene_state else ""

        # Evidence from scene context (location)
        if scene_location:
            ev = WorldLifeEvidence(
                evidence_id=f"ev_scene_{scene_location}",
                source_type="scene_context",
                source_ref=scene_location,
                excerpt=f"当前地点: {scene_location}",
                entity_refs=list(entities)[:5],
                location_ref=scene_location,
                confidence=0.8,
                relevance_score=0.7,
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from accepted turns
        for i, turn in enumerate(snapshot.recent_turn_records):
            turn_text = turn.writer_output or ""
            ev = WorldLifeEvidence(
                evidence_id=f"ev_turn_{turn.turn_id}",
                source_type="accepted_turn",
                source_ref=turn.turn_id,
                excerpt=turn_text[:200],
                entity_refs=list(entities)[:5],
                location_ref=scene_location,
                confidence=0.9,
                relevance_score=0.8,
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from active memories
        for i, mem in enumerate(snapshot.active_memories):
            ev = WorldLifeEvidence(
                evidence_id=f"ev_am_{mem.get('memory_id', i)}",
                source_type="active_memory",
                source_ref=mem.get("memory_id", ""),
                excerpt=mem.get("summary", ""),
                entity_refs=mem.get("entity_refs", []),
                location_ref=scene_location,
                confidence=mem.get("confidence", 0.7),
                relevance_score=mem.get("importance", 0.5),
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from RAG recall
        for i, rag in enumerate(snapshot.rag_recall):
            ev = WorldLifeEvidence(
                evidence_id=f"ev_rag_{rag.get('memory_id', i)}",
                source_type="rag_memory",
                source_ref=rag.get("memory_id", ""),
                excerpt=rag.get("summary", ""),
                entity_refs=rag.get("entity_refs", []),
                location_ref=scene_location,
                confidence=rag.get("confidence", 0.6),
                relevance_score=rag.get("importance", 0.4),
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from worldbook
        for i, wb in enumerate(snapshot.active_worldbook_entries):
            ev = WorldLifeEvidence(
                evidence_id=f"ev_wb_{i}",
                source_type="worldbook",
                source_ref=wb.get("title", f"wb_{i}"),
                excerpt=worldbook_entry_excerpt(wb, 200),
                location_ref=scene_location,
                confidence=0.5,
                relevance_score=0.3,
                created_at=now,
            )
            evidence.append(ev)

        return evidence
