"""ContinuityRuntime — orchestrates the Continuity Agent.

Flow:
  RoundSnapshot + DelegationTask + TriggerResult
  → build ContinuityRequest
  → plan queries via ContinuityQueryPlanner
  → collect evidence from snapshot
  → rank evidence via ContinuityEvidenceRanker
  → detect issues via ContinuityIssueDetector
  → validate via ContinuityValidator
  → rank issues via ContinuityRanker
  → produce ContinuityResult

The runtime does NOT:
- Write to CardState, TurnRecord, ActiveMemory, RAG
- Access SQLite/Store directly
- Delegate to sub-agents
- Generate player-visible final text
- Create new events or advance timeline
- Modify relationships or scenes
- Access environment variables, files, or network
"""
from __future__ import annotations

import uuid
import time
from datetime import datetime, timezone
from typing import Any

from ..contracts.round_snapshot import RoundSnapshot
from ..contracts.delegation_plan import DelegationTask
from ..contracts.continuity_request import ContinuityRequest
from ..contracts.continuity_evidence import ContinuityEvidence, EvidenceSourceType
from ..contracts.continuity_issue import ContinuityIssue, ContinuitySeverity
from ..contracts.continuity_conflict import ContinuityConflict, ConflictResolution
from ..contracts.continuity_result import ContinuityResult, ContinuityStatus
from ..contracts.continuity_trigger_diagnostics import ContinuityTriggerDiagnostics
from .continuity_trigger_policy import ContinuityTriggerResult
from .continuity_query_planner import ContinuityQueryPlanner
from .continuity_evidence_ranker import ContinuityEvidenceRanker
from .continuity_issue_detector import ContinuityIssueDetector
from .continuity_validator import ContinuityValidator
from .continuity_ranker import ContinuityRanker
from .snapshot_content import worldbook_entry_excerpt


