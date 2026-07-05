# M1: Three-Layer Memory Foundation V1 — Delivery Report

## 1. Current State

| Item | Value |
|------|-------|
| Branch | `master` |
| HEAD | `4ffea0e8` (ComfyUI upstream) |
| Working tree | `awp-demo-turn-lifecycle-v2/` subtree, untracked under upstream `custom_nodes/` |
| Git user | `SDRTIO-bit` |

## 2. P1–P3 Baseline Test Results

```
174 passed (pre-M1 baseline, all P1–P3 tests green)
```

After M1 implementation: **204 passed** (174 baseline + 30 new M1 tests), **0 failed, 0 skipped**.

## 3. M1 New & Modified Files

### New (27 files)

| Layer | File | Purpose |
|-------|------|---------|
| contracts | `active_memory.py` | `ActiveMemoryRecord` v1 (20+ fields, kind/status enums, backward-compat aliases) |
| contracts | `rag_memory.py` | `RagMemoryRecord` v1 (scope/status/enums, entity/alias/tag keys) |
| contracts | `accepted_turn_window.py` | `AcceptedTurnWindow` + `select_accepted_window` (L1) |
| contracts | `turn_record_reference.py` | `TurnRecordReference` compact view |
| contracts | `memory_context_budget.py` | `BudgetDecision` / `MemoryContextBudget` |
| contracts | `active_memory_proposal.py` | `ActiveMemoryProposal` (future MemoryCurator) |
| contracts | `memory_retention_decision.py` | `RetentionDecision` / `MemoryRetentionResult` |
| contracts | `memory_recall_request.py` | `MemoryRecallRequest` (entity/alias/tag/status/scope filters) |
| contracts | `memory_recall_result.py` | `MemoryRecallResult` / `RecallHit` (score/hit_reasons/provenance/conflict_status) |
| contracts | `memory_evidence.py` | `MemoryEvidence` provenance binding |
| runtime | `active_memory_recall_runtime.py` | Deterministic L2 recall wrapper |
| runtime | `rag_recall_runtime.py` | Deterministic L3 recall (FTS5 + `EmbeddingRetrievalAdapter` protocol reserved) |
| runtime | `memory_context_assembler.py` | Priority-fixed assembly + `ConflictSignal` deterministic conflict adjudication |
| storage | `sqlite/recall_log_store.py` | `SqliteRecallLogStore` + `SqliteRetentionDecisionStore` |
| nodes | `accepted_turn_window_node.py` | `AWPV2AcceptedTurnWindow` |
| nodes | `active_memory_recall_node.py` | `AWPV2ActiveMemoryRecall` |
| nodes | `rag_memory_recall_node.py` | `AWPV2RagMemoryRecall` |
| nodes | `memory_context_assembler_node.py` | `AWPV2MemoryContextAssembler` |
| nodes | `memory_commit_plan_node.py` | `AWPV2MemoryCommitPlan` |
| nodes | `active_memory_commit_node.py` | `AWPV2ActiveMemoryCommit` |
| nodes | `rag_memory_commit_node.py` | `AWPV2RagMemoryCommit` |
| nodes | `memory_diagnostics_node.py` | `AWPV2MemoryDiagnostics` |
| tests | `test_m1_memory_foundation.py` | 30 tests covering M1 #1–#28 + E2E |
| workflows | `official_memory_runtime_v2.json` | 15-node official memory runtime workflow |

### Modified (14 files)

| Layer | File | Change |
|-------|------|--------|
| contracts | `memory_commit_plan.py` | Upgraded to use `ActiveMemoryRecord`/`RagMemoryRecord`; added `trace_id`/`expected_card_state_revision`/`memory_commit_id`/`idempotency_key`/`quality_decision_ref`; new `MemoryCommitRequest`/`Receipt`/`Result`/`Status` |
| contracts | `round_snapshot.py` | Added `memory_recall_diagnostics` + `memory_budget_decision` fields |
| runtime | `round_snapshot_builder.py` | Wired `AcceptedTurnWindow` + `ActiveMemoryRecallRuntime` + `RagMemoryRecallRuntime` + `MemoryContextAssembler`; produces diagnostics + budget |
| runtime | `active_memory_commit_runtime.py` | Added `commit_request()` with full gate (accept/trace/CS/TR success), idempotency, 15-slot retention; legacy `commit()` preserved |
| runtime | `rag_memory_commit_runtime.py` | Same gate/idempotency/scope enforcement; legacy `commit()` preserved |
| runtime | `turn_orchestrator.py` | Steps 11–12 wired: `MemoryCommitPlan` + `ActiveMemoryCommit` + `RAGMemoryCommit` with `commit_request` |
| storage | `interfaces.py` | Added `get_active_count`/`set_status`/`touch_recall`/`recall`/`record_receipt`/`get_receipt_by_idempotency_key` to `ActiveMemoryStore`/`RagMemoryStore`; added `RecallLogStore`/`RetentionDecisionStore` |
| storage | `sqlite/database.py` | Migration v2: 14 ALTERs + FTS5 + 6 new tables |
| storage | `sqlite/active_memory_store.py` | Full rewrite with to_dict/from_dict, new columns, recall, receipts |
| storage | `sqlite/rag_memory_store.py` | Full rewrite with FTS5 + LIKE fallback (CJK), recall, receipts, scope |
| policies | `memory_policy.py` | Summary 30–80 chars; `retention_score` + `decide_retention`; priority constants |
| fakes | `fake_stores.py` | All new methods for `FakeActiveMemoryStore`/`FakeRagMemoryStore`; `FakeRecallLogStore`/`FakeRetentionDecisionStore` |
| fakes | `__init__.py` | Exports `FakeRecallLogStore`/`FakeRetentionDecisionStore` |
| nodes | `__init__.py` | Registered 8 M1 nodes (22 total) |
| tests | `test_p1_nodes.py` | Updated `all_expected` to include M1 nodes |
| tests | `test_p2_nodes.py` | Updated node count 14 → 22 |

