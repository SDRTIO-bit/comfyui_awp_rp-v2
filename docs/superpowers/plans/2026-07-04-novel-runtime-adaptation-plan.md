# 小说写作模式适配计划

Date: 2026-07-04

## 设计原则

**并行共存，不替换。** RP 模式和小说模式共享同一套引擎基础设施（LLM 适配器、存储层、质量门控框架、子代理调度），但各自有独立的 prompt、contract、curator 和 API 端点。RP 的任何现有行为不被修改。

**质量优先，分级思考。** 小说模式对输出质量的要求远高于 RP 模式，但"全面 thinking=high"是错误的——不同 Agent 需要不同强度的推理。过度推理对创意写作有害（文风僵硬），对结构规划有益。因此：
- **Director/Architect/ContinuityChecker 用 thinking=high。** 全局规划和连贯性检查需要深度推理。
- **Chapter Writer/LedgerCurator 用 thinking=medium。** 创意写作和信息提取需要适度推理，过度推理有害。
- **Style Cleaner 确定性为主，LLM 为辅（thinking=low）。** 禁用词/退化检测用规则，仅风格校验用 LLM。
- **一号主 Agent 从"执行导演"升级为"大纲优化导演"。** RP 的 Director 只做当轮规划，小说的 Director 需要具备全局视野——优化故事线、丰富大纲结构、设计伏笔回收、管理节奏曲线。

## 架构总览

```
                          ┌─────────────────────────────┐
                          │     awp_rp_runtime_v2       │
                          │                             │
                          │  ┌──────────┐ ┌──────────┐  │
                          │  │ RP Mode  │ │Novel Mode│  │
                          │  │(existing)│ │  (new)   │  │
                          │  └────┬─────┘ └────┬─────┘  │
                          │       │            │        │
                          │  ┌────┴────────────┴─────┐  │
                          │  │   Shared Infrastructure│  │
                          │  │  LLM Adapters          │  │
                          │  │  Storage (SQLite)       │  │
                          │  │  Quality Pipeline       │  │
                          │  │  Trace / Audit          │  │
                          │  │  Model Profile Registry │  │
                          │  └────────────────────────┘  │
                          └─────────────────────────────┘
```

RP 的 114 个 ComfyUI 节点、REST API、管理面板全部保留不动。小说模式作为新增模块叠加。

---

## Phase 1: 小说数据契约层

**目标：** 定义小说写作专用的数据结构，与 RP 的 contract 并行存在。

### 1.1 NovelProject 契约

新建 `contracts/novel_project.py`：

```python
@dataclass(frozen=True)
class NovelProject:
    schema_id: str = "awp.novel.project.v1"
    project_id: str
    title: str
    genre: str              # 都市/玄幻/悬疑/言情/科幻...
    target_platform: str    # 起点/番茄/自定义
    target_reader: str      # 目标读者画像
    core_emotion: str       # 全书核心情绪
    one_sentence_pitch: str
    status: str             # planning / writing / paused / completed
    created_at: str
    updated_at: str
```

### 1.2 VolumePlan 契约

新建 `contracts/novel_volume.py`：

```python
@dataclass(frozen=True)
class VolumePlan:
    schema_id: str = "awp.novel.volume-plan.v1"
    volume_id: str
    project_id: str
    index: int
    title: str
    chapter_start: int
    chapter_end: int
    core_conflict: str
    emotional_arc: str
    major_payoffs: list[str]
    foreshadowing_plan: list[str]
```

### 1.3 ChapterPlan 契约

新建 `contracts/novel_chapter.py`：

```python
@dataclass(frozen=True)
class SceneBeat:
    schema_id: str = "awp.novel.scene-beat.v1"
    beat_id: str
    index: int
    purpose: str            # setup / conflict / climax / resolution / bridge
    density: str            # dense / normal / sparse
    budget_chars: int       # 本节拍目标字数
    description: str        # 本节拍要发生什么
    required_facts: list[str]   # 必须包含的事实
    payoff_refs: list[str]      # 关联的爽点/伏笔

@dataclass(frozen=True)
class ChapterPlan:
    schema_id: str = "awp.novel.chapter-plan.v1"
    chapter_id: str
    project_id: str
    volume_id: str
    chapter_index: int
    title: str
    target_chars: int           # 目标总字数 2000-5000
    chapter_position: str       # high_pressure / progression / relationship / setup / cooldown / information
    target_emotion: str         # 本章目标情绪
    opening_hook: str           # 开头钩子
    main_payoff: str            # 主要爽点/核心事件
    ending_hook: str            # 结尾悬念
    summary_5_part: str         # 五句话概要
    plot_lines: list[str]       # 涉及的线索
    character_changes: list[str] # 本章角色变化
    information_gap: list[str]  # 信息差设计
    scene_beats: list[SceneBeat]
    cost_and_reward: str        # 燃料管理：本章消耗什么、留下什么
```

### 1.4 ChapterDraft 契约

新建 `contracts/novel_draft.py`：

```python
@dataclass(frozen=True)
class ChapterDraft:
    schema_id: str = "awp.novel.chapter-draft.v1"
    draft_id: str
    chapter_id: str
    revision: int
    source_plan_revision: int
    text: str
    char_count: int
    status: str                 # draft / accepted / rejected / superseded
    quality_decision_id: str
    created_at: str
```

### 1.5 DirectorGuidage 契约

Director 的输出，对应 RP 的 `DirectorPlan` + `FinalTurnBrief`，但增加了全局优化维度。

新建 `contracts/novel_director_guidance.py`：

```python
@dataclass(frozen=True)
class OutlineEnhancement:
    """大纲优化建议。"""
    target: str                     # "volume" / "chapter" / "scene_beat"
    target_id: str
    enhancement_type: str           # "add_beat" / "modify_beat" / "add_subplot" / "adjust_pacing" / "add_foreshadowing"
    description: str
    reasoning: str
    priority: str                   # "must_have" / "nice_to_have" / "optional"

@dataclass(frozen=True)
class ForeshadowingAction:
    """伏笔调度动作。"""
    foreshadowing_id: str
    action: str                     # "plant" / "advance" / "payoff" / "red_herring"
    scene_context: str
    subtlety: str                   # "explicit" / "implicit" / "background"

@dataclass(frozen=True)
class CharacterArcBeat:
    """角色弧光节拍。"""
    character_name: str
    arc_phase: str                  # "setup" / "challenge" / "growth" / "crisis" / "transformation"
    beat_description: str
    relationship_shifts: list[str]

@dataclass(frozen=True)
class SubplotStatus:
    """支线进度。"""
    subplot_name: str
    status: str                     # "dormant" / "advancing" / "climaxing" / "resolving" / "resolved"
    chapters_since_last_update: int
    urgency: str                    # "needs_attention" / "on_track" / "can_wait"

@dataclass(frozen=True)
class DirectorGuidance:
    schema_id: str = "awp.novel.director-guidance.v1"
    guidance_id: str

    # 当章方向
    chapter_direction: str
    emotional_arc: str
    pacing_strategy: str
    key_scenes: list[str]
    dialogue_tone: str

    # 大纲优化
    outline_enhancements: list[OutlineEnhancement]
    foreshadowing_schedule: list[ForeshadowingAction]
    character_arc_beats: list[CharacterArcBeat]
    reader_expectation_plan: str

    # 全局视角
    subplot_status: list[SubplotStatus]
    risk_flags: list[str]
    opportunities: list[str]

    reasoning: str
```

