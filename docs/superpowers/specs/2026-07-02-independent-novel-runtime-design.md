# Independent Novel Runtime Design

Date: 2026-07-02

## Goal

Turn the current AWP RP Runtime V2 into an independent long-form novel runtime that can generate readable, satisfying web-novel chapters without depending on ComfyUI.

The first release is not trying to produce "masterpiece" prose. It should reliably produce chapters that:

- have a clear hook, event progression, payoff, and next-chapter pull
- preserve character, timeline, foreshadowing, and world facts
- avoid obvious AI writing artifacts, repetition, metadata leaks, and continuity breaks
- save all state in a durable, inspectable form

## Non-Goals

- Do not build a full commercial writing platform in the first release.
- Do not rewrite the storage layer from scratch.
- Do not keep ComfyUI as the primary execution model.
- Do not require users to manage all context manually in prompt files.
- Do not optimize for literary experimentation before continuity and chapter reliability work.

## Reference Project Findings

`worldwonderer/oh-story-claudecode` is a strong reference for long-form web-novel workflow design. It is not a runtime engine. Its useful ideas are:

- file-based novel project layout: `设定/`, `大纲/`, `正文/`, `追踪/`, `对标/`
- chapter outline before prose
- per-chapter state filtering: only load information that would cause this chapter to be wrong if missing
- after-writing tracking updates: foreshadowing, timeline, character state, context summary
- deterministic checks for length, metadata leaks, repeated titles, repeated text, and AI-like patterns
- separated roles: architect, narrative writer, consistency checker, explorer

The current AWP project should absorb those protocols as product behavior, not copy the skill package directly. AWP already has stronger foundations for persistence, agent orchestration, memory, quality gates, replay, and APIs.

## Architecture Direction

Use SQLite as the source of truth and Markdown as the user-facing project export/import format.

```
NovelProject
  -> VolumePlan
  -> ChapterPlan
  -> SceneBeat[]
  -> ChapterDraft
  -> QualityReview
  -> ContinuityCommit
  -> Markdown Export
```

The runtime owns the canonical objects. Markdown files mirror those objects so users can read, edit, back up, and version them.

## Package And Entry Points

The project remains Python-first, but ComfyUI becomes optional integration instead of the package identity.

Proposed package identity:

- distribution name: `awp-novel-runtime`
- import package: keep `awp_rp_runtime_v2` during migration, add `novel/` modules inside it first
- later optional rename: `awp_novel_runtime`

First-release entry points:

- CLI: `python -m awp_rp_runtime_v2.novel`
- API server: `python -m awp_rp_runtime_v2.novel.server`
- optional legacy Comfy nodes: kept but no longer required

## Data Model

### NovelProject

Represents one book.

Fields:

- `project_id`
- `title`
- `genre`
- `target_platform`
- `target_reader`
- `core_emotion`
- `one_sentence_pitch`
- `status`
- `created_at`
- `updated_at`

### VolumePlan

Represents a major arc or volume.

Fields:

- `volume_id`
- `project_id`
- `index`
- `title`
- `chapter_start`
- `chapter_end`
- `core_conflict`
- `emotional_arc`
- `major_payoffs`
- `foreshadowing_plan`

### ChapterPlan

This is the gate before prose. No first draft without a chapter plan.

Fields:

- `chapter_id`
- `project_id`
- `volume_id`
- `chapter_index`
- `title`
- `target_chars`
- `chapter_position`
- `target_emotion`
- `opening_hook`
- `main_payoff`
- `ending_hook`
- `summary_5_part`
- `plot_lines`
- `character_changes`
- `information_gap`
- `scene_beats`
- `cost_and_reward`

`chapter_position` supports values like:

- `high_pressure`
- `progression`
- `relationship`
- `setup`
- `cooldown`
- `information`

The point is to avoid forcing every chapter to behave like a climax while still giving every chapter a reason to continue.

### SceneBeat

A structured unit inside a chapter plan.

Fields:

- `beat_id`
- `chapter_id`
- `index`
- `purpose`
- `density`
- `budget_chars`
- `description`
- `required_facts`
- `payoff_refs`

