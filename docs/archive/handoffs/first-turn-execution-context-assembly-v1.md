# P-First Turn Execution & Context Assembly V1

## Summary

Implements the first formal RP turn execution for a bootstrapped Session. The system can now execute the complete chain from player input through Director/Writer/Quality/State/Turn/Memory to a final FirstTurnReceipt.

**Branch:** `feat/first-turn-execution-context-assembly-v1`
**Tag:** `first-turn-execution-context-assembly-v1`
**Tests:** 764 passing (53 new)

---

## Architecture

### Contracts (4 new)

| Contract | Schema ID | Purpose |
|----------|-----------|---------|
| `FirstTurnRequest` | `awp.rp.first-turn-request.v1` | Request to execute first formal turn |
| `FirstTurnContext` | `awp.rp.first-turn-context.v1` | Assembled context for Director/Writer |
| `OpeningContext` | `awp.rp.opening-context.v1` | Controlled OpeningRecord projection (NOT a TurnRecord) |
| `SessionBoundWorldbookRetrievalResult` | `awp.rp.session-bound-worldbook-retrieval-result.v1` | Explainable retrieval output |
| `FirstTurnReceipt` | `awp.rp.first-turn-receipt.v1` | Successful completion receipt |
| `FirstTurnFailure` | `awp.rp.first-turn-failure.v1` | Structured failure |
| `FirstTurnDiagnostics` | `awp.rp.first-turn-diagnostics.v1` | Step-level diagnostic info |

### Runtime (1 new)

| Module | Class | Purpose |
|--------|-------|---------|
| `runtime/first_turn_pipeline.py` | `FirstTurnPipeline` | Orchestrates the complete first turn execution |

### Nodes (8 new)

| Node Class | Display Name | Purpose |
|------------|-------------|---------|
| `AWPV2FirstTurnRequest` | AWP V2 首回合请求 | Create FirstTurnRequest contract |
| `AWPV2SessionReadyValidator` | AWP V2 会话就绪校验 | Validate session readiness |
| `AWPV2OpeningContextLoader` | AWP V2 开场上文加载 | Load OpeningContext from OpeningRecord |
| `AWPV2SessionBoundWorldbookRetriever` | AWP V2 会话绑定世界书检索 | Retrieve worldbook entries from binding |
| `AWPV2FirstTurnContextAssembler` | AWP V2 首回合上下文装配 | Assemble FirstTurnContext |
| `AWPV2FirstTurnReceipt` | AWP V2 首回合收据 | Produce receipt after successful turn |
| `AWPV2FirstTurnDiagnostics` | AWP V2 首回合诊断 | Output diagnostics |
| `AWPV2FirstTurnExecution` | AWP V2 首回合执行 | Combined end-to-end execution |

### Workflows (2 new)

| File | Purpose |
|------|---------|
| `workflows/official_first_turn_execution_v1.json` | Official ComfyUI workflow |
| `workflows/api/first_turn_execution_v1.api.json` | API workflow for testing |

### Test Scenarios (3 new)

| File | Scenario ID | Suite |
|------|------------|-------|
| `first_turn_normal_no_agent.json` | `first_turn_normal_no_agent` | first-turn |
| `first_turn_quality_reject.json` | `first_turn_quality_reject` | first-turn |
| `first_turn_session_not_ready.json` | `first_turn_session_not_ready` | first-turn |

---

## Answers to Required Questions

### 1. How does FirstTurn differ from OpeningRecord?

**OpeningRecord** is created during Session Bootstrap. It records the greeting context and is frozen (immutable). It is NOT a TurnRecord, does NOT trigger D6, and does NOT enter ActiveMemory or RagMemory.

**FirstTurn** is a formal RP turn executed after Bootstrap. It produces a TurnRecord, triggers D6 (possibly no-op), and can write to memory. The OpeningRecord is injected into the FirstTurn as `OpeningContext` — a controlled projection that the Writer can see but cannot confuse with a previous turn output.

### 2. How does FirstTurnRequest validate Session Binding?

The pipeline performs 4 identity checks:
1. **Session exists** — `binding_store.load(session_id)` returns non-None
2. **Session ready** — `binding.status == "ready"`
3. **Card identity match** — `binding.logical_card_id == request.expected_logical_card_id`
4. **Version match** — `binding.card_version == request.expected_card_version`
5. **Source hash match** — `binding.source_hash == request.expected_source_hash`

Any mismatch produces a structured `FirstTurnFailure` with the specific failure code.

### 3. How does RoundSnapshot represent first turn (no history, no memory)?

The RoundSnapshot is built with:
- `recent_turn_records = []` — empty list, not an error
- `active_memories = []` — empty list, not an error
- `rag_recall = []` — empty list, not an error
- `memory_budget_decision = {"disposition": "noop", "reason": "first_turn_no_memory"}`

These are marked as normal dispositions, not failures.

### 4. How does worldbook retrieval stay session-bound?