### 1.6 ContinuityLedger 契约

新建 `contracts/novel_ledger.py`：

```python
@dataclass(frozen=True)
class LedgerItem:
    schema_id: str = "awp.novel.ledger-item.v1"
    item_id: str
    project_id: str
    section: str    # character_state / timeline / foreshadowing / world_rules / relationship / open_threads
    entity: str     # 关联实体名
    content: str    # 条目内容
    status: str     # active / resolved / contradicted / stale
    source_chapter: int
    created_at: str
    updated_at: str
```

### 1.7 NovelCharacter 契约

新建 `contracts/novel_character.py`：

```python
@dataclass(frozen=True)
class NovelCharacter:
    """小说角色。多角色管理、关系图、语言风格、POV 资格。"""
    schema_id: str = "awp.novel.character.v1"
    character_id: str
    project_id: str
    name: str
    aliases: list[str]              # 别名/称号
    role: str                       # protagonist / antagonist / supporting / minor
    personality: str                # 性格描述
    voice_style: str                # 语言风格（口语化/书面腔/方言/特殊口癖）
    pov_eligible: bool              # 是否可以作为 POV 角色
    core_motivation: str            # 核心动机
    weakness: str                   # 弱点/缺陷
    relationships: list[CharacterRelationship]  # 与其他角色的关系
    current_state: dict[str, Any]   # 当前状态（身份/能力/位置/情绪）
    arc_phase: str                  # setup / challenge / growth / crisis / transformation
    first_appearance: int           # 首次出场章节
    created_at: str
    updated_at: str

@dataclass(frozen=True)
class CharacterRelationship:
    """角色关系。"""
    target_character_id: str
    target_name: str
    relation_type: str              # 恋人/仇人/师徒/父子/对手/盟友/暗恋...
    description: str                # 关系描述
    tension: str                    # 当前张力（高/中/低/无）
```

### 1.8 BatchProgress 契约

新建 `contracts/novel_batch.py`：

```python
@dataclass(frozen=True)
class BatchProgress:
    """批量生成进度追踪。"""
    schema_id: str = "awp.novel.batch-progress.v1"
    batch_id: str
    project_id: str
    chapter_start: int
    chapter_end: int
    chapter_index: int              # 当前处理的章节
    status: str                     # pending / in_progress / completed / failed
    retry_count: int                # 当前重试次数（每章最多 3 次）
    error_message: str              # 失败原因（status=failed 时）
    created_at: str
    updated_at: str
```

### 1.9 NovelWritePacket 契约

Writer 的输入包，对应 RP 的 `WriterInputBundle`：

```python
@dataclass
class NovelWritePacket:
    schema_id: str = "awp.novel.write-packet.v1"
    packet_id: str
    project_id: str
    chapter_id: str
    chapter_plan: ChapterPlan
    previous_chapter_summary: str
    relevant_ledger_items: list[LedgerItem]
    character_states: dict[str, Any]
    world_constraints: list[str]
    style_profile: dict[str, Any]       # 复用 preset 系统
    benchmark_snippets: list[str]       # 对标片段
    director_guidance: DirectorGuidance  # Director 的全局指导（替代 RP 的 director_score）
    current_scene_beat: SceneBeat | None # 当前正在生成的 beat（分 beat 模式）
    accumulated_text: str               # 已生成的 beat 文本（分 beat 模式，拼接用）
```

**产出物：** 7 个新 contract 文件，与 RP 的 contract 目录并行。

---

## Phase 2: 小说存储层

**目标：** 在 SQLite 中新增小说专用表，复用现有 `Database` 类和 `RuntimeStoreFactory`。

### 2.1 新增表

| 表名 | 对应契约 | 说明 |
|------|----------|------|
| `novel_projects` | NovelProject | 项目元数据 |
| `novel_volumes` | VolumePlan | 卷计划 |
| `novel_chapter_plans` | ChapterPlan | 章节计划（含嵌套 scene_beats JSON） |
| `novel_chapter_drafts` | ChapterDraft | 章节草稿/修订 |
| `novel_ledger_items` | LedgerItem | 连续性账本 |
| `novel_characters` | NovelCharacter | 角色管理（多角色、关系图、语言风格、POV） |
| `novel_batch_progress` | BatchProgress | 批量生成进度追踪（重试/恢复/断点续写） |
| `novel_quality_reviews` | NovelQualityReview | 质量审查记录 |

### 2.2 存储接口

新建 `storage/novel_interfaces.py`：

```python
class NovelProjectStore(ABC):
    def create(self, project: NovelProject) -> None: ...
    def load(self, project_id: str) -> NovelProject: ...
    def list_all(self) -> list[NovelProject]: ...
    def update(self, project: NovelProject) -> None: ...
    def delete(self, project_id: str) -> None: ...

class NovelChapterPlanStore(ABC):
    def save(self, plan: ChapterPlan) -> None: ...
    def load(self, chapter_id: str) -> ChapterPlan: ...
    def load_by_index(self, project_id: str, chapter_index: int) -> ChapterPlan: ...
    def list_by_project(self, project_id: str) -> list[ChapterPlan]: ...
    def get_next_index(self, project_id: str) -> int: ...

class NovelChapterDraftStore(ABC):
    def save(self, draft: ChapterDraft) -> None: ...
    def load(self, draft_id: str) -> ChapterDraft: ...
    def load_latest(self, chapter_id: str) -> ChapterDraft: ...
    def list_by_chapter(self, chapter_id: str) -> list[ChapterDraft]: ...

class NovelLedgerStore(ABC):
    def upsert(self, item: LedgerItem) -> None: ...
    def load(self, item_id: str) -> LedgerItem: ...
    def list_by_project(self, project_id: str, section: str = "") -> list[LedgerItem]: ...
    def resolve(self, item_id: str) -> None: ...
    def search(self, project_id: str, query: str) -> list[LedgerItem]: ...
```

### 2.3 SQLite 实现

新建 `storage/sqlite/novel_stores.py`，实现上述接口。

### 2.4 注册到工厂

