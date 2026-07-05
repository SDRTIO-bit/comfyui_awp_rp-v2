"""EmotionRelationshipRuntime — orchestrates the Emotion/Relationship Agent.

Flow:
  RoundSnapshot + DelegationTask + TriggerResult
  → build EmotionRelationshipRequest
  → plan queries via EmotionRelationshipQueryPlanner
  → collect evidence from snapshot
  → generate candidates via EmotionRelationshipCandidateGenerator
  → validate via EmotionRelationshipValidator
  → rank via EmotionRelationshipRanker
  → produce EmotionRelationshipResult

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
from ..contracts.emotion_relationship_request import EmotionRelationshipRequest
from ..contracts.relationship_evidence import RelationshipEvidence
from ..contracts.emotion_relationship_candidate import EmotionRelationshipCandidate
from ..contracts.emotion_relationship_result import (
    EmotionRelationshipResult, EmotionRelationshipStatus, RejectedEmotionCandidate,
)
from ..contracts.emotion_relationship_trigger_diagnostics import EmotionRelationshipTriggerDiagnostics
from ..contracts.relationship_risk import RelationshipRisk, RelationshipRiskLevel
from .emotion_relationship_trigger_policy import EmotionRelationshipTriggerResult
from .emotion_relationship_query_planner import EmotionRelationshipQueryPlanner
from .emotion_relationship_candidate_generator import EmotionRelationshipCandidateGenerator
from .emotion_relationship_validator import EmotionRelationshipValidator
from .emotion_relationship_ranker import EmotionRelationshipRanker
from .snapshot_content import worldbook_entry_excerpt


class EmotionRelationshipRuntime:
    """Orchestrates the Emotion/Relationship Agent execution.

    This runtime processes the trigger result and snapshot data to produce
    a structured EmotionRelationshipResult with candidates and recommendations.
    """

    def __init__(self):
        self.query_planner = EmotionRelationshipQueryPlanner()
        self.candidate_generator = EmotionRelationshipCandidateGenerator()
        self.validator = EmotionRelationshipValidator()
        self.ranker = EmotionRelationshipRanker()

    def run(
        self,
        snapshot: RoundSnapshot,
        task: DelegationTask,
        trigger_result: EmotionRelationshipTriggerResult,
        envelope: Any = None,
    ) -> EmotionRelationshipResult:
        """Run the Emotion/Relationship Agent.

        Args:
            snapshot: The current round snapshot
            task: The delegation task
            trigger_result: The trigger policy result
            envelope: Optional AgentTaskEnvelope (unused in fake mode)

        Returns:
            EmotionRelationshipResult with candidates and recommendations
        """
        now = datetime.now(timezone.utc).isoformat()
        start_time = time.time()
        result_id = f"err_{uuid.uuid4().hex[:12]}"

        # If no trigger, return immediately
        if not trigger_result.should_trigger:
            return EmotionRelationshipResult(
                result_id=result_id,
                trace_id=snapshot.trace_id,
                snapshot_id=snapshot.snapshot_id,
                task_run_id=task.task_id,
                status=EmotionRelationshipStatus.NO_TRIGGER,
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
                elif "关系事件断言" in error:
                    violated_policy = "relationship_event"
                elif "关系修改" in error:
                    violated_policy = "relationship_modification"
                elif "玩家代理权" in error:
                    violated_policy = "player_agency"
                elif "突然转变" in error:
                    violated_policy = "sudden_shift"
                elif "mustNotAssertAsFact" in error:
                    violated_policy = "assertion_violation"
                elif "mustNotModifyRelationship" in error:
                    violated_policy = "relationship_violation"
                elif "MemoryCommit" in error:
                    violated_policy = "memory_commit"

                rejected_candidates.append(RejectedEmotionCandidate(
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
            rejected_candidates.append(RejectedEmotionCandidate(
                candidate_id=c.candidate_id,
                reason="被更高优先级候选淘汰",
                violated_policy="outranked",
                evidence_refs=c.evidence_refs,
            ))

        # Determine status
        status = EmotionRelationshipStatus.SUCCESS
        degraded_reasons = []
        if not accepted_candidates and raw_candidates:
            status = EmotionRelationshipStatus.DEGRADED
            degraded_reasons.append("所有候选均被验证拒绝或淘汰")
        elif not accepted_candidates:
            status = EmotionRelationshipStatus.DEGRADED
            degraded_reasons.append("无有效候选")

        # Build recommended IDs
        recommended_ids = [c.candidate_id for c in accepted_candidates]

        duration_ms = int((time.time() - start_time) * 1000)

        # Build diagnostics
        diagnostics = EmotionRelationshipTriggerDiagnostics(
            diagnostics_id=f"erd_{uuid.uuid4().hex[:8]}",
            trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id,
            task_run_id=task.task_id,
            should_trigger=trigger_result.should_trigger,
            trigger_reasons=trigger_result.trigger_reasons,
            emotion_relationship_domains=trigger_result.emotion_relationship_domains,
            focus_entities=trigger_result.focus_entities,
            risk_level=trigger_result.risk_level,
            max_candidate_count=trigger_result.max_candidate_count,
            tool_calls_made=0,  # No actual tool calls in snapshot mode
            candidates_generated=len(raw_candidates),
            candidates_accepted=len(accepted_candidates),
            candidates_rejected=len(rejected_candidates),
            total_duration_ms=duration_ms,
            degraded=(status == EmotionRelationshipStatus.DEGRADED),
            degraded_reasons=degraded_reasons,
            created_at=now,
        )

        # Build result
        result = EmotionRelationshipResult(
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
        trigger_result: EmotionRelationshipTriggerResult,
    ) -> EmotionRelationshipRequest:
        """Build EmotionRelationshipRequest from trigger result."""
        return EmotionRelationshipRequest(
            request_id=f"err_{uuid.uuid4().hex[:8]}",
            trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id,
            task_run_id=task.task_id,
            card_id=snapshot.card_id,
            session_id=snapshot.session_id,
            focus_entities=trigger_result.focus_entities,
            focus_relationship_pairs=[],
            player_intent=snapshot.player_input[:100],
            max_candidates=5,
            required_evidence=True,
            must_not_create_facts=True,
            must_not_modify_relationships=True,
            budget=task.max_tokens or 1000,
        )

    def _collect_evidence_from_snapshot(
        self,
        snapshot: RoundSnapshot,
        trigger_result: EmotionRelationshipTriggerResult,
    ) -> list[RelationshipEvidence]:
        """Collect evidence from snapshot data."""
        evidence: list[RelationshipEvidence] = []
        now = datetime.now(timezone.utc).isoformat()
        entities = set(trigger_result.focus_entities)

        # Evidence from accepted turns
        for i, turn in enumerate(snapshot.recent_turn_records):
            turn_text = turn.writer_output or ""
            ev = RelationshipEvidence(
                evidence_id=f"ev_turn_{turn.turn_id}",
                source_type="accepted_turn",
                source_ref=turn.turn_id,
                excerpt=turn_text[:200],
                entity_refs=list(entities)[:5],
                confidence=0.9,
                relevance_score=0.8,
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from active memories
        for i, mem in enumerate(snapshot.active_memories):
            ev = RelationshipEvidence(
                evidence_id=f"ev_am_{mem.get('memory_id', i)}",
                source_type="active_memory",
                source_ref=mem.get("memory_id", ""),
                excerpt=mem.get("summary", ""),
                entity_refs=mem.get("entity_refs", []),
                confidence=mem.get("confidence", 0.7),
                relevance_score=mem.get("importance", 0.5),
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from RAG recall
        for i, rag in enumerate(snapshot.rag_recall):
            ev = RelationshipEvidence(
                evidence_id=f"ev_rag_{rag.get('memory_id', i)}",
                source_type="rag_memory",
                source_ref=rag.get("memory_id", ""),
                excerpt=rag.get("summary", ""),
                entity_refs=rag.get("entity_refs", []),
                confidence=rag.get("confidence", 0.6),
                relevance_score=rag.get("importance", 0.4),
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from worldbook
        for i, wb in enumerate(snapshot.active_worldbook_entries):
            ev = RelationshipEvidence(
                evidence_id=f"ev_wb_{i}",
                source_type="worldbook",
                source_ref=wb.get("title", f"wb_{i}"),
                excerpt=worldbook_entry_excerpt(wb, 200),
                confidence=0.5,
                relevance_score=0.3,
                created_at=now,
            )
            evidence.append(ev)

        return evidence
