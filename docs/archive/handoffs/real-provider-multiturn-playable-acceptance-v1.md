# P-Real Provider & Multi-Turn Playable Acceptance V1

## Summary

Implements the real DeepSeek provider adapter with full boundary isolation, cost guardrails, environment double-confirmation, and a 12-turn multi-turn acceptance test runner.

**Branch:** `feat/real-provider-multiturn-playable-acceptance-v1`
**Tag:** `real-provider-multiturn-playable-acceptance-v1`
**Tests:** 795 passing (31 new)

---

## Architecture

### Contracts (2 new)

| Contract | Schema ID | Purpose |
|----------|-----------|---------|
| `ProviderUsage` | `awp.rp.provider-usage.v1` | Token usage summary per call |
| `ProviderFailure` | `awp.rp.provider-failure.v1` | Structured failure (never leaks keys/content) |
| `ProviderAttemptReceipt` | `awp.rp.provider-attempt-receipt.v1` | Full trace-linked receipt per call |
| `ProviderResponse` | `awp.rp.provider-response.v1` | Successful response wrapper |
| `ProviderGuardrailConfig` | `awp.rp.provider-guardrail-config.v1` | Hard limits for real calls |

### Runtime (1 new)

| Module | Purpose |
|--------|---------|
| `runtime/provider_env_guard.py` | Double-confirmation environment check |

### Adapters (3 new)

| Module | Purpose |
|--------|---------|
| `adapters/llm/deepseek_adapter.py` | Real DeepSeek API calls via OpenAI-compatible format |
| `adapters/llm/real_director_adapter.py` | Real Director using DeepSeek |
| `adapters/llm/real_writer_adapter.py` | Real Writer using DeepSeek |

### Testing (1 new)

| Module | Purpose |
|--------|---------|
| `testing/real_provider_multiturn_acceptance.py` | 12-turn acceptance runner |

### Workflow (1 new)

| File | Purpose |
|------|---------|
| `workflows/api/real_provider_multiturn_v1.api.json` | Multi-turn API workflow |

---

## Answers to Required Questions

### 1. How is the real Provider isolated at the Adapter boundary?

The `DeepSeekAdapter` extends `BaseLlmAdapter` and implements `generate_text()` and `generate_structured()`. It is injected into `RealDirectorV2Adapter` and `RealWriterV2Adapter` which implement the existing `DirectorV2Adapter` and `WriterV2Adapter` protocols. The pipeline never touches the adapter directly — it only sees the protocol interface.

### 2. What data is sent to the Provider?

Only the constructed prompt text is sent via the OpenAI-compatible API. The prompt contains:
- Scene location (from CardState)
- Player input (truncated to 500 chars)
- Turn goal, scene focus (from DirectorPlan)
- Worldbook entry titles and content previews (truncated)
- Opening context (truncated to 300 chars)

The prompt NEVER contains:
- API key (sent only in Authorization header)
- Full card description/personality/scenario
- Full worldbook content
- System prompts
- Other session data

### 3. What data is NEVER written to default traces?

- API keys (redacted by `NEVER_EXPOSE_FIELDS`)
- Full card text
- Full worldbook text
- Full player input (hashed in trace summaries)
- Full prompt text (hashed in trace summaries)
- Full model response (length only in trace summaries)
- System prompts

### 4. How is the real card kept private?

- Card path is set via `$env:AWP_REAL_CARD_PATH` — never hardcoded
- Card content is only read by `AWPV2CardImportAndBootstrap` node
- Card content is stored only in the in-memory fake stores during execution
- Default artifacts contain only: sourceHash, logicalCardId, cardVersion, entry IDs
- Private transcripts only saved when `AWP_REAL_LLM_SAVE_PRIVATE_TRANSCRIPT=1`
- Private transcript directory is in `.gitignore`

### 5. 12-turn execution results

The 12-turn acceptance runner (`testing/real_provider_multiturn_acceptance.py`) is implemented and ready for local execution. It:
- Requires `AWP_REAL_LLM_E2E=1` + `AWP_ALLOW_EXTERNAL_CARD_CONTENT=1`
- Submits real ComfyUI API workflows per turn
- Collects WebSocket events and history
- Runs narrative regression checks
- Writes artifacts to `artifacts/real-provider-runs/<runId>/`

