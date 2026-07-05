"""HistoryRecallRuntime — orchestrates the History/Recall Agent.

Flow:
  RoundSnapshot + DelegationTask + TriggerResult
  → build HistoryRecallRequest
  → plan queries via HistoryRecallQueryPlanner
  → execute tools via ToolGateway (or snapshot data directly)
  → rank evidence via RecallEvidenceRanker
  → validate via HistoryRecallValidator
  → produce HistoryRecallResult

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
from ..contracts.recall_focus import RecallKind
from ..contracts.recall_evidence import RecallEvidence, EvidenceSourceType
from ..contracts.continuity_risk import ContinuityRisk, RiskLevel
from ..contracts.history_recall_request import HistoryRecallRequest
from ..contracts.history_recall_result import HistoryRecallResult, HistoryRecallStatus
from ..contracts.history_recall_suggestion import HistoryRecallSuggestion, HistorySuggestionKind
from ..contracts.history_recall_diagnostics import HistoryRecallDiagnostics
from .history_recall_trigger_policy import TriggerResult
from .history_recall_query_planner import HistoryRecallQueryPlanner
from .recall_evidence_ranker import RecallEvidenceRanker
from .history_recall_validator import HistoryRecallValidator
from .snapshot_content import worldbook_entry_excerpt


class HistoryRecallRuntime:
    """Orchestrates the History/Recall Agent execution.

    This runtime processes the trigger result and snapshot data to produce
    a structured HistoryRecallResult with evidence and recommendations.
    """

    def __init__(self):
        self.query_planner = HistoryRecallQueryPlanner()
        self.evidence_ranker = RecallEvidenceRanker()
        self.validator = HistoryRecallValidator()

    def run(
        self,
        snapshot: RoundSnapshot,
        task: DelegationTask,
        trigger_result: TriggerResult,
        envelope: Any = None,
    ) -> HistoryRecallResult:
        """Run the History/Recall Agent.

        Args:
            snapshot: The current round snapshot
            task: The delegation task
            trigger_result: The trigger policy result
            envelope: Optional AgentTaskEnvelope (unused in fake mode)

        Returns:
            HistoryRecallResult with evidence and recommendations
        """
        now = datetime.now(timezone.utc).isoformat()
        start_time = time.time()
        result_id = f"hrr_{uuid.uuid4().hex[:12]}"

        # If no trigger, return immediately
        if not trigger_result.should_trigger:
            return HistoryRecallResult(
                result_id=result_id,
                trace_id=snapshot.trace_id,
                snapshot_id=snapshot.snapshot_id,
                task_run_id=task.task_id,
                status=HistoryRecallStatus.NO_TRIGGER,
                created_at=now,
            )

        # Build request
        request = self._build_request(snapshot, task, trigger_result)

        # Collect evidence from snapshot data
        evidence = self._collect_evidence_from_snapshot(snapshot, trigger_result)

        # Rank evidence
        ranked_evidence = self.evidence_ranker.rank(evidence)

        # Determine confirmed and ambiguous facts
        confirmed_evidence = self.evidence_ranker.filter_confirmed(ranked_evidence)
        conflicted_evidence = self.evidence_ranker.filter_conflicted(ranked_evidence)

        # Build confirmed facts from confirmed evidence
        confirmed_facts = []
        for ev in confirmed_evidence:
            if ev.excerpt:
                confirmed_facts.append(ev.excerpt)

        # Build ambiguous facts
        ambiguous_facts = []
        for ev in ranked_evidence:
            if ev.conflict_status == "stale":
                ambiguous_facts.append(f"[stale] {ev.excerpt}")

        # Build conflicts
        conflicts = []
        for ev in conflicted_evidence:
            conflicts.append({
                "evidence_id": ev.evidence_id,
                "source_type": ev.source_type,
                "excerpt": ev.excerpt,
                "conflict_status": ev.conflict_status,
                "conflict_reason": ev.conflict_reason,
            })

        # Build continuity risks
        continuity_risks = []
        if conflicts:
            continuity_risks.append(ContinuityRisk(
                risk_id=f"cr_{uuid.uuid4().hex[:8]}",
                risk_level=RiskLevel.HIGH if len(conflicts) > 1 else RiskLevel.MEDIUM,
                description=f"发现{len(conflicts)}条冲突证据",
                entity_refs=trigger_result.suggested_focus_entities[:3],
            ))

        # Build writer recommendations
        writer_recommendations = []
        for fact in confirmed_facts[:5]:
            writer_recommendations.append(f"保持事实一致: {fact[:80]}")
        if continuity_risks:
            writer_recommendations.append("注意历史冲突，避免矛盾叙述")

        # Build director recommendations
        director_recommendations = []
        if conflicts:
            director_recommendations.append("需要决定如何处理历史冲突")
        if ambiguous_facts:
            director_recommendations.append("存在模糊历史事实，可能需要进一步确认")

        # Build suggestions
        suggestions = self._build_suggestions(
            confirmed_facts, continuity_risks, trigger_result
        )

        # Determine status
        status = HistoryRecallStatus.SUCCESS
        degraded_reasons = []
        if conflicted_evidence:
            status = HistoryRecallStatus.DEGRADED
            degraded_reasons.append(f"存在{len(conflicted_evidence)}条冲突证据")

        duration_ms = int((time.time() - start_time) * 1000)

        # Build diagnostics
        diagnostics = HistoryRecallDiagnostics(
            diagnostics_id=f"hd_{uuid.uuid4().hex[:8]}",
            trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id,
            task_run_id=task.task_id,
            trigger_reasons=trigger_result.trigger_reasons,
            suggested_focus_entities=trigger_result.suggested_focus_entities,
            risk_level=trigger_result.risk_level.value,
            tool_calls_made=0,  # No actual tool calls in snapshot mode
            evidence_collected=len(evidence),
            evidence_confirmed=len(confirmed_evidence),
            evidence_ambiguous=len(ambiguous_facts),
            evidence_conflicted=len(conflicted_evidence),
            total_duration_ms=duration_ms,
            degraded=(status == HistoryRecallStatus.DEGRADED),
            degraded_reasons=degraded_reasons,
            created_at=now,
        )

        # Validate
        result = HistoryRecallResult(
            result_id=result_id,
            trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id,
            task_run_id=task.task_id,
            status=status,
            focus_entities=trigger_result.suggested_focus_entities,
            evidence=ranked_evidence,
            confirmed_facts=confirmed_facts,
            ambiguous_facts=ambiguous_facts,
            conflicts=conflicts,
            continuity_risks=continuity_risks,
            writer_recommendations=writer_recommendations,
            director_recommendations=director_recommendations,
            degraded_reasons=degraded_reasons,
            suggestions=suggestions,
            created_at=now,
        )

        # Validate result
        errors = self.validator.validate(result)
        if errors:
            # Downgrade to degraded if validation fails
            result.status = HistoryRecallStatus.DEGRADED
            result.degraded_reasons.extend(errors)

        return result

    def _build_request(
        self,
        snapshot: RoundSnapshot,
        task: DelegationTask,
        trigger_result: TriggerResult,
    ) -> HistoryRecallRequest:
        """Build HistoryRecallRequest from trigger result."""
        recall_kinds = []
        for kind_str in trigger_result.suggested_recall_kinds:
            try:
                recall_kinds.append(RecallKind(kind_str))
            except ValueError:
                pass

        return HistoryRecallRequest(
            request_id=f"hrr_{uuid.uuid4().hex[:8]}",
            trace_id=snapshot.trace_id,
            snapshot_id=snapshot.snapshot_id,
            task_run_id=task.task_id,
            card_id=snapshot.card_id,
            session_id=snapshot.session_id,
            focus_entities=trigger_result.suggested_focus_entities,
            recall_kinds=recall_kinds,
            max_tool_calls=len(task.tool_allowlist) or 7,
        )

    def _collect_evidence_from_snapshot(
        self,
        snapshot: RoundSnapshot,
        trigger_result: TriggerResult,
    ) -> list[RecallEvidence]:
        """Collect evidence from snapshot data (accepted turns, active memory, RAG)."""
        evidence: list[RecallEvidence] = []
        now = datetime.now(timezone.utc).isoformat()
        entities = set(trigger_result.suggested_focus_entities)

        # Evidence from accepted turns (L1 — highest priority)
        for i, turn in enumerate(snapshot.recent_turn_records):
            # Check if any focus entity is mentioned
            turn_text = turn.writer_output or ""
            if entities and not any(e in turn_text for e in entities):
                # Still include if no entities specified
                if entities:
                    continue

            ev = RecallEvidence(
                evidence_id=f"ev_turn_{turn.turn_id}",
                source_type=EvidenceSourceType.ACCEPTED_TURN,
                source_ref=turn.turn_id,
                source_turn_id=turn.turn_id,
                source_card_state_revision=turn.result_card_state_revision,
                excerpt=turn_text[:200],
                entity_refs=list(entities)[:5],
                confidence=0.9,
                recency=1.0 - (i * 0.1),  # More recent = higher
                relevance_score=0.8,
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from active memories (L2)
        for i, mem in enumerate(snapshot.active_memories):
            mem_refs = set(mem.get("entity_refs", []))
            if entities and not (mem_refs & entities):
                continue

            ev = RecallEvidence(
                evidence_id=f"ev_am_{mem.get('memory_id', i)}",
                source_type=EvidenceSourceType.ACTIVE_MEMORY,
                source_ref=mem.get("memory_id", ""),
                excerpt=mem.get("summary", ""),
                entity_refs=mem.get("entity_refs", []),
                confidence=mem.get("confidence", 0.7),
                recency=0.8 - (i * 0.05),
                relevance_score=mem.get("importance", 0.5),
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from RAG recall (L3)
        for i, rag in enumerate(snapshot.rag_recall):
            rag_refs = set(rag.get("entity_refs", []))
            if entities and not (rag_refs & entities):
                continue

            conflict_status = rag.get("conflict_status", "")
            ev = RecallEvidence(
                evidence_id=f"ev_rag_{rag.get('memory_id', i)}",
                source_type=EvidenceSourceType.RAG_MEMORY,
                source_ref=rag.get("memory_id", ""),
                excerpt=rag.get("summary", ""),
                entity_refs=rag.get("entity_refs", []),
                confidence=rag.get("confidence", 0.6),
                recency=0.6 - (i * 0.05),
                relevance_score=rag.get("importance", 0.4),
                conflict_status=conflict_status,
                conflict_reason=rag.get("conflict_reason", ""),
                created_at=now,
            )
            evidence.append(ev)

        # Evidence from worldbook
        for i, wb in enumerate(snapshot.active_worldbook_entries):
            ev = RecallEvidence(
                evidence_id=f"ev_wb_{i}",
                source_type=EvidenceSourceType.WORLDBOOK,
                source_ref=wb.get("title", f"wb_{i}"),
                excerpt=worldbook_entry_excerpt(wb, 200),
                confidence=0.5,
                recency=0.5,
                relevance_score=0.3,
                created_at=now,
            )
            evidence.append(ev)

        return evidence

    def _build_suggestions(
        self,
        confirmed_facts: list[str],
        continuity_risks: list[ContinuityRisk],
        trigger_result: TriggerResult,
    ) -> list[HistoryRecallSuggestion]:
        """Build HistoryRecallSuggestion list from findings."""
        suggestions: list[HistoryRecallSuggestion] = []

        # Continuity facts
        for i, fact in enumerate(confirmed_facts[:5]):
            suggestions.append(HistoryRecallSuggestion(
                suggestion_id=f"hs_{uuid.uuid4().hex[:8]}",
                kind=HistorySuggestionKind.CONTINUITY_FACT,
                summary=fact[:200],
                confidence=0.8,
                priority=0.9 - (i * 0.1),
            ))

        # Continuity risks
        for risk in continuity_risks:
            suggestions.append(HistoryRecallSuggestion(
                suggestion_id=f"hs_{uuid.uuid4().hex[:8]}",
                kind=HistorySuggestionKind.HISTORICAL_CONFLICT,
                summary=risk.description,
                entity_refs=risk.entity_refs,
                confidence=0.7,
                priority=0.95,
            ))

        # Writer constraints from trigger
        if "promise_history" in trigger_result.suggested_recall_kinds:
            suggestions.append(HistoryRecallSuggestion(
                suggestion_id=f"hs_{uuid.uuid4().hex[:8]}",
                kind=HistorySuggestionKind.WRITER_CONSTRAINT,
                summary="保持承诺历史一致性",
                confidence=0.8,
                priority=0.85,
            ))

        return suggestions
