# Delegation Policy

## Allowed Sub-Agent Roles

| Role | Purpose |
|---|---|
| `rp-critic` | Check consistency, quality, character voice |
| `rp-memory-curator` | Identify memory candidates |
| `rp-state-updater` | Propose state changes |
| `worldbook-researcher` | Search worldbook for relevant entries |
| `continuity-checker` | Check timeline, location, knowledge consistency |

## Constraints

- Maximum 5 sub-agents per turn
- Maximum 10 tool calls per sub-agent
- Maximum 2000 result tokens per sub-agent
- No recursive delegation (sub-agents cannot spawn sub-agents)
- Sub-agents cannot write to any store
- Sub-agents return AgentSuggestion with evidence

## Delegation Modes

- `none`: No sub-agents needed
- `history_and_opportunity`: Complex turn with history and opportunities
- `continuity_check`: Need to verify consistency
- `full_review`: Complex turn requiring multiple perspectives

## Budget Policy

- Maximum 50,000 tokens per turn
- Maximum 10 LLM calls per turn
- Maximum 3 concurrent sub-agents