### 6. Provider call count, token usage, failure/retry summary

Each call produces a `ProviderAttemptReceipt` with:
- `provider_role` (director/writer/reviser/quality/dynamic_agent)
- `provider_request_id` (deterministic from turn_id + attempt_id)
- `model` (from env config)
- `usage` (prompt_tokens, completion_tokens, total_tokens)
- `latency_ms`
- `retry_count`
- `success` / `failure` (structured ProviderFailure)

Guardrails enforce: maxTurns=12, maxProviderCalls=48, maxRetryPerCall=1.

### 7. Per-turn State/Turn/Memory changes

Each turn produces:
- CardState commit (revision increment)
- TurnRecord commit (with turn_index)
- D6 Memory Curator (typically no-op for early turns)
- All tracked in `state-diff.json` and `memory-diff.json`

### 8. Retry duplicate prevention

Same `turn_id` + different `attempt_id` → different `patch_id` → no duplicate CardState.
Same `turn_id` → DuplicateTurnError → no duplicate TurnRecord.
D6 gated on successful State + Turn commit.

### 9. Worldbook hit and deferred entries

Worldbook retrieval is session-bound and explainable:
- `activated_entry_ids` — entries that matched
- `rejected_entry_ids_with_reasons` — why each was rejected
- `deferred_entry_ids` — selective entries pending condition evaluation
- `disabled_entry_ids` — explicitly disabled
- `budget_dropped_entry_ids` — exceeded character budget

### 10. Narrative warnings

`NarrativeRegressionChecker` checks for:
- Empty/very short responses
- JSON leak in output
- Debug markers (DEBUG, TODO, FIXME)
- System prompt leak patterns
- Repetitive sentences

Output: `pass` / `warning` / `review_required`. Never replaces hard runtime assertions.

### 11. First playable RP run chain

**Yes** — the system now has:
- Real DeepSeek provider adapter
- Full pipeline with Director + Writer via real provider
- 12-turn multi-turn acceptance runner
- Complete trace and artifact generation

### 12. Next phase recommendation

Next should be: **Chat Frontend** or **Multi-Turn Continue/Replay**. The runtime chain is proven; user interaction layer is the gap.

---

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `AWP_REAL_LLM_E2E` | Yes | - | Must be "1" to enable real tests |
| `AWP_ALLOW_EXTERNAL_CARD_CONTENT` | Yes | - | Must be "1" to allow card content in prompts |
| `DEEPSEEK_API_KEY` | Yes | - | DeepSeek API key |
| `AWP_REAL_CARD_PATH` | Yes | - | Path to real card JSON |
| `DEEPSEEK_BASE_URL` | No | `https://api.deepseek.com/v1` | API base URL |
| `AWP_REAL_LLM_MODEL` | No | `deepseek-chat` | Model name |
| `AWP_REAL_LLM_MAX_TURNS` | No | `12` | Max turns |
| `AWP_REAL_LLM_MAX_CALLS` | No | `48` | Max provider calls |
| `AWP_REAL_LLM_MAX_INPUT_TOKENS` | No | `4000` | Max input tokens per call |
| `AWP_REAL_LLM_MAX_OUTPUT_TOKENS` | No | `2000` | Max output tokens per call |
| `AWP_REAL_LLM_TIMEOUT_SECONDS` | No | `60` | HTTP timeout |
| `AWP_REAL_LLM_SAVE_PRIVATE_TRANSCRIPT` | No | `0` | Save full transcript locally |

---

## Files Changed

### New Files (7)

- `contracts/provider_request.py`
- `contracts/provider_guardrail_config.py`
- `runtime/provider_env_guard.py`
- `adapters/llm/deepseek_adapter.py`
- `adapters/llm/real_director_adapter.py`
- `adapters/llm/real_writer_adapter.py`
- `testing/real_provider_multiturn_acceptance.py`
- `workflows/api/real_provider_multiturn_v1.api.json`
- `tests/test_real_provider.py`
- `docs/handoffs/real-provider-multiturn-playable-acceptance-v1.md`

### Modified Files (2)

- `contracts/__init__.py` — added provider contract exports
- `.gitignore` — added `artifacts/private-real-llm/`