## 4. L1 / L2 / L3 Data Contracts

### L1: AcceptedTurnWindow

```
accepted_turn_window.py: AcceptedTurnWindow
  - card_id, session_id, snapshot_id, window_size (default 5)
  - turns: list[TurnRecord] — full, never truncated, most-recent first
  - references: list[TurnRecordReference]
  - select_accepted_window(turns, limit) — stable sort by turn_index DESC
  - _is_accepted: turn_id non-empty (store only persists accepted)
```

### L2: ActiveMemoryRecord

```
active_memory.py: ActiveMemoryRecord (frozen=True)
  - memory_id, card_id, session_id
  - summary (30–80 Unicode chars, M1 formal name)
  - kind: ActiveMemoryKind enum (10 values)
  - entity_refs, source_turn_ids, source_snapshot_ids, source_card_state_revision
  - importance, confidence (0–1)
  - status: ActiveMemoryStatus enum (active/resolved/superseded/expired/evicted/conflicted)
  - resolved_at, expires_at, retention_reason, merge_reason, eviction_reason
  - created_at, updated_at, last_recalled_at, recall_count
  - Backward-compat: content→summary, memory_type→kind, entities→entity_refs, source_turn_id→source_turn_ids[0], state_version→source_card_state_revision
```

### L3: RagMemoryRecord

```
rag_memory.py: RagMemoryRecord (frozen=True)
  - memory_id, card_id, session_id
  - scope: RagMemoryScope enum (session / card_global)
  - content, summary
  - entity_refs, aliases, event_tags, location_tags, time_tags, relationship_tags
  - source_turn_ids, source_card_state_revision
  - importance, confidence
  - status: RagMemoryStatus enum (active/resolved/expired/superseded/conflicted)
  - resolved_at, expires_at, created_at, updated_at, last_recalled_at, recall_count
  - provenance, evidence
  - Backward-compat: entities→entity_refs, time_range→time_tags, source_turn_id→source_turn_ids[0], etc.
```

## 5. ActiveMemory 15-Slot Retention Rules

**Retain (high score):**
- Unresolved threads, promises, secrets/misunderstandings
- Relationship shifts, emotional trends, explicit unfinished player goals
- High-importance scene pressure with source evidence
- Active status, high importance + confidence, entity-bound

**Evict (low score):**
- Resolved (score −100), expired, conflicted, superseded, evicted
- No entity refs, low importance, long unrecalled
- Scored by `MemoryPolicy.retention_score()` — deterministic, no randomness

**Mechanism:** After every commit, if `get_active_count > 15`, `decide_retention()` scores all active memories, evicts lowest until ≤15, logs to `MemoryRetentionResult` and `RetentionDecisionStore`.

## 6. RAG Retrieval, Filtering, Sorting & Conflict Downgrade

### Retrieval
- V1: SQLite FTS5 (trigram tokenizer) with LIKE fallback for 2-char CJK tokens
- Query split into individual terms OR'd together
- `EmbeddingRetrievalAdapter` protocol reserved (not used in M1)

### Filters
- `entity_refs`, `aliases`, `event_tags`, `location_tags`, `time_tags`, `relationship_tags`
- `status` filter (default: active only)
- `scope` filter (session / card_global)
- `min_importance`, `min_confidence`
- `exclude_stale` (resolved/expired/conflicted excluded by default)

### Sorting
- FTS5 path: bm25 score DESC → importance DESC → confidence DESC
- LIKE fallback: importance DESC → confidence DESC → created_at DESC