在 `SessionRuntimeStoreRegistry` 中新增：
```python
self.novel_project_store: NovelProjectStore = ...
self.novel_chapter_plan_store: NovelChapterPlanStore = ...
self.novel_chapter_draft_store: NovelChapterDraftStore = ...
self.novel_ledger_store: NovelLedgerStore = ...
```

**产出物：** 3 个新文件（接口、SQLite 实现、注册），与现有 storage 并行。

---

## Phase 3: 小说 Agent 层

**目标：** 定义小说写作专用的 Agent 角色和 prompt，复用子代理调度框架。

### LLM 思考策略

小说模式采用**分级思考**策略——不同 Agent 需要不同强度的推理：

| Agent | 模型 | thinking | reasoning_effort | 说明 |
|-------|------|----------|-----------------|------|
| Director（大纲优化导演） | deepseek-v4-pro | **enabled** | **high** | 全局推理，伏笔调度，节奏曲线设计 |
| Architect（章节规划） | deepseek-v4-pro | **enabled** | **high** | 结构规划，beat 预算，钩子/反转设计 |
| Chapter Writer（章节写手） | deepseek-v4-pro | **enabled** | **medium** | 创意写作，过度推理导致文风僵硬 |
| Continuity Checker | deepseek-v4-flash | **enabled** | **high** | 连贯性检查需要细节推理，检测隐性矛盾 |
| Style Cleaner（确定性部分） | — | — | — | 纯规则，不用 LLM |
| Style Cleaner（LLM 风格校验） | deepseek-v4-flash | **enabled** | **low** | 仅"这段是否与文风设定一致"用 LLM |
| Ledger Curator | deepseek-v4-flash | **enabled** | **medium** | 需要推理从章节文本中提取角色状态、伏笔、时间线 |
| 子代理（D1-D5 小说版） | deepseek-v4-flash | **enabled** | **medium** | 每个子代理需要深度分析 |
| QualityGate | — | — | — | 纯确定性执行，12 步检查用规则实现 |

与 RP 的关键差异：
- RP 的 Writer 禁用 thinking（延迟敏感），小说的 Writer **启用 thinking=medium**（质量优先但不过度推理）
- RP 的 Director 用 flash 模型（成本控制），小说的 Director 用 **pro 模型**（全局优化需要更强推理）
- Style Cleaner 以确定性检查为主，LLM 只做轻量风格校验

### 3.1 Director Agent（大纲优化导演）

**这是小说模式与 RP 模式最大的差异点。**

RP 的 Director 只做当轮规划（"这一轮怎么写"），小说的 Director 是一个**全局故事架构师**——它不只是规划当前章节，而是持续优化整个故事线。

**与 RP Director 的本质区别：**

| 维度 | RP Director | 小说 Director |
|------|-------------|---------------|
| 视野 | 当轮（1 个回合） | 全书（项目+卷+章） |
| 职责 | 规划这一轮怎么回应玩家 | 优化故事线、丰富大纲、管理节奏 |
| 输出 | TurnBrief（当轮方向） | DirectorGuidance（章节方向 + 大纲优化建议 + 伏笔调度） |
| 主动性 | 被动（等玩家输入） | 主动（推动故事向前） |
| 优化对象 | 单轮叙事质量 | 全书结构质量 |

**职责：**
- **故事线优化：** 审视当前大纲，发现薄弱环节（伏笔断线、节奏平缓、角色扁平），提出优化建议
- **章节规划增强：** 在 Architect 生成的章节计划基础上，补充情感节拍、信息差设计、读者预期管理
- **伏笔调度：** 管理全书伏笔的埋设-推进-回收节奏，确保每章至少推进一条线索
- **节奏曲线管理：** 避免连续高压或连续低谷，设计章节间的情绪起伏
- **读者预期操控：** 设计悬念、误导、反转的时机
- **角色弧光追踪：** 确保主要角色有清晰的成长轨迹

**输出契约：** `DirectorGuidance`

```python
@dataclass(frozen=True)
class DirectorGuidance:
    schema_id: str = "awp.novel.director-guidance.v1"
    guidance_id: str

    # 当章方向
    chapter_direction: str          # 本章的叙事方向和重点
    emotional_arc: str              # 本章情绪弧线（开头→中间→结尾）
    pacing_strategy: str            # 节奏策略（紧凑/舒缓/张弛有度）
    key_scenes: list[str]           # 必须出现的关键场景
    dialogue_tone: str              # 对话基调

    # 大纲优化（Director 的核心价值）
    outline_enhancements: list[OutlineEnhancement]  # 对当前大纲的优化建议
    foreshadowing_schedule: list[ForeshadowingAction]  # 本章应执行的伏笔动作
    character_arc_beats: list[CharacterArcBeat]  # 本章的角色弧光节拍
    reader_expectation_plan: str    # 读者预期操控策略

    # 全局视角
    subplot_status: list[SubplotStatus]  # 各支线进度
    risk_flags: list[str]           # 可能的问题（节奏重复、角色行为矛盾等）
    opportunities: list[str]        # 可利用的戏剧机会

    reasoning: str                  # 推理过程（供审查）

@dataclass(frozen=True)
class OutlineEnhancement:
    """大纲优化建议。Director 不直接修改大纲，而是提出建议供人工确认。"""
    target: str                     # "volume" / "chapter" / "scene_beat"
    target_id: str                  # 目标 ID
    enhancement_type: str           # "add_beat" / "modify_beat" / "add_subplot" / "adjust_pacing" / "add_foreshadowing"
    description: str                # 具体建议
    reasoning: str                  # 为什么需要这个优化
    priority: str                   # "must_have" / "nice_to_have" / "optional"

@dataclass(frozen=True)
class ForeshadowingAction:
    """伏笔调度动作。"""
    foreshadowing_id: str           # 伏笔 ID
    action: str                     # "plant" / "advance" / "payoff" / "red_herring"
    scene_context: str              # 在什么场景中执行
    subtlety: str                   # "explicit" / "implicit" / "background"

@dataclass(frozen=True)
class CharacterArcBeat:
    """角色弧光节拍。"""
    character_name: str
    arc_phase: str                  # "setup" / "challenge" / "growth" / "crisis" / "transformation"
    beat_description: str           # 本章的具体弧光节拍
    relationship_shifts: list[str]  # 本章关系变化

@dataclass(frozen=True)
class SubplotStatus:
    """支线进度追踪。"""
    subplot_name: str
    status: str                     # "dormant" / "advancing" / "climaxing" / "resolving" / "resolved"
    chapters_since_last_update: int
    urgency: str                    # "needs_attention" / "on_track" / "can_wait"
```