The `SessionBoundWorldbookRetriever` reads ONLY from the `WorldbookBinding` associated with the current session:
- Entries are classified as `bound` (candidate), `disabled`, or `deferred`
- Disabled entries are never activated
- Selective entries are deferred (not activated)
- Constant entries activate within a character budget (default 4000)
- The output includes `candidate_entry_ids`, `activated_entry_ids`, `rejected_entry_ids_with_reasons`, `budget_dropped_entry_ids` — fully explainable

### 5. Which Dynamic Agents can normally not execute in first turn?

All 5 agents (D1-D5) return `not_required` for typical first turns because:
- **D1 History** — no accepted TurnRecords to recall
- **D2 Opportunity** — no unresolved threads, no relationship tension
- **D3 World-Life** — no world state history
- **D4 Emotion/Relationship** — no relationship history
- **D5 Continuity** — no prior facts to check against

The pipeline architecture supports complex first turns where agents COULD be triggered (via Director delegation plan), but the trigger policies correctly return `should_trigger=False` for empty contexts.

### 6. What does Writer see? What can't it see?

**Writer sees:**
- `FinalTurnBrief` (narrative plan, constraints, opportunities)
- `RoundSnapshot` projection (player input, CardState, worldbook entries)
- `OpeningContext` projection (greeting content)

**Writer cannot see:**
- Raw Dynamic Agent outputs
- Store internals
- Original CardDefinition
- Original Worldbook full text
- Memory stores
- Tool gateway internals

### 7. How does reject guarantee zero side effects?

When Quality Gate rejects:
- `diag.outcome = "quality_rejected"`
- No `CardState.commit()` call
- No `TurnRecord.save()` call
- No D6 execution
- No memory writes
- Receipt is still produced (with `quality_verdict = "reject"`) for traceability

### 8. How does accept trigger State, Turn, D6, and Memory?

On Quality Gate accept:
1. **State Proposal** — generates proposed state changes
2. **CardState Commit** — writes state with revision increment
3. **TurnRecord Commit** — writes turn record (only if state commit succeeded)
4. **D6 Memory Curator** — evaluates memory candidates (typically no-op for first turn)
5. **Receipt** — produced with all commit statuses

### 9. How does retry prevent duplicate submissions?

- Each attempt has a unique `attempt_id`
- `CardStatePatch` uses a deterministic `patch_id` derived from `turn_id + attempt_id`
- `FakeCardStateStore.commit()` checks for duplicate `patch_id` and returns `DUPLICATE_PATCH`
- `FakeTurnRecordStore.save()` raises `DuplicateTurnError` for same `turn_id`

### 10. Real Comfy API scenarios

The API workflow `workflows/api/first_turn_execution_v1.api.json` supports:
- Template variables: `{{session_id}}`, `{{player_input}}`, `{{logical_card_id}}`, etc.
- Combined with bootstrap workflow for end-to-end testing
- Requires running ComfyUI instance (not run in CI by default)

### 11. Readiness for next phase

**Yes** — the system is ready to enter `P-Real Provider Boundary & First Playable RP Turn V1`:
- First turn pipeline is complete and tested
- All adapters are fake but structurally correct
- The pipeline can be wired to a real LLM provider by replacing the fake adapters
- State, Turn, and Memory commit paths are verified

---

## Files Changed

### New Files (17)

**Contracts:**
- `contracts/first_turn_request.py`
- `contracts/first_turn_context.py`
- `contracts/first_turn_receipt.py`
- `contracts/first_turn_diagnostics.py`

**Runtime:**
- `runtime/first_turn_pipeline.py`

**Nodes:**
- `nodes/first_turn_request_node.py`
- `nodes/session_ready_validator_node.py`
- `nodes/opening_context_loader_node.py`
- `nodes/session_bound_worldbook_retriever_node.py`
- `nodes/first_turn_context_assembler_node.py`
- `nodes/first_turn_receipt_node.py`
- `nodes/first_turn_diagnostics_node.py`
- `nodes/first_turn_execution_node.py`

**Workflows:**
- `workflows/official_first_turn_execution_v1.json`
- `workflows/api/first_turn_execution_v1.api.json`

**Tests:**
- `tests/test_first_turn.py`
- `tests/workflow_scenarios/first_turn_normal_no_agent.json`
- `tests/workflow_scenarios/first_turn_quality_reject.json`
- `tests/workflow_scenarios/first_turn_session_not_ready.json`

**Documentation:**
- `docs/handoffs/first-turn-execution-context-assembly-v1.md`

### Modified Files (6)

- `contracts/__init__.py` — added FirstTurn exports
- `runtime/__init__.py` — added FirstTurnPipeline export
- `runtime/node_diagnostic_specs.py` — added 8 new diagnostic specs
- `nodes/__init__.py` — registered 8 new nodes
- `tests/test_p1_nodes.py` — updated expected node count
- `tests/test_p2_nodes.py` — updated expected node count
- `tests/test_observability.py` — updated scenario counts