### Conflict Downgrade
- `MemoryContextAssembler` applies `ConflictSignal` rules:
  - Entity overlap + negated term in summary/content → `conflicted` (L2) or `ignored` (L3), removed from high-priority context, recorded in diagnostics
- `source_card_state_revision < current.revision` → `stale` (downgraded, ranked lower)
- CardState hard facts always win — no LLM judgement

## 7. Memory Commit Gate, Idempotency & Retry

### Gate chain (zero side effects on any block)
1. `quality_decision is None` → `BLOCKED_NO_GATE`
2. `not is_accepted()` → `BLOCKED_GATE_NOT_ACCEPT`
3. `trace_id` mismatch → `BLOCKED_TRACE_MISMATCH`
4. `card_state_commit_success=False` → `BLOCKED_CARD_STATE`
5. `turn_record_commit_success=False` → `BLOCKED_TURN_RECORD`
6. Plan validation fails → `BLOCKED_VALIDATION`

### Idempotency
- `idempotency_key` unique per `(card_id, session_id)`
- Replay returns original `MemoryCommitReceipt` with `IDEMPOTENT_REPLAY` status
- `memory_commit_id` changes for each retry attempt

### Retry
- Failed attempt (gate reject/revise) → zero writes
- Successful attempt (gate accept) → writes once with new `memory_commit_id`/`idempotency_key`
- Same `idempotency_key` replay → zero writes (idempotent)

## 8. RoundSnapshot Memory Context Composition

```
RoundSnapshot (frozen, immutable):
  - recent_turn_records: last ≤5 accepted TurnRecords (L1, full, never truncated)
  - active_memories: recalled L2 (≤15, with conflict_status/diagnostics)
  - rag_recall: recalled L3 (≤10, with conflict_status/diagnostics)
  - memory_recall_diagnostics: per-memory RecallDiagnostics (layer/ priority/ rank/ score/ conflict_status/ kept/ drop_reason)
  - memory_budget_decision: BudgetDecision (l1_turns_used/ active_memories_used/ rag_used/ trimmed)
  - active_worldbook_entries: worldbook (lowest priority)

Priority order (hard, fixed in assembler):
  CardState > L1 > ActiveMemory > high-conf RAG > ordinary RAG > worldbook

Budget rules:
  - L1 NEVER truncated (even 5th turn kept whole)
  - Cut low-priority RAG first → worldbook → (L1 untouched)
```

## 9. SQLite Tables, Indexes, Constraints & Migration

### Migration v1 (existing)
8 tables: `schema_migrations`, `card_states`, `card_state_patch_receipts`, `turn_records`, `round_snapshots`, `execution_traces`, `active_memory_records`, `rag_memory_records`

### Migration v2 (M1)
**ALTER TABLE active_memory_records** — 14 new columns:
`kind`, `summary`, `importance`, `confidence`, `source_card_state_revision`, `source_turn_ids_json`, `entity_refs_json`, `created_at`, `last_recalled_at`, `recall_count`, `resolved_at`, `expires_at`, `eviction_reason`, `retention_reason`

**ALTER TABLE rag_memory_records** — 14 new columns:
`scope`, `status`, `summary`, `importance`, `confidence`, `source_card_state_revision`, `source_turn_ids_json`, `entity_refs_json`, `aliases_json`, `tags_json`, `updated_at`, `last_recalled_at`, `recall_count`, `provenance`

**New FTS5 table:**
`rag_memory_fts` (trigram tokenizer, synced via INSERT/DELETE in store)

**New tables (6):**
- `active_memory_commit_receipts` — PK `(card_id, session_id, idempotency_key)`, unique on `(card_id, session_id, memory_commit_id)`
- `rag_memory_commit_receipts` — same structure
- `memory_recall_logs` — audit log, indexed by `(card_id, session_id, created_at)`
- `memory_retention_decisions` — audit log, indexed by `(card_id, session_id, turn_id)`

**Key constraints:**
- `(card_id, session_id, memory_id)` unique for active memory (PK)
- Active count ≤15 enforced by `MemoryPolicy.decide_retention()`
- `(card_id, session_id, idempotency_key)` unique for receipts
- `cardId + sessionId` isolation enforced at every query

## 10. ComfyUI Nodes & Official Workflow

### 8 M1 Nodes (22 total registered)