**Prompt 结构：**
```
=== STABLE DIRECTOR CONTRACT ===
你是长篇网文的大纲优化导演。你有两个核心职责：
1. 为当前章节提供精确的叙事方向
2. 审视全书结构，持续优化故事线

你不是写手，你不出正文。你是"总编辑 + 导演"的结合体。
你需要用深度思考来审视故事的全局结构，发现读者会注意到但作者可能忽略的问题。

=== PROJECT CONTEXT ===
项目设定: {novel_project}
全书大纲: {full_outline}
已完成章节摘要: {completed_chapters_summary}
连续性账本: {relevant_ledger_items}
角色状态: {character_states}
伏笔清单: {foreshadowing_list}
支线进度: {subplot_status}

=== CURRENT TASK ===
当前要写第 {chapter_index} 章
章节计划: {chapter_plan}
前一章结尾: {previous_chapter_ending}

=== THINKING WORKFLOW ===
1. 先审视全书结构：当前处于什么阶段？节奏是否合理？
2. 检查伏笔：有哪些需要推进？有哪些需要埋设？
3. 检查角色弧光：主要角色在本章应该有什么成长？
4. 检查支线：哪些支线需要推进？哪些可以暂缓？
5. 设计读者预期：本章应该给读者什么期待？如何误导或满足？
6. 最后：为 Writer 提供精确的本章方向

=== OUTPUT FORMAT ===
严格的 JSON 输出，符合 DirectorGuidance schema。
```

### 3.2 Chapter Writer Agent（章节写手）

替代 RP 中的 Writer，但面向章节级别。**启用 thinking**，因为文学创作需要构思过程——选择意象、设计对话、安排节奏都需要"想一想再写"。

**职责：**
- 根据 ChapterPlan 生成正文
- 遵循 SceneBeat 的密度指示（dense 展开，sparse 压缩）
- 遵循风格预设（复用 kedai_heavy_v1.txt 的 Gate A-H）
- 遵循 Director 的叙事方向和情绪弧线
- 不写角色设定、不修改状态

**Prompt 结构：**
```
=== STABLE WRITING CONTRACT ===
{kedai_heavy_v1.txt 的 CACHE-STABLE 部分}

=== CHAPTER PLAN ===
{chapter_plan}

=== PREVIOUS CHAPTER ===
{previous_chapter_summary}

=== CONTINUITY CONTEXT ===
{relevant_ledger_items}

=== CHARACTER STATES ===
{character_states}

=== STYLE GATES ===
{kedai_heavy_v1.txt 的 Gate A-H}

=== DIRECTOR GUIDANCE ===
{director_guidance}
// 包含：chapter_direction, emotional_arc, pacing_strategy,
// key_scenes, dialogue_tone, foreshadowing_schedule,
// character_arc_beats, reader_expectation_plan

=== OUTPUT RULES ===
- 只输出正文，无标签、无 JSON、无元信息
- 目标 {target_chars} 字
- 结尾必须留悬念/钩子
- 不复述上一章结尾
- 严格遵循 Director 的情绪弧线和节奏策略
- 在 thinking 中先构思场景、对话、意象，再动笔
```

**复用点：** 直接复用 `kedai_heavy_v1.txt` 预设的 8 道门控（Gate A-H），这些门控对小说同样有效。

### 3.3 Continuity Checker Agent（连续性检查）

**职责：**
- 检测事实矛盾（人物年龄、地点、时间线）
- 检测伏笔断裂（埋了但没回收，或回收了但没埋）
- 检测角色行为漂移（性格突变）
- 检测世界观规则违反

**工具调用：** 复用现有子代理框架，新增工具：
- `chapter_outline_lookup` — 查看章节计划
- `ledger_lookup` — 查连续性账本
- `character_state_lookup` — 查角色状态
- `previous_chapter_lookup` — 查前文

### 3.4 Style Cleaner Agent（风格清洗）

**职责：**
- AI 味检测（"仿佛"、"犹如"、"不禁"等）
- 重复段落检测
- 工程术语泄露检测（"API"、"JSON"、"prompt"等）
- 标点/段落合理性检查

**实现方式：** 可以是 LLM agent，也可以是纯确定性检查（复用 RP 的 QualityPipelineRuntime 框架）。

### 3.5 Ledger Curator Agent（账本管理员）

替代 RP 中的 `TurnEvolutionCurator`，但面向小说连续性。

**职责：**
- 分析已接受的章节正文
- 提议更新连续性账本（角色状态变化、伏笔推进、时间线更新、关系变化）
- 提议新增/解决开放线索

**Prompt 结构：**
```
=== CURATOR CONTRACT ===
你负责维护长篇小说的连续性账本。分析已接受的章节正文，更新追踪信息。

=== CHAPTER PLAN ===
{chapter_plan}

=== ACCEPTED CHAPTER TEXT ===
{chapter_text}

=== CURRENT LEDGER ===
{current_ledger_items}

=== OUTPUT FORMAT ===
JSON: {
  "ledger_updates": [...],     // 新增/修改的账本条目
  "ledger_resolves": [...],    // 标记为已解决的条目
  "chapter_summary": "...",    // 本章一句话摘要（供下一章的 previous_chapter_summary）
  "foreshadowing_changes": [...] // 伏笔状态变化
}
```

---

## Phase 4: 小说引擎编排层

**目标：** 实现小说写作的主流程编排。

> **⚠️ 审计修正：** NovelEngine **不能子类化** PersistentTurnEngine。RP 引擎的 `execute()` 是 700+ 行的单体方法，参数全是 RP 专用的（player_input, binding, snapshot, card_state），内部调用链硬编码。NovelEngine 必须是**全新的类**，共享底层基础设施（LLM 适配器、存储、契约），不共享引擎本身。

### 4.1 NovelEngine

新建 `runtime/novel_engine.py`，**不继承** PersistentTurnEngine。

