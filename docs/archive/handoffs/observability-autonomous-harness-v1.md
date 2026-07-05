# P-Observability & Autonomous Workflow Test Harness V1 — Handoff

## Phase
P-Observability & Autonomous Workflow Test Harness V1

## Branch
feat/observability-autonomous-harness-v1

## HEAD
3f4b2ee

## Tag
observability-autonomous-harness-v1

## Test Count
680 passed (615 existing + 65 new)

## Baseline
Branched from feat/card-import-normalization-v1 @ a1b14e5 (card-import-normalization-v1.1)

---

## Goals Achieved

1. **Three-Layer Status Model**: Every NodeExecutionRecord carries executionStatus, businessDisposition, semanticHealth
2. **Run Correlation**: WorkflowRunContext binds workflowRunId / traceId / turnId / attemptId / promptId without conflation
3. **Trace Data Model**: 8 new contracts for machine-readable diagnostic results
4. **Node Tracing Wrapper**: @awp_trace_node decorator + DiagnosticCollector, observational only
5. **Node Diagnostic Specs**: Registry of 25+ critical node specifications with enforced vs observational checks
6. **Data Redaction**: Three-level redaction (summary/redline/raw), never exposes sensitive data
7. **Scenario System**: 7 declarative JSON scenarios, deterministic assertion engine
8. **ComfyUI API Client**: HTTP/WS client for real E2E testing
9. **Diagnostic API**: Read-only programmatic access to run diagnostics
10. **CI**: GitHub Actions for push/PR and nightly runs
11. **Scripts**: PowerShell scripts for local E2E and scheduled task registration
12. **Documentation**: Testing guide and AI failure triage guide

---

## New Contracts (8 files)

| File | schemaId |
|------|----------|
| `contracts/workflow_run_record.py` | awp.rp.workflow-run-record.v1 |
| `contracts/node_execution_record.py` | awp.rp.node-execution-record.v1 |
| `contracts/node_contract_check.py` | awp.rp.node-contract-check.v1 |
| `contracts/node_diagnostic_spec.py` | awp.rp.node-diagnostic-spec.v1 |
| `contracts/trace_artifact_ref.py` | awp.rp.trace-artifact-ref.v1 |
| `contracts/workflow_test_result.py` | awp.rp.workflow-test-result.v1 |
| `contracts/workflow_test_failure.py` | awp.rp.workflow-test-failure.v1 |
| `contracts/workflow_test_scenario.py` | awp.rp.workflow-test-scenario.v1 |

---

## Runtime Modules (4 files)

| File | Purpose |
|------|---------|
| `runtime/awp_trace_wrapper.py` | DiagnosticCollector, @awp_trace_node, AWPTraceableNodeMixin, mark_node_not_reached/blocked |
| `runtime/node_diagnostic_specs.py` | NODE_DIAGNOSTIC_SPECS registry (25+ nodes) |
| `runtime/diagnostic_redactor.py` | DiagnosticRedactor, DiagnosticSummaryBuilder, ArtifactRetentionPolicy |
| `runtime/diagnostic_api.py` | DiagnosticAPI — read-only local diagnostic interface |

---

## Testing Infrastructure (10 files)

| File | Purpose |
|------|---------|
| `testing/workflow_scenario_runner.py` | WorkflowScenarioRunner, FakeScenarioExecutor |
| `testing/scenario_fixture_factory.py` | Load scenario definitions from JSON |
| `testing/scenario_assertion_engine.py` | Deterministic assertion runner |
| `testing/scenario_report_writer.py` | Write run.json, timeline.json, junit.xml, report.md |
| `testing/comfy_api_client.py` | HTTP client for ComfyUI /prompt, /history |
| `testing/api_workflow_loader.py` | Load/validate API workflow JSON files |
| `testing/api_workflow_fixture_patcher.py` | Inject test fixtures into API workflows |
| `testing/comfy_websocket_collector.py` | Collect WS execution events |
| `testing/comfy_history_collector.py` | Parse /history responses |
| `testing/comfy_api_scenario_runner.py` | ComfyApiScenarioExecutor for real E2E |
| `testing/run_workflow_scenarios.py` | CLI entry point |

---

## Scenario List (7 scenarios)

| ID | Description | Suite |
|----|-------------|-------|
| card_import_safe_json | Legal card import, staged → approved → ready, zero side effects | smoke |
| conditional_worldbook_branch | Flag-based worldbook branching, first-match-wins | smoke |
| dynamic_agent_not_required | Low-risk input, no unnecessary agents started | smoke |
| quality_reject_zero_side_effect | Quality reject → zero writes on all commit nodes | smoke |
| accepted_turn_with_memory_curation | Accept → commit → curate, auditable memory writes | smoke |
| retry_idempotency | Same turn retry, no duplicate writes, attemptId distinction | smoke |
| upstream_failure_propagation | Upstream fail → downstream blocked_by_upstream_failure | smoke |

---

## Node Tracing Strategy

**Mechanism**: `@awp_trace_node(collector)` decorator