| Node Class | Display Name | INPUT_TYPES (required) | OUTPUT_SCHEMA_ID |
|------------|-------------|----------------------|-----------------|
| `AWPV2AcceptedTurnWindow` | 已接受回合窗口 | turn_records, card_id, session_id | `awp.rp.accepted-turn-window.v1` |
| `AWPV2ActiveMemoryRecall` | 活跃记忆召回 | active_memories, card_id, session_id | `awp.rp.memory-recall-result.v1` |
| `AWPV2RagMemoryRecall` | RAG记忆召回 | rag_memories, card_id, session_id | `awp.rp.memory-recall-result.v1` |
| `AWPV2MemoryContextAssembler` | 记忆上下文组装 | card_state, l1_turns, active_recall, rag_recall | `awp.rp.memory-context.v1` |
| `AWPV2MemoryCommitPlan` | 记忆提交计划 | round_snapshot, accepted_text, quality_decision, turn_id | `awp.rp.memory-commit-plan.v1` |
| `AWPV2ActiveMemoryCommit` | 活跃记忆提交 | memory_commit_plan, quality_decision, card_state_commit_result, turn_record_commit_result | `awp.rp.memory-commit-result.v1` |
| `AWPV2RagMemoryCommit` | RAG记忆提交 | (same 4 inputs) | `awp.rp.memory-commit-result.v1` |
| `AWPV2MemoryDiagnostics` | 记忆诊断 | round_snapshot | `awp.rp.memory-diagnostics.v1` |

All commit nodes explicitly receive QualityDecision, CardStateCommitResult, TurnRecordCommitResult, MemoryCommitPlan. Default no implicit side effects. Diagnostics in every output.

### Official Workflow: `workflows/official_memory_runtime_v2.json`

15 nodes, 24 links, visible in ComfyUI:
```
CardState Init → AcceptedTurnWindow → ActiveMemoryRecall → RagMemoryRecall
→ MemoryContextAssembler → RoundSnapshot → Director → Writer → QualityGate
→ CardStateCommit → TurnRecordCommit → MemoryCommitPlan
→ ActiveMemoryCommit → RagMemoryCommit → MemoryDiagnostics
```

## 11. Test Results

```
Command: python -m pytest -q -p no:cacheprovider
Result:  204 passed in 1.60s
Skipped: 0
Failed:  0
```

### M1 Test Coverage (30 tests)

| # | Scenario | Status |
|---|----------|--------|
| 1 | L1 only returns accepted turns | ✅ |
| 2 | L1 at most 5 | ✅ |
| 3 | 5th turn not truncated | ✅ |
| 4 | rejected/revise/failed not in L1 | ✅ |
| 5 | cardId isolation | ✅ |
| 6 | sessionId isolation | ✅ |
| 7 | ActiveMemory ≤15 | ✅ |
| 8 | Deterministic eviction at cap | ✅ |
| 9 | Resolved evicted first | ✅ |
| 10 | High-importance promise not ejected by low | ✅ |
| 11 | sourceTurnId + revision required | ✅ |
| 12 | FTS5 keyword recall (LIKE fallback for CJK) | ✅ |
| 13 | Entity/alias/tag filters | ✅ |
| 14 | No cross cardId/sessionId leak | ✅ |
| 15 | Stale downgraded by default | ✅ |
| 16 | RAG vs CardState conflict ignored | ✅ |
| 17 | Gate revise → zero write | ✅ |
| 18 | Gate reject → zero write | ✅ |
| 19 | Missing gate → zero write | ✅ |
| 20 | CardStateCommit failed → zero write | ✅ |
| 21 | TurnRecordCommit failed → zero write | ✅ |
| 22 | IdempotencyKey replay no duplicate | ✅ |
| 23 | Retry no duplicate memory | ✅ |
| 24 | Snapshot immutable + diagnostics | ✅ |
| 25 | Snapshot records recall diagnostics + budget | ✅ |
| 26 | L1 > L2 > L3 priority order | ✅ |
| 27 | All P1–P3 tests pass (174) | ✅ |
| 28 | Official memory workflow JSON valid | ✅ |
| E2E | 6 turns → snapshot → L1=5 → RAG sources → conflict → retry idempotent | ✅ |

## 12. Unimplemented But Reserved Interfaces

| Interface | Location | Status |
|-----------|----------|--------|
| `EmbeddingRetrievalAdapter` (vector retrieval) | `runtime/rag_recall_runtime.py` | Protocol defined, not used in M1 |
| `MemoryCuratorAgent` (free subagent) | `contracts/active_memory_proposal.py` | Proposal contract exists; M1 uses deterministic fixture in orchestrator |
| `HistoryRecallAgent` | — | Future work; recall is deterministic in M1 |
| `card_global` RAG scope | `contracts/rag_memory.py` + stores | Fully supported in schema; not auto-enabled (must be explicit) |
| `MemoryCommitReceipt` persistence (active + rag) | Tables + stores | Fully implemented; receipts survive restarts |

## 13. Phase Readiness

**M1 is complete.** All 28 required scenarios pass, plus the E2E integration test. The three-layer memory (L1/L2/L3) is fully wired into the formal turn chain with gate-gated, idempotent commits and deterministic retention.

**Ready for C1: Dual-Primary Agent & Tool Gateway Enhancement** (next phase).