```python
class NovelEngine:
    """小说章节生成引擎。独立于 PersistentTurnEngine，共享底层基础设施。

    共享的基础设施：
    - SessionRuntimeStoreRegistry（存储层）
    - RuntimeStoreFactory（工厂）
    - DeepSeekAdapter（LLM 调用）
    - ModelProfileRegistry（profile 管理）
    - QualityIssue / QualityDecision（质量契约）

    不共享的：
    - PersistentTurnEngine（RP 专用单体引擎）
    - QualityPipelineRuntime（RP 专用门控逻辑）
    - WriterInputBundleV2Builder（RP 专用 bundle 构建）
    - SubAgentLLMRunner（RP 的 thinking 被硬编码禁用）
    """

    def __init__(self, registry: SessionRuntimeStoreRegistry, profile: str = "production"):
        self._registry = registry
        self._profile = profile
        # 复用底层 LLM 适配器
        self._architect_adapter = NovelArchitectAdapter(registry)
        self._director_adapter = NovelDirectorAdapter(registry)
        self._writer_adapter = NovelWriterAdapter(registry)
        self._continuity_checker = NovelContinuityChecker(registry)
        self._style_cleaner = NovelStyleCleaner(registry)
        self._ledger_curator = NovelLedgerCurator(registry)
        self._quality_pipeline = NovelQualityPipeline(registry)
        self._packet_builder = NovelWritePacketBuilder(registry)

    def plan_chapter(
        self,
        *,
        project_id: str,
        chapter_index: int,
        task_description: str = "",
    ) -> tuple[ChapterPlan, list[LedgerItem]]:
        """Phase 1: Architect 规划章节。"""
        # 1. 加载 NovelProject + VolumePlan
        # 2. 加载已完成章节摘要
        # 3. 加载相关 LedgerItem
        # 4. 调用 Architect Agent（LLM）
        # 5. 验证 ChapterPlan 必填字段
        # 6. 持久化 ChapterPlan
        # 7. 导出 大纲/细纲_第XXX章.md（可选）

    def write_chapter(
        self,
        *,
        project_id: str,
        chapter_index: int,
        revision: int = 1,
    ) -> ChapterDraft:
        """Phase 2: Director 优化 + 分 beat 生成章节正文。"""
        # 1. 加载 ChapterPlan
        # 2. 加载全书上下文（大纲、已完成章节、账本、伏笔、支线）
        # 3. 调用 Director Agent（LLM, thinking=high）
        #    → 输出 DirectorGuidance（章节方向 + 大纲优化建议 + 伏笔调度）
        # 4. 构建 NovelWritePacket（含 DirectorGuidance）
        # 5. 分 beat 生成（核心流程）：
        #    accumulated_text = ""
        #    for beat in chapter_plan.scene_beats:
        #        beat_packet = build_beat_packet(beat, accumulated_text, ...)
        #        beat_text = writer_agent.generate(beat_packet)  # thinking=medium
        #        # 每个 beat 300-800 字，单次 LLM 调用可控
        #        accumulated_text += beat_text
        #    # 一章 5-10 个 beat，失败只需重写当前 beat
        # 6. 质量门控（确定性 12 步检查 + LLM 风格校验 thinking=low）
        # 7. 如果拒绝，重试（最多 2 次，只重写失败的 beat）
        # 8. 持久化 ChapterDraft
        # 9. 调用 Ledger Curator（LLM, thinking=medium）
        # 10. 更新 Ledger
        # 11. 导出 正文/第XXX章_章名.md（可选）

    def _generate_beat(
        self,
        *,
        beat: BeatDetail,
        accumulated_text: str,
        chapter_plan: ChapterPlan,
        director_guidance: DirectorGuidance,
        ledger_items: list[LedgerItem],
        max_retries: int = 2,
    ) -> str:
        """单个 beat 生成，失败重试只影响当前 beat。"""
        for attempt in range(max_retries + 1):
            beat_packet = NovelWritePacketBuilder.build_beat_packet(
                beat=beat,
                accumulated_text=accumulated_text,
                chapter_plan=chapter_plan,
                director_guidance=director_guidance,
                ledger_items=ledger_items,
            )
            beat_text = self._writer_adapter.generate(beat_packet)
            # 简单校验：字数在 beat 预算的 80%-120% 范围内
            if len(beat_text) >= beat.budget_chars * 0.8:
                return beat_text
            # 字数不足，重试
        # 所有重试用完，返回最后一次的结果
        return beat_text

    def revise_chapter(
        self,
        *,
        project_id: str,
        chapter_index: int,
        feedback: str = "",
        mode: str = "full",  # full / targeted
    ) -> ChapterDraft:
        """Phase 3: 修订章节。"""
        # 1. 加载当前 ChapterDraft + ChapterPlan
        # 2. 加载前/后章上下文
        # 3. 加载 Ledger
        # 4. 构建修订 NovelWritePacket（含反馈）
        # 5. 调用 Chapter Writer Agent
        # 6. 质量门控
        # 7. 连续性影响检查
        # 8. 持久化新 ChapterDraft revision
        # 9. 更新 Ledger

    def batch_write(
        self,
        *,
        project_id: str,
        chapter_start: int,
        chapter_end: int,
        on_chapter_complete: Callable[[int, ChapterDraft], None] | None = None,
    ) -> list[ChapterDraft]:
        """Phase 4: 批量连续生成，带容错。"""
        # 1. 查询 batch_progress，跳过已完成和失败的章节
        # 2. for chapter_index in range(chapter_start, chapter_end + 1):
        #     2.1 检查 batch_progress 状态：
        #         - completed → 跳过
        #         - failed → 跳过（已重试 3 次都失败）
        #         - pending/in_progress → 执行
        #     2.2 写入 batch_progress: status="in_progress"
        #     2.3 重试循环（最多 3 次）：
        #         try:
        #             plan_chapter() + write_chapter()
        #             写入 batch_progress: status="completed"
        #             break
        #         except Exception as e:
        #             写入 batch_progress: status="in_progress", retry_count++
        #             if retry_count >= 3:
        #                 写入 batch_progress: status="failed", error=str(e)
        #                 log error, 不阻塞后续章节
        #     2.4 每章写完立即更新 Ledger
        #     2.5 每 3 章做一次中途快照
        #     2.6 回调 on_chapter_complete
        # 3. 返回所有 completed 的 ChapterDraft
```

### 4.2 质量门控

新建 `runtime/novel_quality_pipeline.py`，复用 RP 的 `QualityPipelineRuntime` 框架。

**阻断规则：**
- 正文低于目标字数 90%
- 检测到重复文本循环
- 检测到截断
- JSON/工具痕迹/prompt 文本泄露
- 内部词（"细纲"、"伏笔"、"本章"、"上一章"、"读者"）出现在正文中
- 硬连续性事实违反

**警告规则：**
- 章名与已有章名重复
- dense beat 未充分展开
- sparse beat 过度展开
- 结尾钩子太弱
- 角色状态更新缺失
- 风格漂移

### 4.3 Markdown 导出器

新建 `runtime/novel_markdown_exporter.py`：

```python
class NovelMarkdownExporter:
    def export_project(self, project_id: str, output_dir: str) -> None:
        """导出完整项目为 oh-story 兼容目录结构。"""
        # {book_title}/
        # ├── 设定/
        # │   ├── 世界观/
        # │   ├── 角色/
        # │   ├── 势力/
        # │   ├── 关系.md
        # │   ├── 文风.md
        # │   └── 题材定位.md
        # ├── 大纲/
        # │   ├── 大纲.md
        # │   ├── 卷纲_第001卷.md
        # │   └── 细纲_第001章.md
        # ├── 正文/
        # │   └── 第001章_章名.md
        # ├── 追踪/
        # │   ├── 上下文.md
        # │   ├── 伏笔.md
        # │   ├── 时间线.md
        # │   └── 角色状态.md
        # └── 对标/

    def export_chapter(self, chapter_id: str, output_dir: str) -> None:
        """导出单章。"""
```

### 4.4 Markdown 导入器

新建 `runtime/novel_markdown_importer.py`：