`density` is `dense`, `normal`, or `sparse`. Dense beats carry the satisfying material: face-slap, reveal, reversal, emotional peak, danger, or payoff. Sparse beats bridge time, place, and setup.

### ChapterDraft

Represents a generated or revised chapter.

Fields:

- `draft_id`
- `chapter_id`
- `revision`
- `source_plan_revision`
- `text`
- `char_count`
- `status`
- `quality_decision_id`
- `created_at`

### ContinuityLedger

Replaces loose "memory" as the novel-facing continuity surface.

Logical sections:

- `character_state`
- `timeline_events`
- `foreshadowing_items`
- `world_rules`
- `relationship_state`
- `open_threads`

The ledger is backed by SQLite rows and exported to Markdown files.

## Markdown Project Layout

Exported projects follow an oh-story-compatible layout:

```
{book_title}/
├── 设定/
│   ├── 世界观/
│   ├── 角色/
│   ├── 势力/
│   ├── 关系.md
│   ├── 文风.md
│   └── 题材定位.md
├── 大纲/
│   ├── 大纲.md
│   ├── 卷纲_第001卷.md
│   └── 细纲_第001章.md
├── 正文/
│   └── 第001章_章名.md
├── 追踪/
│   ├── 上下文.md
│   ├── 伏笔.md
│   ├── 时间线.md
│   └── 角色状态.md
└── 对标/
```

Rules:

- SQLite is canonical.
- Markdown export is deterministic.
- Markdown import can update runtime state, but must produce a validation report before applying changes.
- Generated prose files must not contain internal plan terms outside the title line.

## Agent Roles

Reuse the current Director/Writer/sub-agent architecture, but remap roles for novel work.

### Architect

Builds and repairs high-level structure.

Responsibilities:

- book premise
- volume plan
- chapter plan
- hook/payoff/reversal design
- scene beat budget

### Chapter Writer

Writes prose from `ChapterWritePacket`.

Responsibilities:

- produce chapter text
- follow the chapter plan
- expand dense beats and compress sparse beats
- preserve style constraints
- avoid metadata leaks

### Continuity Checker

Read-only consistency checker.

Responsibilities:

- fact conflicts
- timeline conflicts
- character state drift
- unresolved or contradicted foreshadowing
- world-rule violations

### Style Cleaner

Can be implemented as a separate pass or folded into the quality pipeline.

Responsibilities:

- AI-like phrase detection
- repetition detection
- punctuation and paragraph sanity
- engineering-term leakage

### Ledger Curator

Equivalent to the current turn evolution curator, but chapter-aware.

Responsibilities:

- update character states
- update timeline
- mark foreshadowing as added, advanced, paid off, or stale
- add long-term recall records

## Main Flow

### Create Project

1. User provides title, genre, target platform, target emotion, and rough premise.
2. Runtime creates `NovelProject`.
3. Architect creates initial project bible:
   - topic positioning
   - main character skeleton
   - world skeleton
   - first volume plan
4. Runtime exports Markdown scaffold.

### Plan Chapter

1. Load project state and current volume.
2. Architect creates `ChapterPlan`.
3. Plan validator checks required fields:
   - target emotion
   - hook
   - main payoff or functional reason
   - ending pull
   - scene beats
   - character changes
   - budget total
4. If valid, persist plan and export `大纲/细纲_第XXX章.md`.

### Write Chapter

1. Build `ChapterWritePacket`:
   - chapter plan
   - previous chapter summary
   - relevant character states
   - relevant foreshadowing
   - relevant world constraints
   - style profile
   - benchmark snippets if available
2. Chapter Writer generates prose.
3. Quality pipeline runs deterministic and LLM-assisted checks.
4. If accepted, save `ChapterDraft`.
5. Ledger Curator updates continuity state.
6. Export prose and tracking Markdown.

### Revise Chapter

1. Load draft, chapter plan, previous/next chapter context, and ledger state.
2. User chooses full rewrite or targeted rewrite.
3. Runtime creates a new `ChapterDraft` revision.
4. Continuity impact is checked before ledger updates are committed.

## Quality Gates

First-release gates should be pragmatic.

Blocking:

- chapter text is below 90 percent of target length
- repeated text loop detected
- obvious truncation detected
- JSON, tool traces, prompt text, or debug text leaked
- internal words like `细纲`, `伏笔`, `本章`, `上一章`, `读者` appear in prose body without an allowed in-story reason
- chapter violates hard continuity facts

Warning:

- title duplicates an existing chapter title
- dense beats were under-expanded
- sparse beats were over-expanded
- ending hook is weak
- character state update is missing despite clear change
- style drift is detected

The acceptance target is "readable and satisfying", not "perfect". Warnings should be visible but should not block unless they compound into an obvious failure.

## Storage Migration

Add new SQLite tables alongside existing RP tables:

- `novel_projects`
- `novel_volumes`
- `novel_chapter_plans`
- `novel_scene_beats`
- `novel_chapter_drafts`
- `novel_ledger_items`
- `novel_quality_reviews`
- `novel_exports`

Existing RP stores should not be removed in phase one. The new novel layer can reuse:

- provider configuration
- model profile registry
- LLM adapters
- trace store concepts
- memory stores where useful
- quality decision contracts where compatible

## API Surface

First-release REST endpoints:

```
POST /api/novels
GET  /api/novels
GET  /api/novels/{project_id}

POST /api/novels/{project_id}/volumes
POST /api/novels/{project_id}/chapters/plan
GET  /api/novels/{project_id}/chapters/{chapter_index}/plan

POST /api/novels/{project_id}/chapters/{chapter_index}/draft
GET  /api/novels/{project_id}/chapters/{chapter_index}/drafts
POST /api/novels/{project_id}/chapters/{chapter_index}/revise

GET  /api/novels/{project_id}/ledger
POST /api/novels/{project_id}/export
POST /api/novels/{project_id}/import-markdown
```

CLI mirrors the same behavior:

```
python -m awp_rp_runtime_v2.novel create
python -m awp_rp_runtime_v2.novel plan-chapter
python -m awp_rp_runtime_v2.novel write-chapter
python -m awp_rp_runtime_v2.novel export
```

## Frontend

The existing management panel can be reused later, but the first implementation should not depend on frontend work.

Minimum UI later:

- project list
- chapter plan viewer/editor
- draft viewer
- ledger viewer
- export button

## Testing Strategy

Unit tests:

- chapter plan validation
- scene beat budget validation
- ledger update application
- Markdown export formatting
- metadata leak detection
- repetition detection

Integration tests:

- create project -> plan chapter -> write fake draft -> quality accept -> ledger update -> export
- chapter cannot be written without a valid plan
- accepted draft creates deterministic Markdown files
- repeated request with same idempotency key returns the existing draft

Real provider acceptance:

- generate 3 chapters from one project
- verify no metadata leaks
- verify character state persists
- verify at least one foreshadowing item can be added and later paid off

## Phasing

### Phase 1: Independent Novel Core

- add novel data contracts
- add SQLite stores
- add CLI entry point
- add chapter plan validation
- add fake-provider write flow
- add Markdown export
- add deterministic quality checks

### Phase 2: Real LLM Chapter Generation

- add Architect prompt
- add Chapter Writer prompt
- add Continuity Checker prompt
- adapt provider profiles for novel roles
- add 3-chapter real-provider acceptance test

### Phase 3: API Server

- add novel REST endpoints
- make existing management server independent from ComfyUI
- expose project/chapter/draft/ledger operations

### Phase 4: UI

- adapt the management panel to Novel mode
- add chapter planning and draft review screens

## Risks

- The existing RP turn engine is large and should not be mutated into a chapter engine directly.
- Memory curation is currently a weak point and must become chapter-aware before long projects.
- The prompt layer may overfit to RP "wait for player input" behavior unless Novel Writer has a clean contract.
- Markdown import can corrupt state if it writes directly without validation.
- Running real long chapters through LLM providers will need cost and retry controls.

## Decision

Proceed with a new `novel` runtime layer inside the current repository, preserving existing RP behavior while adding independent long-form novel generation.

The first implementation target is:

> plan one chapter, generate one readable chapter draft, pass deterministic checks, update continuity ledger, and export oh-story-compatible Markdown without ComfyUI.
