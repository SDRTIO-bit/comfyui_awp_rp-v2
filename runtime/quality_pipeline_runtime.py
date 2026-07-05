"""QualityPipelineRuntime — unified quality checking pipeline.

Runs all quality gates and aggregates results.
Only accepted drafts can proceed to state/memory commits.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..contracts.writer_draft import WriterDraft
from ..contracts.quality_issue import QualityIssue, IssueSeverity, IssueCategory
from ..contracts.quality_gate_result import QualityGateResult
from ..contracts.round_snapshot import RoundSnapshot
from ..contracts.quality_decision import QualityDecision, QualityVerdict


class IdentityGate:
    """Checks character identity and name consistency."""

    def check(self, draft: WriterDraft, snapshot: RoundSnapshot) -> QualityGateResult:
        issues = []
        # Check that character names in the draft match known characters
        known_chars = set(snapshot.card_state.scene_state.active_npcs)
        known_chars.add("player")

        # Simple heuristic: if draft mentions unknown character names, flag it
        # (In a real system, this would use NLP or LLM)
        for char in snapshot.card_state.scene_state.active_npcs:
            if char and char not in draft.text and len(draft.text) > 200:
                issues.append(QualityIssue(
                    issue_id=f"qi_{uuid.uuid4().hex[:8]}",
                    gate_name="identity",
                    category=IssueCategory.IDENTITY,
                    severity=IssueSeverity.WARNING,
                    description=f"Active character '{char}' not mentioned in draft",
                    fixable=True,
                    fix_guidance=f"Include character '{char}' in the narrative",
                ))

        return QualityGateResult(
            gate_result_id=f"qgr_{uuid.uuid4().hex[:12]}",
            gate_name="identity",
            trace_id=draft.trace_id,
            snapshot_id=draft.snapshot_id,
            writer_draft_id=draft.draft_id,
            passed=not any(i.severity == IssueSeverity.ERROR for i in issues),
            issues=issues,
            error_count=sum(1 for i in issues if i.severity == IssueSeverity.ERROR),
            warning_count=sum(1 for i in issues if i.severity == IssueSeverity.WARNING),
        )


class SceneGate:
    """Checks scene and CardState fact consistency."""

    def check(self, draft: WriterDraft, snapshot: RoundSnapshot) -> QualityGateResult:
        issues = []

        # Check scene location consistency
        scene_location = snapshot.card_state.scene_state.location
        if scene_location and scene_location not in draft.text and len(draft.text) > 200:
            issues.append(QualityIssue(
                issue_id=f"qi_{uuid.uuid4().hex[:8]}",
                gate_name="scene",
                category=IssueCategory.SCENE,
                severity=IssueSeverity.WARNING,
                description=f"Scene location '{scene_location}' not reflected in draft",
                fixable=True,
                fix_guidance=f"Reference the scene location '{scene_location}'",
            ))

        return QualityGateResult(
            gate_result_id=f"qgr_{uuid.uuid4().hex[:12]}",
            gate_name="scene",
            trace_id=draft.trace_id,
            snapshot_id=draft.snapshot_id,
            writer_draft_id=draft.draft_id,
            passed=not any(i.severity == IssueSeverity.ERROR for i in issues),
            issues=issues,
            error_count=sum(1 for i in issues if i.severity == IssueSeverity.ERROR),
            warning_count=sum(1 for i in issues if i.severity == IssueSeverity.WARNING),
        )


class LengthGate:
    """Checks minimum and maximum text length.

    Short text is a blocking error here. The writer-specific 1000-character
    policy is handled separately in PersistentTurnEngine._quality_check.
    """

    def __init__(self, min_length: int = 250, max_length: int = 10000):
        self.min_length = min_length
        self.max_length = max_length

    def check(self, draft: WriterDraft) -> QualityGateResult:
        issues = []
        length = len(draft.text)

        if length < self.min_length:
            issues.append(QualityIssue(
                issue_id=f"qi_{uuid.uuid4().hex[:8]}",
                gate_name="length",
                category=IssueCategory.LENGTH,
                severity=IssueSeverity.ERROR,
                description=f"Text length {length} below minimum {self.min_length}",
                fixable=True,
                fix_guidance=f"Expand the text to at least {self.min_length} characters",
            ))

        if length > self.max_length:
            issues.append(QualityIssue(
                issue_id=f"qi_{uuid.uuid4().hex[:8]}",
                gate_name="length",
                category=IssueCategory.LENGTH,
                severity=IssueSeverity.WARNING,
                description=f"Text length {length} exceeds maximum {self.max_length}",
                fixable=True,
                fix_guidance=f"Trim the text to {self.max_length} characters or fewer",
            ))

        return QualityGateResult(
            gate_result_id=f"qgr_{uuid.uuid4().hex[:12]}",
            gate_name="length",
            trace_id=draft.trace_id,
            snapshot_id=draft.snapshot_id,
            writer_draft_id=draft.draft_id,
            passed=not any(i.severity == IssueSeverity.ERROR for i in issues),
            issues=issues,
            error_count=sum(1 for i in issues if i.severity == IssueSeverity.ERROR),
            warning_count=sum(1 for i in issues if i.severity == IssueSeverity.WARNING),
        )


class FormatGate:
    """Checks format compliance and content leaks."""

    def check(self, draft: WriterDraft) -> QualityGateResult:
        issues = []
        text = draft.text

        # Check for JSON leaks — look for actual JSON object patterns,
        # not just any brace+colon (which triggers on {{user}}, XML tags, etc.)
        import re as _re
        _json_like = _re.compile(r'\{\s*"[^"]+"\s*:\s*(?:"|-?\d|\[|\{|true|false|null)')
        _m = _json_like.search(text)
        if _m:
            issues.append(QualityIssue(
                issue_id=f"qi_{uuid.uuid4().hex[:8]}",
                gate_name="format",
                category=IssueCategory.CONTENT_LEAK,
                severity=IssueSeverity.ERROR,
                description="Text contains JSON-like content",
                evidence=text[max(0, _m.start()-20):_m.end()+20],
                fixable=True,
                fix_guidance="Remove all JSON, debug info, and system statements",
            ))

        # Check for debug markers
        debug_markers = ["DEBUG", "TODO", "FIXME", "```", "print(", "console.log"]
        for marker in debug_markers:
            if marker in text:
                issues.append(QualityIssue(
                    issue_id=f"qi_{uuid.uuid4().hex[:8]}",
                    gate_name="format",
                    category=IssueCategory.CONTENT_LEAK,
                    severity=IssueSeverity.ERROR,
                    description=f"Text contains debug marker: '{marker}'",
                    evidence=marker,
                    fixable=True,
                    fix_guidance=f"Remove '{marker}' from the text",
                ))

        # Check for tool call text
        tool_markers = ["tool_call", "function_call", "```json", "```python"]
        for marker in tool_markers:
            if marker in text.lower():
                issues.append(QualityIssue(
                    issue_id=f"qi_{uuid.uuid4().hex[:8]}",
                    gate_name="format",
                    category=IssueCategory.CONTENT_LEAK,
                    severity=IssueSeverity.ERROR,
                    description=f"Text contains tool call text: '{marker}'",
                    evidence=marker,
                    fixable=True,
                    fix_guidance="Remove all tool call text from the narrative",
                ))

        return QualityGateResult(
            gate_result_id=f"qgr_{uuid.uuid4().hex[:12]}",
            gate_name="format",
            trace_id=draft.trace_id,
            snapshot_id=draft.snapshot_id,
            writer_draft_id=draft.draft_id,
            passed=not any(i.severity == IssueSeverity.ERROR for i in issues),
            issues=issues,
            error_count=sum(1 for i in issues if i.severity == IssueSeverity.ERROR),
            warning_count=sum(1 for i in issues if i.severity == IssueSeverity.WARNING),
        )


class QualityPipelineRuntime:
    """Unified quality checking pipeline.

    Runs all gates and aggregates results.
    Only accepted drafts can proceed to state/memory commits.
    """

    def __init__(
        self,
        identity_gate: IdentityGate | None = None,
        scene_gate: SceneGate | None = None,
        length_gate: LengthGate | None = None,
        format_gate: FormatGate | None = None,
    ):
        self.identity_gate = identity_gate or IdentityGate()
        self.scene_gate = scene_gate or SceneGate()
        self.length_gate = length_gate or LengthGate()
        self.format_gate = format_gate or FormatGate()

    def check(
        self,
        draft: WriterDraft,
        snapshot: RoundSnapshot,
    ) -> QualityDecision:
        """Run all quality gates and aggregate results.

        Returns QualityDecision with verdict and all issues.
        """
        # Run all gates
        gate_results = [
            self.identity_gate.check(draft, snapshot),
            self.scene_gate.check(draft, snapshot),
            self.length_gate.check(draft),
            self.format_gate.check(draft),
        ]

        # Aggregate issues
        all_issues = []
        for result in gate_results:
            all_issues.extend(result.issues)

        # Determine verdict
        # NOTE: Only ERROR-level issues block the turn. WARNING-level issues
        # are diagnostic — they are recorded but do NOT trigger REVISE.
        # This ensures the turn can complete even if the Writer's output
        # doesn't mention every active NPC or scene location.
        has_errors = any(i.severity == IssueSeverity.ERROR for i in all_issues)

        if has_errors:
            verdict = QualityVerdict.REVISE
        else:
            verdict = QualityVerdict.ACCEPTED

        # Build blocking reasons
        blocking_reasons = [
            i.description for i in all_issues if i.severity == IssueSeverity.ERROR
        ]
        warnings = [
            i.description for i in all_issues if i.severity == IssueSeverity.WARNING
        ]

        # Build checks summary
        checks = []
        for result in gate_results:
            checks.append({
                "name": result.gate_name,
                "passed": result.passed,
                "error_count": result.error_count,
                "warning_count": result.warning_count,
            })

        return QualityDecision(
            trace_id=draft.trace_id,
            source_turn_id=draft.snapshot_id,
            verdict=verdict,
            candidate_text=draft.text,
            blocking_reasons=blocking_reasons,
            warnings=warnings,
            checks=checks,
            overall_score=1.0 if not has_errors else 0.0,
            retry_allowed=True,
            max_retries=1,
        )