```python
class NovelMarkdownImporter:
    def import_project(self, project_dir: str) -> tuple[NovelProject, list[str]]:
        """从 oh-story 目录结构导入项目。返回 (project, validation_warnings)。"""
        # 1. 解析 设定/ 目录 → NovelProject
        # 2. 解析 大纲/ 目录 → VolumePlan + ChapterPlan
        # 3. 解析 正文/ 目录 → ChapterDraft
        # 4. 解析 追踪/ 目录 → LedgerItem
        # 5. 验证并返回 warnings
```

---

## Phase 5: 小说 API 层

**目标：** 在现有 REST API 旁新增小说端点，共享 aiohttp 服务器。

### 5.1 REST 端点

在 `scripts/awp_server.py` 的 `create_app()` 中新增路由组：

```
# 项目管理
POST   /awp/api/v1/novels                          # 创建项目
GET    /awp/api/v1/novels                          # 列出项目
GET    /awp/api/v1/novels/{project_id}             # 项目详情
DELETE /awp/api/v1/novels/{project_id}             # 删除项目

# 卷计划
POST   /awp/api/v1/novels/{project_id}/volumes     # 创建卷计划
GET    /awp/api/v1/novels/{project_id}/volumes     # 列出卷计划

# 章节计划
POST   /awp/api/v1/novels/{project_id}/chapters/plan        # Architect 规划章节
GET    /awp/api/v1/novels/{project_id}/chapters/{idx}/plan   # 获取章节计划
PUT    /awp/api/v1/novels/{project_id}/chapters/{idx}/plan   # 更新章节计划

# 章节写作
POST   /awp/api/v1/novels/{project_id}/chapters/{idx}/write   # Writer 生成正文
GET    /awp/api/v1/novels/{project_id}/chapters/{idx}/drafts   # 列出草稿版本
POST   /awp/api/v1/novels/{project_id}/chapters/{idx}/revise   # 修订章节

# 批量生成
POST   /awp/api/v1/novels/{project_id}/batch-write             # 连续生成多章
GET    /awp/api/v1/novels/{project_id}/batch-write/{batch_id}  # 批量进度

# 连续性账本
GET    /awp/api/v1/novels/{project_id}/ledger                  # 查看账本
POST   /awp/api/v1/novels/{project_id}/ledger                  # 手动添加账本条目

# 导入导出
POST   /awp/api/v1/novels/{project_id}/export                  # 导出 Markdown
POST   /awp/api/v1/novels/import-markdown                      # 导入 Markdown
```

### 5.2 CLI 入口

新建 `novel/__main__.py`：

```python
"""用法: python -m awp_rp_runtime_v2.novel <command> [args]"""

# 命令:
#   create    --title "..." --genre "..." --pitch "..."
#   plan      --project <id> --chapter <n>
#   write     --project <id> --chapter <n>
#   batch     --project <id> --from <n> --to <n>
#   export    --project <id> --output <dir>
#   import    --dir <path>
#   ledger    --project <id> [--section <s>]
#   status    --project <id>
```

---

## Phase 6: ComfyUI 节点（可选）

**目标：** 为 ComfyUI 用户提供小说写作节点，复用现有节点注册模式。

### 6.1 新增节点

| 节点名 | 功能 |
|--------|------|
| `AWPV2NovelProjectCreate` | 创建小说项目 |
| `AWPV2NovelVolumePlan` | 创建卷计划 |
| `AWPV2NovelChapterPlan` | Architect 规划章节 |
| `AWPV2NovelChapterWrite` | Writer 生成正文 |
| `AWPV2NovelChapterRevise` | 修订章节 |
| `AWPV2NovelLedgerView` | 查看账本 |
| `AWPV2NovelExport` | 导出 Markdown |
| `AWPV2NovelBatchWrite` | 批量生成 |

在 `nodes/__init__.py` 中注册到 `NODE_CLASS_MAPPINGS`。

### 6.2 工作流模板

新建 `workflows/novel_chapter_write.json` — 一键章节写作工作流。

---

## Phase 7: 前端适配（后续）

**目标：** 在现有管理面板中新增小说模式 Tab。

### 7.1 页面

| 页面 | 功能 |
|------|------|
| 项目列表 | 创建/删除/选择项目 |
| 项目概览 | 卷计划、章节目录、进度 |
| 章节计划 | 查看/编辑 Architect 生成的章节计划 |
| 章节正文 | 查看/编辑草稿，触发修订 |
| 连续性账本 | 查看/编辑账本条目 |
| 批量生成 | 设置范围、启动、进度监控 |
| 导入导出 | Markdown 文件管理 |

---

## 共享基础设施映射

> **⚠️ 审计修正：** 区分"直接复用"和"需要新建"。RP 的引擎层（PersistentTurnEngine、QualityPipelineRuntime、SubAgentLLMRunner）**不能直接复用**——它们是 RP 专用的单体实现。小说模式共享的是更底层的基础设施。

### 直接复用（不修改）

| RP 组件 | 复用方式 |
|---------|---------|
| `DeepSeekAdapter` | 直接复用，thinking 在调用层控制（不在 Adapter 层） |
| `Database` + migration 机制 | 直接复用，新增 novel 表的 migration |
| `RuntimeStoreFactory` | 直接复用，新增 novel store 访问器 |
| `SessionRuntimeStoreRegistry` | 直接复用，新增 novel store 实例 |
| `QualityIssue` / `QualityDecision` / `QualityGateResult` | 直接复用质量契约 |
| `ExecutionTrace` / `TraceEvent` | 直接复用，新增 novel 类型标记 |
| `BudgetPolicy` | 直接复用，构造时传入小说版参数 |
| `RetryPolicy` | 直接复用 |

### 需要扩展

| RP 组件 | 扩展方式 |
|---------|---------|
| `ModelProfileRegistry` | 新增 6 个小说 profile（见下表），不修改 ModelProfile 数据类 |
| `kedai_heavy_v1.txt` | 复用 Gate A-H，新增章节级门控 |

### 需要新建（不复用 RP 实现）

| RP 组件 | 小说模式新建组件 | 原因 |
|---------|----------------|------|
| `PersistentTurnEngine` | `NovelEngine` | RP 引擎是 700+ 行单体方法，参数 RP 专用 |
| `QualityPipelineRuntime` | `NovelQualityPipeline` | RP 门控检查角色名/CardState，小说需要禁用词/退化/beat 预算 |
| `SubAgentLLMRunner` | `NovelSubAgentRunner` | RP 的 thinking 被硬编码禁用（`_EXTRA_DISABLE_THINKING`） |
| `WriterInputBundleV2Builder` | `NovelWritePacketBuilder` | RP 的约束列表硬编码，小说需要不同的约束 |
| `TurnEvolutionCurator` | `NovelLedgerCurator` | RP 的 curator prompt 面向 CardState，小说面向 Ledger |
| `PromptAssembler` | `NovelPromptAssembler` | RP 的 system prompt 是 RP 专用的 |