**Wrapped nodes**: Only AWP-owned nodes (via explicit opt-in)

**Wrapper does**:
1. Record start time
2. Build redacted input summary
3. Call original node function
4. Build redacted output summary
5. Run observational contract checks
6. Record exception summary if any
7. Save NodeExecutionRecord
8. Return original result unchanged

**Wrapper never**:
- Changes inputs/outputs/return types
- Changes wiring, caching, or commit behavior
- Swallows original exceptions

---

## Redaction Rules

| Level | Name | Default | Content |
|-------|------|---------|---------|
| 1 | Summary | YES | Type, length, hash only |
| 2 | Redline | NO | Key IDs, revision, status, count, reason codes |
| 3 | Raw | NO | Full artifacts, local only |

**Never exposed at any level**: API keys, tokens, cookies, system prompts, full card text, full player input, full prompt, full RAG text, raw model chain-of-thought.

---

## ComfyUI E2E Configuration

- API workflows live in `workflows/api/*.api.json`
- Test fixtures injected via `APIWorkflowFixturePatcher`
- ComfyUI WebSocket events collected via `ComfyWebSocketCollector`
- History queried via `ComfyHistoryCollector`
- Exit code 2 if ComfyUI not available

---

## CI Configuration

**`.github/workflows/ci.yml`**:
- Triggers: push, pull_request, workflow_dispatch
- Matrix: Python 3.10, 3.11, 3.12
- Jobs: unit tests + smoke scenario suite
- No GPU, no real ComfyUI, no real models, no API keys

**`.github/workflows/nightly-scenarios.yml`**:
- Daily at 18:17 UTC = 03:17 Asia/Tokyo
- All test suites (smoke + integration)
- Uploads test artifacts (7-day retention)

---

## Local Scripts

**`scripts/run_awp_comfy_e2e.ps1`**:
- Connects/verifies local ComfyUI
- Runs comfy-api-e2e suite
- Writes local reports
- Returns correct exit code

**`scripts/register_awp_comfy_e2e_task.ps1`**:
- Creates optional Windows Task Scheduler job
- Default: daily at 03:17 Asia/Tokyo local (18:17 UTC previous day)
- Must be explicitly run — not auto-registered
- Does not access real models, commit code, or modify main

---

## What Runs Unattended

| Where | What | Requires |
|-------|------|----------|
| push/PR (CI) | pytest + smoke suite | Nothing (pure Python) |
| Nightly (CI) | pytest + smoke + integration | Nothing (pure Python) |
| Scheduled task (local) | comfy-api-e2e suite | Local ComfyUI |

---

## What Requires Real ComfyUI

- `comfy-api-e2e` suite only
- Exit code 2 if not available
- Still uses fake adapters (no real models)

---

## What AI Can Read

- `failures.json`, `timeline.json`, `node-records.json`
- `state-diff.json`, `memory-diff.json`
- `report.md`, `run.json`
- Diagnostic API (programmatic)

## What AI Must NOT Read

- Full card text, worldbook text, player input
- System prompts, API keys, tokens
- Raw model chain-of-thought

---

## Real ComfyUI API Acceptance

Verified against live ComfyUI 0.3.62 (RTX 3060):

| Check | Result |
|-------|--------|
| AWP nodes discovered | 77 nodes via /object_info |
| Critical nodes present | All found |
| Smoke workflow | SUCCESS |
| card_import_safe_json | SUCCESS |
| quality_reject_zero_side_effect | SUCCESS |
| retry_idempotency | SUCCESS |

Run: `python -m awp_rp_runtime_v2.testing.real_comfy_acceptance`

## Time Configuration

| System | Time | Timezone |
|--------|------|----------|
| GitHub nightly cron | 18:17 | UTC |
| Windows scheduled task | 03:17 | Asia/Tokyo local |

Both fire at the same absolute moment.

---

## Known Limitations

1. API workflow JSON files for real ComfyUI E2E not yet created (placeholder structure only)
2. WebSocket collector is a stub — real WS connection not implemented in V1
3. Diagnostic API is programmatic only (no HTTP server)
4. No MCP tool mapping yet (interface designed for future mapping)
5. ConditionalWorldbook node not in registered nodes (spec registered but no ComfyUI node yet)

---

## Next Phase Recommendation

**P-AutoTriage Agent V1**: AI agent that reads structured diagnostic evidence from this harness and proposes fixes. The evidence format is already designed for AI consumption.

**CardSession Bootstrap & Worldbook Binding V1**: The observability infrastructure is ready to trace card import → session binding → worldbook binding flows.

---

## Architecture Constraints (Must Not Regress)

1. Trace write failure ≠ Writer failure ≠ CardState Commit failure ≠ TurnRecord Commit failure ≠ Memory Commit rollback
2. Commit Runtime receipt must maintain existing business audit & idempotency semantics
3. Trace system must be observational only — never change node business results
4. No global monkeypatch of ComfyUI nodes
5. All test pass/fail decisions by deterministic rules, never by LLM