class ContinuityRuntime:
    """Orchestrates the Continuity Agent execution.

    This runtime processes the trigger result and snapshot data to produce
    a structured ContinuityResult with issues and constraints.
    """

    def __init__(self):
        self.query_planner = ContinuityQueryPlanner()
        self.evidence_ranker = ContinuityEvidenceRanker()
        self.issue_detector = ContinuityIssueDetector()
        self.validator = ContinuityValidator()
        self.ranker = ContinuityRanker()

    def run(
        self,
        snapshot: RoundSnapshot,
        task: DelegationTask,
        trigger_result: ContinuityTriggerResult,
        envelope: Any = None,
    ) -> ContinuityResult:
        """Run the Continuity Agent.

        Args:
            snapshot: The current round snapshot
            task: The delegation task
            trigger_result: The trigger policy result
            envelope: Optional AgentTaskEnvelope (unused in fake mode)

        Returns:
            ContinuityResult with issues and constraints
        """
        now = datetime.now(timezone.utc).isoformat()
        start_time = time.time()
        result_id = f"clr_{uuid.uuid4().hex[:12]}"

        # If no trigger, return immediately
        if not trigger_result.should_trigger:
            return ContinuityResult(
                result_id=result_id,
                trace_id=snapshot.trace_id,
                snapshot_id=snapshot.snapshot_id,
                task_run_id=task.task_id,
                status=ContinuityStatus.NO_TRIGGER,
                created_at=now,
            )

        # Build request
        request = self._build_request(snapshot, task, trigger_result)

        # Collect evidence from snapshot data
        evidence = self._collect_evidence_from_snapshot(snapshot, trigger_result)

        # Rank evidence by priority
        ranked_evidence = self.evidence_ranker.rank(evidence)

        # Detect conflicts
        conflicts_raw = self.evidence_ranker.detect_conflicts(ranked_evidence)

        # Mark stale evidence
        ranked_evidence = self.evidence_ranker.mark_stale(ranked_evidence)

        # Build conflict records
        conflicts = []
        for ev_high, ev_low, desc in conflicts_raw:
            conflicts.append(ContinuityConflict(
                conflict_id=f"cc_{uuid.uuid4().hex[:8]}",
                trace_id=snapshot.trace_id,
                snapshot_id=snapshot.snapshot_id,
                higher_priority_evidence_id=ev_high.evidence_id,
                lower_priority_evidence_id=ev_low.evidence_id,
                higher_priority_source=ev_high.source_type.value,
                lower_priority_source=ev_low.source_type.value,
                fact_description=desc,
                resolution=ConflictResolution.HIGHER_PRIORITY_WINS,
                resolution_reason=f"{ev_high.source_type.value} 优先于 {ev_low.source_type.value}",
                created_at=now,
            ))

        # Detect issues
        raw_issues = self.issue_detector.detect(
            snapshot=snapshot,
            trigger_result=trigger_result,
            evidence=ranked_evidence,
            max_issues=request.max_issues,
        )

        # Validate issues
        valid_issues, rejected_with_reasons = self.validator.validate_batch(
            raw_issues, ranked_evidence, snapshot,
        )

        # Rank valid issues
        accepted_issues, outranked = self.ranker.rank(
            valid_issues, max_blocking=3, max_warning=3,
        )

        # Classify by severity
        blocking = [i for i in accepted_issues if i.severity == ContinuitySeverity.BLOCKING]
        warnings = [i for i in accepted_issues if i.severity == ContinuitySeverity.WARNING]
        info = [i for i in accepted_issues if i.severity == ContinuitySeverity.INFO]

        # Build writer constraints
        writer_constraints = []
        for issue in blocking:
            if issue.writer_constraint:
                writer_constraints.append(issue.writer_constraint)
        for issue in warnings:
            if issue.writer_constraint:
                writer_constraints.append(issue.writer_constraint)

        # Build director recommendations
        director_recommendations = []
        for issue in blocking:
            if issue.director_recommendation:
                director_recommendations.append(issue.director_recommendation)
        for issue in warnings:
            if issue.director_recommendation:
                director_recommendations.append(issue.director_recommendation)

        # Determine status
        status = ContinuityStatus.SUCCESS
        degraded_reasons = []
        if not accepted_issues and raw_issues:
            status = ContinuityStatus.DEGRADED
            degraded_reasons.append("所有 issue 均被验证拒绝或淘汰")
        elif not accepted_issues:
            status = ContinuityStatus.DEGRADED
            degraded_reasons.append("无有效 issue")

        duration_ms = int((time.time() - start_time) * 1000)

        # Build diagnostics
        diagnostics = ContinuityTriggerDiagnostics(
            diagnostics_id=f"cld_{uuid.uuid4().hex[:8]}",
            trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id,
            task_run_id=task.task_id,
            should_trigger=trigger_result.should_trigger,
            trigger_reasons=trigger_result.trigger_reasons,
            continuity_domains=trigger_result.continuity_domains,
            focus_entities=trigger_result.focus_entities,
            focus_locations=trigger_result.focus_locations,
            focus_turns=trigger_result.focus_turns,
            risk_level=trigger_result.risk_level,
            max_issue_count=trigger_result.max_issue_count,
            tool_calls_made=0,
            issues_detected=len(raw_issues),
            issues_blocking=len(blocking),
            issues_warning=len(warnings),
            issues_info=len(info),
            total_duration_ms=duration_ms,
            degraded=(status == ContinuityStatus.DEGRADED),
            degraded_reasons=degraded_reasons,
            created_at=now,
        )

        # Build result
        return ContinuityResult(
            result_id=result_id,
            trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id,
            task_run_id=task.task_id,
            status=status,
            issues=accepted_issues,
            blocking_issues=blocking,
            warnings=warnings,
            informational_notes=info,
            conflicts=conflicts,
            writer_constraints=writer_constraints,
            director_recommendations=director_recommendations,
            degraded_reasons=degraded_reasons,
            created_at=now,
        )

    def _build_request(
        self,
        snapshot: RoundSnapshot,
        task: DelegationTask,
        trigger_result: ContinuityTriggerResult,
    ) -> ContinuityRequest:
        """Build ContinuityRequest from trigger result."""
        return ContinuityRequest(
            request_id=f"clr_{uuid.uuid4().hex[:8]}",
            trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id,
            task_run_id=task.task_id,
            card_id=snapshot.card_id,
            session_id=snapshot.session_id,
            focus_entities=trigger_result.focus_entities,
            focus_locations=trigger_result.focus_locations,
            focus_turns=trigger_result.focus_turns,
            max_issues=trigger_result.max_issue_count,
            required_evidence=True,
            budget=task.max_tokens or 1000,
        )

    def _collect_evidence_from_snapshot(
        self,
        snapshot: RoundSnapshot,
        trigger_result: ContinuityTriggerResult,
    ) -> list[ContinuityEvidence]:
        """Collect evidence from snapshot data."""
        evidence: list[ContinuityEvidence] = []
        now = datetime.now(timezone.utc).isoformat()
        scene_location = snapshot.card_state.scene_state.location if snapshot.card_state.scene_state else ""

        # Evidence from CardState (highest priority)
        if scene_location:
            ev = ContinuityEvidence(
                evidence_id=f"ev_cardstate_{scene_location}",
                source_type=EvidenceSourceType.CARD_STATE,
                source_ref=f"cardstate:{snapshot.card_id}",
                source_snapshot_id=snapshot.snapshot_id,
                source_card_state_revision=snapshot.base_card_state_revision,
                excerpt=f"当前地点: {scene_location}",
                entity_refs=[],
                location_refs=[scene_location],
                confidence=1.0,
                recency=1.0,
                relevance_score=1.0,
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from accepted turns (second highest priority)
        for turn in snapshot.recent_turn_records:
            turn_text = turn.writer_output or ""
            ev = ContinuityEvidence(
                evidence_id=f"ev_turn_{turn.turn_id}",
                source_type=EvidenceSourceType.ACCEPTED_TURN,
                source_ref=turn.turn_id,
                source_turn_id=turn.turn_id,
                excerpt=turn_text[:200],
                entity_refs=[],
                location_refs=[scene_location],
                confidence=0.9,
                recency=0.9,
                relevance_score=0.8,
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from active memories
        for mem in snapshot.active_memories:
            ev = ContinuityEvidence(
                evidence_id=f"ev_am_{mem.get('memory_id', '')}",
                source_type=EvidenceSourceType.ACTIVE_MEMORY,
                source_ref=mem.get("memory_id", ""),
                excerpt=mem.get("summary", ""),
                entity_refs=mem.get("entity_refs", []),
                location_refs=[scene_location],
                confidence=mem.get("confidence", 0.7),
                recency=0.7,
                relevance_score=mem.get("importance", 0.5),
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from RAG recall
        for rag in snapshot.rag_recall:
            ev = ContinuityEvidence(
                evidence_id=f"ev_rag_{rag.get('memory_id', '')}",
                source_type=EvidenceSourceType.RAG_MEMORY,
                source_ref=rag.get("memory_id", ""),
                excerpt=rag.get("summary", ""),
                entity_refs=rag.get("entity_refs", []),
                location_refs=[scene_location],
                confidence=rag.get("confidence", 0.6),
                recency=0.5,
                relevance_score=rag.get("importance", 0.4),
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from worldbook
        for i, wb in enumerate(snapshot.active_worldbook_entries):
            ev = ContinuityEvidence(
                evidence_id=f"ev_wb_{i}",
                source_type=EvidenceSourceType.WORLDBOOK,
                source_ref=wb.get("title", f"wb_{i}"),
                excerpt=worldbook_entry_excerpt(wb, 200),
                location_refs=[scene_location],
                confidence=0.5,
                recency=0.3,
                relevance_score=0.3,
                created_at=now,
            )
            evidence.append(ev)

        return evidence