### 新增 Model Profile + Thinking 控制

> **⚠️ 审计修正：** thinking **不在 ModelProfile 中配置**。DeepSeekAdapter 的 thinking 是通过 `extra_body` 参数在调用层控制的：
> ```python
> # RP 的做法（硬编码禁用）
> _EXTRA_DISABLE_THINKING = {"thinking": {"type": "disabled"}}
> adapter.call_tool_turn(..., extra_body=_EXTRA_DISABLE_THINKING)
> ```
>
> 小说模式的做法：**各 Agent Adapter 定义自己的 thinking 配置**，调用时传入 `extra_body`：
> ```python
> # novel_writer_adapter.py
> _THINKING_MEDIUM = {"thinking": {"type": "enabled", "reasoning_effort": "medium"}}
> adapter.call_text(prompt, extra_body=_THINKING_MEDIUM)
> ```
>
> ModelProfile 数据类**不需要修改**。新增 profile 只是为了隔离小说和 RP 的模型配置。

**小说 Agent 的 thinking 控制：**

| Agent | extra_body 配置 | 定义位置 |
|-------|----------------|---------|
| Director | `{"thinking": {"type": "enabled", "reasoning_effort": "high"}}` | `novel_director_adapter.py` |
| Architect | `{"thinking": {"type": "enabled", "reasoning_effort": "high"}}` | `novel_architect_adapter.py` |
| Writer | `{"thinking": {"type": "enabled", "reasoning_effort": "medium"}}` | `novel_writer_adapter.py` |
| ContinuityChecker | `{"thinking": {"type": "enabled", "reasoning_effort": "high"}}` | `novel_continuity_checker.py` |
| StyleCleaner (LLM) | `{"thinking": {"type": "enabled", "reasoning_effort": "low"}}` | `novel_style_cleaner.py` |
| LedgerCurator | `{"thinking": {"type": "enabled", "reasoning_effort": "medium"}}` | `novel_ledger_curator.py` |
| QualityGate | 不调用 LLM | — |

**新增 Model Profile（仅隔离模型配置，不含 thinking）：**

| Profile ID | 模型 | default_max_tokens | 用途 |
|------------|------|-------------------|------|
| `novel-director` | deepseek-v4-pro | 8000 | 大纲优化导演 |
| `novel-architect` | deepseek-v4-pro | 6000 | 章节规划 |
| `novel-writer` | deepseek-v4-pro | 4000 | 章节写作 |
| `novel-continuity` | deepseek-v4-flash | 4000 | 连续性检查 |
| `novel-style-cleaner-llm` | deepseek-v4-flash | 2000 | 仅风格校验用 LLM |
| `novel-ledger-curator` | deepseek-v4-flash | 4000 | 账本管理 |

### NovelQualityPipeline 组合复用

> **审计发现：** QualityPipelineRuntime 中有 2 个通用门控可复用（LengthGate、FormatGate），2 个 RP 专用不可复用（IdentityGate、SceneGate）。

```python
class NovelQualityPipeline:
    def __init__(self):
        # 复用 RP 的通用门控
        from .quality_pipeline_runtime import LengthGate, FormatGate
        self._length_gate = LengthGate(min_length=2000, max_length=8000)
        self._format_gate = FormatGate()  # JSON 泄露检查

        # 小说专用门控（全新实现）
        self._banned_words_gate = BannedWordsGate()      # 禁用词检查
        self._degeneration_gate = DegenerationGate()      # 退化检测
        self._metadata_leak_gate = MetadataLeakGate()     # 元信息泄露
        self._beat_budget_gate = BeatBudgetGate()         # beat 预算校验
        self._chapter_hook_gate = ChapterHookGate()       # 章尾钩子检查
        self._style_consistency_gate = StyleConsistencyGate()  # 风格一致性（LLM）
```

### 小说模式 BudgetPolicy 差异

| 参数 | RP 模式 | 小说模式 | 原因 |
|------|---------|---------|------|
| max_tokens_per_turn | 50,000 | 100,000 | Director 深度思考 + 分 beat 生成多次调用 |
| max_llm_calls_per_turn | 10 | 20 | 多 Agent 并行 + 分 beat 生成（5-10 个 beat） |
| max_sub_agents | 3 | 5 | 小说需要更多分析维度 |
| thinking_budget | disabled (Writer) | 分级（见上表） | 质量优先但分级控制 |
| max_chapter_retries | 2 | 2 | 单章重试上限 |
| max_batch_retries | — | 3 | 批量生成每章重试上限 |

---

## 文件清单

### 新增文件（共约 42 个）

```
contracts/
├── novel_project.py              # NovelProject
├── novel_volume.py               # VolumePlan
├── novel_chapter.py              # ChapterPlan, SceneBeat, ContentSummary, PlotArrangement, CharacterAppearance, BeatDetail, EndingDesign
├── novel_draft.py                # ChapterDraft
├── novel_ledger.py               # LedgerItem
├── novel_character.py            # NovelCharacter, CharacterRelationship
├── novel_batch.py                # BatchProgress
├── novel_director_guidance.py    # DirectorGuidance, OutlineEnhancement, ForeshadowingAction, CharacterArcBeat, SubplotStatus
└── novel_write_packet.py         # NovelWritePacket

storage/
├── novel_interfaces.py           # 存储接口
└── sqlite/
    └── novel_stores.py           # SQLite 实现

runtime/
├── novel_engine.py               # 主编排引擎（全新，不继承 PersistentTurnEngine）
├── novel_quality_pipeline.py     # 质量门控（全新，不继承 QualityPipelineRuntime）
├── novel_prompt_assembler.py     # Prompt 组装（全新，不继承 PromptAssembler）
├── novel_architect_adapter.py    # Architect LLM 适配（复用 DeepSeekAdapter，thinking=high）
├── novel_director_adapter.py     # Director LLM 适配（复用 DeepSeekAdapter，thinking=high）
├── novel_writer_adapter.py       # Writer LLM 适配（复用 DeepSeekAdapter，thinking=medium）
├── novel_continuity_checker.py   # 连续性检查（复用 DeepSeekAdapter，thinking=high）
├── novel_style_cleaner.py        # 风格清洗（确定性为主，LLM thinking=low 为辅）
├── novel_ledger_curator.py       # 账本管理员（复用 DeepSeekAdapter，thinking=medium）
├── novel_sub_agent_runner.py     # 子代理运行器（全新，thinking 可配置，不继承 SubAgentLLMRunner）
├── novel_write_packet_builder.py # 写前三步（全新，不继承 WriterInputBundleV2Builder）
├── novel_degeneration_checker.py # 退化检测（从 oh-story 吸收）
├── novel_punctuation_normalizer.py # 标点归一化（从 oh-story 吸收）
├── novel_markdown_exporter.py    # Markdown 导出
└── novel_markdown_importer.py    # Markdown 导入

presets/
├── writer/
│   └── novel_chapter_v1.txt      # 小说章节写作预设
├── banned_words_tier1.txt        # 一级禁用词（从 oh-story 搬入）
├── banned_words_tier2.txt        # 二级禁用词
├── banned_patterns.txt           # 禁用句式
└── quality_checklist.md          # 质量检查清单

nodes/
└── novel_nodes.py                # ComfyUI 节点

novel/
└── __main__.py                   # CLI 入口

scripts/
└── novel_api.py                  # REST 端点处理器

tests/
├── test_novel_contracts.py
├── test_novel_stores.py
├── test_novel_engine.py
├── test_novel_quality.py
├── test_novel_export.py
└── test_novel_integration.py
```

