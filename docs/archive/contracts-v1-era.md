# Contracts Reference

## Schema IDs

| Contract | Schema ID | Version |
|---|---|---|
| CardState | `awp.rp.card-state.v1` | 1 |
| RoundSnapshot | `awp.rp.round-snapshot.v1` | 1 |
| TurnRecord | `awp.rp.turn-record.v1` | 1 |
| TurnBrief | `awp.rp.turn-brief.v1` | 1 |
| DelegationPlan | `awp.rp.delegation-plan.v1` | 1 |
| AgentTaskEnvelope | `awp.rp.agent-task-envelope.v1` | 1 |
| AgentSuggestion | `awp.rp.agent-suggestion.v1` | 1 |
| SuggestionMergeResult | `awp.rp.suggestion-merge-result.v1` | 1 |
| WriterContract | `awp.rp.writer-contract.v1` | 1 |
| QualityDecision | `awp.rp.quality-decision.v1` | 1 |
| StateUpdateProposal | `awp.rp.state-update-proposal.v1` | 1 |
| MemoryCommitPlan | `awp.rp.memory-commit-plan.v1` | 1 |
| ExecutionTrace | `awp.rp.execution-trace.v1` | 1 |

## Key Invariants

1. All contracts are serializable (to_dict / from_dict)
2. All contracts carry schema_id and schema_version
3. RoundSnapshot is frozen (immutable) once built
4. AgentSuggestion must carry evidence and source_refs
5. QualityDecision has explicit verdict (accepted/rejected)
6. StateUpdateProposal is a candidate patch (not yet committed)
7. ExecutionTrace records every event chronologically