### 修改文件（共约 5 个）

```
storage/sqlite/database.py           # 新增 novel 表的 CREATE TABLE migration
runtime/session_runtime_registry.py  # 新增 novel store 注册
runtime/runtime_store_factory.py     # 新增 novel store 访问器
adapters/llm/model_profile_registry.py # 注册 6 个小说 profile（不修改 ModelProfile 数据类）
scripts/awp_server.py                # 新增 novel 路由
nodes/__init__.py                    # 注册 novel 节点（可选）
```

---

## 测试策略

### 单元测试（Phase 1-2）
- NovelProject / ChapterPlan / ChapterDraft 契约验证
- SQLite 存储 CRUD
- ChapterPlan 必填字段校验
- SceneBeat 预算校验
- Ledger 条目状态转换

### 集成测试（Phase 3-4）
- `create_project → plan_chapter → write_fake_draft → quality_accept → ledger_update → export`
- 无计划不能写正文
- 幂等请求返回已有草稿
- Markdown 导出确定性验证

### 真实 LLM 验收测试（Phase 4）
- 生成 3 章连续内容
- 验证无元数据泄露
- 验证角色状态跨章持久
- 验证伏笔可以埋设并回收
- 验证连续性账本正确更新

---

## 实施顺序建议

```
Phase 1 (契约)    ← 最快见效，无依赖，纯数据结构
    ↓
Phase 2 (存储)    ← 依赖 Phase 1 的契约
    ↓
Phase 3 (Agent)   ← 依赖 Phase 1 的契约，可与 Phase 2 并行
    ↓
Phase 4 (引擎)    ← 依赖 Phase 1-3
    ↓
Phase 5 (API)     ← 依赖 Phase 4，可与 Phase 6 并行
    ↓
Phase 6 (节点)    ← 依赖 Phase 4，可选
    ↓
Phase 7 (前端)    ← 依赖 Phase 5，后续
```

Phase 1+2+3 可以作为一个 sprint 完成（契约+存储+Agent prompt）。
Phase 4 是核心（引擎编排），需要最多设计精力。
Phase 5+6 是接入层，相对直接。
Phase 7 是体验层，可以后续迭代。

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| RP 引擎改动影响小说模式 | 严格并行设计，共享底层基础设施，不共享引擎层 |
| **PersistentTurnEngine 无法子类化** | **审计发现：RP 引擎是 700+ 行单体方法，NovelEngine 必须是全新实现，共享 LLM 适配器/存储/契约** |
| ~~ModelProfile 缺少 thinking 字段~~ | **已修正：thinking 不在 ModelProfile 中配置，在各 Adapter 调用层用 extra_body 控制** |
| **QualityPipelineRuntime 门控 RP 专用** | **审计发现：RP 门控检查角色名/CardState，NovelQualityPipeline 必须全新实现** |
| **SubAgentLLMRunner thinking 硬编码禁用** | **审计发现：`_EXTRA_DISABLE_THINKING` 硬编码，NovelSubAgentRunner 必须全新实现** |
| 小说 prompt 过度拟合 RP "等玩家输入" | NovelWritePacket 中 `player_input` 改为 `chapter_plan`，prompt 重写 |
| **单章字数不可控** | **分 beat 生成：每个 beat 300-800 字，5-10 个 beat/章，单次调用可控，失败只重写当前 beat** |
| **beat 之间文风不一致** | **每个 beat 的 NovelWritePacket 包含 accumulated_text（已生成部分），Writer 能看到前文风格** |
| **thinking 成本高** | **分级控制：Director/Architect/ContinuityChecker=high，Writer/LedgerCurator=medium，StyleCleaner=low/确定性** |
| **Director 延迟长** | **Director 的深度思考可能需要 30-60 秒，但小说模式不面向实时交互，用户可接受；batch_write 异步执行** |
| 记忆系统在长篇中失效 | Ledger 系统替代 RP 的 ActiveMemory，结构化更强 |
| Markdown 导入破坏状态 | 导入只读验证 + 生成 validation_report，不直接写入 |
| 连续性检查漏报 | LLM 检查（thinking=high）+ 确定性检查双保险 |
| **batch_write 中途失败** | **重试策略：每章最多 3 次，3 次失败标记 failed 并跳过；进度持久化到 batch_progress 表；恢复时跳过 completed/failed** |
| **Director 大纲优化建议过多** | **`OutlineEnhancement` 有 priority 字段，must_have 自动应用，nice_to_have/optional 需人工确认** |
| **多角色管理混乱** | **NovelCharacter 契约：每个角色独立管理 personality/voice_style/relationships/arc_phase** |

---

## 里程碑

| 里程碑 | 交付物 | 验收标准 |
|--------|--------|----------|
| M0: 基础设施扩展 | 6 个小说 profile 注册（不修改 ModelProfile 数据类）+ thinking 在各 Adapter 用 extra_body 控制 | 现有 RP 测试不受影响 |
| M1: 契约+存储 | 9 contract + 2 storage 文件（含 NovelCharacter, BatchProgress） | 全部单元测试通过 |
| M2: Agent Prompt | 6 个 Agent prompt（含 Director）+ 预设 + 6 个小说 Adapter | fake-provider 可运行 |
| M3: 引擎 MVP | NovelEngine（全新实现）+ NovelQualityPipeline + NovelSubAgentRunner | 用 fake provider 生成 1 章，5-10 个 beat |
| M4: 真实生成 | 真实 DeepSeek 调用（分级 thinking） | 3 章连续生成，无泄露，Director 输出大纲优化建议 |
| M5: Batch + 容错 | batch_write + BatchProgress + 重试/恢复 | 批量生成 5 章，中途杀死后恢复，失败章节跳过 |
| M6: API | REST 端点 + CLI | curl 可完成全流程 |
| M7: Markdown | 导入/导出 | oh-story 目录结构可读 |
| M8: ComfyUI 节点 | 8 个节点 | 可视化工作流可运行 |
