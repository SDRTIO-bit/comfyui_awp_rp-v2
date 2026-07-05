# oh-story-claudecode 吸收计划

Date: 2026-07-04

> **配套文档**：本文档描述"怎么搬"（代码实现），[oh-story-core-prompts.md](./2026-07-04-oh-story-core-prompts.md) 描述"搬什么"（prompt 内容）。两份文档对照阅读。

## 定位

oh-story-claudecode 是一套 Claude Code skill 包——没有 Python 代码、没有数据库、没有 API 服务器。它的"引擎"是 Claude Code 本身，通过极其详细的 prompt 指导 LLM 按专业网文创作流程工作。

AWP 的小说模式要做的不是"复刻"它，而是**把它的方法论工程化**——把 prompt 中的规则变成代码、把文件系统变成 SQLite、把 Claude Code 的子代理调度变成 SubAgentLLMRunner。

## 文档关系图

```
oh-story-core-prompts.md（搬什么）
  ├── Chapter Writer 16条规则 ──→ 写入 Chapter Writer system prompt
  ├── Director 7条规则 ──→ 写入 Director system prompt
  ├── Continuity Checker 3条规则 ──→ 写入 Continuity Checker system prompt
  ├── Style Cleaner 4条规则 ──→ 写入 Style Cleaner system prompt
  ├── Architect 3条规则 ──→ 写入 Architect system prompt
  └── 状态筛选 3条规则 ──→ 写入 NovelWritePacketBuilder

oh-story-absorption-plan.md（怎么搬）
  ├── 禁用词表/元信息/退化/标点 ──→ Python 代码（质量门控）
  ├── 细纲模板 ──→ ChapterPlan 契约
  ├── 写前三步 ──→ NovelWritePacketBuilder
  ├── 对标书管理 ──→ ReferenceBook 契约
  ├── 日更工作流 ──→ batch_write()
  └── Markdown 协议 ──→ 导入/导出器
```

## 能直接用的（原样搬进 AWP）

### 1. 禁用词表

> **Prompt 对应**：这些禁用词在 [oh-story-core-prompts.md](./2026-07-04-oh-story-core-prompts.md) 四、Style Cleaner 第4.2节中有完整的使用说明（"最毒禁用句式，出现即修"）。

oh-story 的 `banned-words.md` 有两级禁用词，比 AWP 的 `kedai_heavy_v1.txt` Gate A 更完整：

```python
# runtime/novel_quality_pipeline.py

BANNED_WORDS_TIER1 = {
    # 情态类
    "仿佛", "犹如", "宛若", "如同", "一丝", "一抹", "些许", "几分", "隐约",
    # 动作类
    "深吸一口气", "缓缓", "不禁", "微微", "轻轻", "淡淡",
    # 表情类
    "眼中闪过", "嘴角勾起", "眉头微皱", "眉眼低垂", "瞳孔微缩",
    # 心理类
    "心中一动", "心头一震", "心下了然", "心中暗道", "心底泛起", "不由得",
    # 判断类
    "不容置疑", "不容置喙", "不易察觉", "显而而易见", "毫无疑问", "不可否认",
    # 形容类
    "坚定", "闪烁着光芒", "狡黠", "深邃", "凛冽", "冰冷",
    # 过渡类
    "不由自主", "情不自禁", "自然而然",
}

BANNED_WORDS_TIER2 = {
    # 语境敏感词，高频出现时才替换
    "突然", "好像", "瞬间",
}

BANNED_PATTERNS = [
    # 最毒句式，出现即修
    r"不是.{1,20}，(?:而)?是",      # "不是A，而是B"
    r"，带着[一几分些]",              # "，带着一丝..."
    r"声音不大，却带着",             # "声音不大，却带着一种..."
    r"眼中闪过一丝",                 # "眼中闪过一丝..."
    r"嘴角勾起一抹",                 # "嘴角勾起一抹..."
    r"心中涌起一股",                 # "心中涌起一股..."
    r"他不知道的是",                 # 章末预告
    r"终于明白了",                   # 总结句式
    r"这才意识到",                   # 总结句式
    r"仿佛.{2,10}一般",             # "仿佛...一般"
]

BANNED_ENDING_PATTERNS = [
    r"他终于明白了",                 # 总结性感悟
    r"这一夜，注定",                 # 升华式感叹
    r"人生就是这样",                 # 哲理式收尾
    r"他不知道的是，",               # 伏笔式预告
]
```

### 2. 元信息泄露检测

oh-story 的工程词泄露检测，直接搬进质量门控：

```python
# runtime/novel_quality_pipeline.py

import re

# 标题行以外不得出现的工程词
METADATA_LEAK_PATTERN = re.compile(
    r"第[一二三四五六七八九十百千万两0-9]+章"
    r"|上一章|上章|前一章|本章|这一章"
    r"|前文|后文|伏笔|细纲|读者"
)

def check_metadata_leak(text: str) -> list[str]:
    """检测正文中是否混入工程元信息。"""
    issues = []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        # 跳过标题行（第一行如果是 # 开头）
        if i == 0 and line.startswith("#"):
            continue
        matches = METADATA_LEAK_PATTERN.findall(line)
        if matches:
            issues.append(f"行{i+1}: 检测到工程词泄露 {matches}")
    return issues
```

### 3. 退化检测

oh-story 的 `check-degeneration.js` 检测复读、截断、AI 拒绝语。转为 Python：

```python
# runtime/novel_quality_pipeline.py

import re

def check_degeneration(text: str) -> list[dict]:
    """检测模型退化：复读、截断、AI拒绝语、工程词泄露。"""
    issues = []

    # 1. 复读检测：同一句话出现 3 次以上
    sentences = re.split(r'[。！？\n]', text)
    seen = {}
    for s in sentences:
        s = s.strip()
        if len(s) < 5:
            continue
        seen[s] = seen.get(s, 0) + 1
        if seen[s] >= 3:
            issues.append({
                "type": "repetition",
                "severity": "blocking",
                "detail": f"复读: '{s}' 出现 {seen[s]} 次",
            })

    # 2. 截断检测：末尾不完整
    last_50 = text[-50:].strip()
    if last_50 and last_50[-1] not in "。！？」』）】":
        issues.append({
            "type": "truncation",
            "severity": "blocking",
            "detail": "末尾可能被截断",
        })

    # 3. AI 拒绝语检测
    ai_refusal_patterns = [
        r"作为AI", r"作为语言模型", r"我无法续写",
        r"（此处省略）", r"此处省略", r"�",
        r"抱歉，我", r"对不起，我",
    ]
    for pattern in ai_refusal_patterns:
        if re.search(pattern, text):
            issues.append({
                "type": "ai_refusal",
                "severity": "blocking",
                "detail": f"检测到AI拒绝语: {pattern}",
            })

    # 4. 工程词泄露（tier1 纯工程词）
    tier1_engineering_words = ["细纲", "情节点", "卷纲", "功能标签", "字数预算"]
    for word in tier1_engineering_words:
        if word in text:
            issues.append({
                "type": "engineering_leak",
                "severity": "blocking",
                "detail": f"工程词泄露: '{word}'",
            })

    return issues
```

### 4. 标点归一化

oh-story 的 `normalize-punctuation.js` 清理残留标点。转为 Python：

```python
# runtime/novel_quality_pipeline.py

def normalize_punctuation(text: str) -> str:
    """清理残留的不规范标点。"""
    # 清除省略号（用句号或逗号替代）
    text = text.replace("……", "。")
    text = text.replace("......", "。")
    # 清除破折号
    text = text.replace("——", "，")
    text = text.replace("—", "，")
    text = text.replace("--", "，")
    # 清除独立行 ---
    text = re.sub(r"\n---\n", "\n", text)
    text = re.sub(r"\n---$", "\n", text)
    return text
```

### 5. 字数预算校验

oh-story 的 beat 字数预算机制——每个 beat 标"密/疏"并给字数预算，总和必须落在 [章目标, 章目标×1.1]：

```python
# runtime/novel_quality_pipeline.py

def validate_beat_budget(chapter_plan: "ChapterPlan") -> list[str]:
    """校验 SceneBeat 字数预算总和是否在合理范围。"""
    issues = []
    total_budget = sum(b.budget_chars for b in chapter_plan.scene_beats)
    target = chapter_plan.target_chars

    if total_budget < target:
        issues.append(
            f"beat 预算合计 {total_budget} < 章目标 {target}，需补充展开点"
        )
    elif total_budget > target * 1.1:
        issues.append(
            f"beat 预算合计 {total_budget} > 章目标上限 {target * 1.1}，需压缩过场"
        )

    # 检查是否有 beat 没标密度
    for beat in chapter_plan.scene_beats:
        if beat.density not in ("dense", "normal", "sparse"):
            issues.append(f"beat '{beat.description[:20]}' 缺少密度标记")

    return issues
```

### 6. 质量检查清单

oh-story 的 `quality-checklist.md` 转为确定性检查函数：

```python
# runtime/novel_quality_pipeline.py

def check_chapter_structure(text: str) -> list[str]:
    """章节结构检查。"""
    issues = []
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    if not paragraphs:
        issues.append("正文为空")
        return issues

    # 开头检查（前 500 字）
    opening = text[:500]
    weather_words = ["天气", "阳光", "微风", "月色", "星空"]
    if any(w in opening[:100] for w in weather_words):
        issues.append("开头从天气/风景开始，缺少钩子")

    # 结尾检查（最后 300 字）
    ending = text[-300:]
    summary_patterns = ["终于明白", "这才意识到", "此刻，", "一切", "原来"]
    if any(p in ending for p in summary_patterns):
        issues.append("结尾是总结式收束，应改为动作/悬念收束")

    # 水检测：连续 2 段以上纯情绪无事件
    # （简化实现，实际可用 LLM 辅助判断）

    return issues

def check_filler(text: str) -> list[str]:
    """水字数检测。"""
    issues = []
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    # 连续 3 段以上同一情绪词
    emotion_words = ["愤怒", "悲伤", "开心", "紧张", "恐惧", "惊讶"]
    for word in emotion_words:
        count = sum(1 for p in paragraphs if word in p)
        if count >= 3:
            issues.append(f"情绪词 '{word}' 出现 {count} 次，可能重复")

    return issues
```

---

## 需要工程化的（方法论 → 代码）

### 7. 细纲模板 → ChapterPlan 契约

> **Prompt 对应**：细纲模板的完整规则见 [oh-story-core-prompts.md](./2026-07-04-oh-story-core-prompts.md) 五、Architect 第5.1节（11个维度）。

oh-story 的细纲模板包含 7 个维度，AWP 的 ChapterPlan 需要对齐：

```python
# contracts/novel_chapter.py — 扩展 ChapterPlan

@dataclass(frozen=True)
class ContentSummary:
    """内容概括五段式。"""
    cause: str          # 起因：本章事件为什么发生
    development: str    # 发展：冲突如何推进
    turning_point: str  # 转折：信息/关系/局势哪里改变
    climax: str         # 高潮：本章情绪或动作峰值
    ending: str         # 结尾：收束到什么状态

@dataclass(frozen=True)
class PlotArrangement:
    """情节安排（多线）。"""
    main_line: str          # 主线推进
    sub_line: str           # 辅线推进
    event_line: str         # 事件线/任务线
    emotion_line: str       # 感情线/关系线
    logic_line: str         # 逻辑线：原因→行动→结果→后果

@dataclass(frozen=True)
class CharacterAppearance:
    """人物关系和出场顺序。"""
    appearance_order: list[str]     # 出场顺序
    relationship_changes: list[str] # 人物关系变化
    information_gap: str            # 视角/信息差

@dataclass(frozen=True)
class BeatDetail:
    """情节点细化（对齐 oh-story 的 beat 预算）。"""
    beat_id: str
    description: str        # 谁做了什么
    function_tag: str       # 功能标签：铺垫/高潮/爽点/打脸/人物塑造/设定
    density: str            # 密/疏
    budget_chars: int       # 字数预算

@dataclass(frozen=True)
class EndingDesign:
    """结尾设定和钩子。"""
    closing_state: str      # 收束状态
    open_questions: list[str]  # 未解决问题
    next_chapter_push: str  # 下一章推动力
    hook_type: str          # 钩子类型
    hook_detail: str        # 钩子具体内容
    hook_strength: str      # 强/中/弱

@dataclass(frozen=True)
class ChapterPlan:
    schema_id: str = "awp.novel.chapter-plan.v1"
    chapter_id: str
    project_id: str
    volume_id: str
    chapter_index: int
    title: str
    target_chars: int
    chapter_position: str
    target_emotion: str
    opening_hook: str
    main_payoff: str

    # 从 oh-story 吸收的扩展字段
    content_summary: ContentSummary
    plot_arrangement: PlotArrangement
    character_appearance: CharacterAppearance
    scene_beats: list[BeatDetail]
    ending_design: EndingDesign
    cost_and_reward: str
```

### 8. 写前三步 → NovelWritePacketBuilder

> **Prompt 对应**：写前三步的完整规则见 [oh-story-core-prompts.md](./2026-07-04-oh-story-core-prompts.md) 六、状态筛选（6.1 本节速记、6.2 模块召回、6.3 意图确认）。

oh-story 的"状态筛选 → 模块召回 → 意图确认"三步写前准备，工程化为 NovelWritePacket 的构建过程：

```python
# runtime/novel_write_packet_builder.py

class NovelWritePacketBuilder:
    """构建 NovelWritePacket，实现 oh-story 的写前三步。"""

    def build(
        self,
        chapter_plan: ChapterPlan,
        ledger_items: list[LedgerItem],
        previous_chapter_summary: str,
        reference_books: list[dict],
        director_guidance: DirectorGuidance,
    ) -> NovelWritePacket:
        # Step 1: 状态筛选 — 只保留"不知道就会写错"的信息
        relevant_items = self._filter_relevant_ledger(chapter_plan, ledger_items)
        relevant_characters = self._filter_relevant_characters(chapter_plan)

        # Step 2: 模块召回 — 从对标书找情绪/节奏/文风参考
        emotion_module = self._recall_emotion_module(chapter_plan, reference_books)
        rhythm_reference = self._recall_rhythm(chapter_plan, reference_books)
        style_profile = self._recall_style(reference_books)

        # Step 3: 意图确认 — 一句话概括本章写作目标
        writing_intent = self._confirm_intent(
            chapter_plan, emotion_module, rhythm_reference, director_guidance
        )

        return NovelWritePacket(
            chapter_plan=chapter_plan,
            previous_chapter_summary=previous_chapter_summary,
            relevant_ledger_items=relevant_items,
            character_states=relevant_characters,
            director_guidance=director_guidance,
            writing_intent=writing_intent,  # 新增字段
            emotion_module=emotion_module,   # 新增字段
            rhythm_reference=rhythm_reference,  # 新增字段
            style_profile=style_profile,
            benchmark_snippets=self._load_benchmarks(chapter_plan, reference_books),
        )

    def _filter_relevant_ledger(
        self, plan: ChapterPlan, items: list[LedgerItem]
    ) -> list[LedgerItem]:
        """只保留本章涉及的 ledger 条目。"""
        relevant = []
        plan_text = f"{plan.content_summary.cause} {plan.content_summary.development}"
        for item in items:
            if item.entity in plan_text or item.status == "active":
                relevant.append(item)
        return relevant

    def _confirm_intent(
        self, plan, emotion_module, rhythm, guidance
    ) -> str:
        """一句话写作意图。"""
        parts = []
        parts.append(f"目标情绪: {plan.target_emotion}")
        parts.append(f"节奏: {guidance.pacing_strategy}")
        if emotion_module:
            parts.append(f"情绪模块: {emotion_module.get('name', '无')}")
        if rhythm:
            parts.append(f"节奏参考: {rhythm.get('name', '无')}")
        return " | ".join(parts)
```

### 9. 对标书管理 → ReferenceLibrary

oh-story 的"拆文库 → 对标/"体系，工程化为 AWP 的对标书管理：

```python
# contracts/novel_reference.py

@dataclass(frozen=True)
class ReferenceBook:
    """对标书。"""
    schema_id: str = "awp.novel.reference-book.v1"
    book_id: str
    project_id: str
    name: str
    role: str           # "primary" / "secondary" / "benchmark"
    genre: str
    total_chapters: int
    style_profile: str      # 文风描述
    emotion_modules: list[dict]  # 情绪模块
    rhythm_profile: dict    # 节奏特征
    chapter_summaries: list[dict]  # 章节摘要
    deconstruction_report: str  # 拆文报告

# storage/novel_interfaces.py

class ReferenceBookStore(ABC):
    def save(self, book: ReferenceBook) -> None: ...
    def load(self, book_id: str) -> ReferenceBook: ...
    def list_by_project(self, project_id: str) -> list[ReferenceBook]: ...
    def search_by_emotion(self, project_id: str, emotion: str) -> list[ReferenceBook]: ...
```

### 10. 追踪文件 → ContinuityLedger（已覆盖，补充格式）

oh-story 的追踪文件格式非常精细，AWP 的 ContinuityLedger 应该对齐：

```python
# runtime/novel_ledger_curator.py — Ledger 更新规则

# 伏笔状态机
FORESHADOWING_STATES = {
    "planted": "active",      # 已埋设
    "advanced": "active",     # 已推进
    "paid_off": "resolved",   # 已回收
    "stale": "stale",         # 过期未回收
    "contradicted": "contradicted",  # 被矛盾
}

# 角色状态快照格式（对齐 oh-story 的 state-tracking.md）
CHARACTER_STATE_TEMPLATE = """
## {name}
- 身份: {identity}
- 能力: {ability}
- 关系: {relationships}
- 公众形象: {public_image}
- 最近变化: {recent_changes}
- 变更记录:
  - 第{N}章: {change_description}
"""
```

---

## 需要适配的（方法论 → AWP 架构）

### 11. Agent 映射

oh-story 的 6 个 Agent 映射到 AWP 的小说 Agent：

| oh-story Agent | AWP 小说 Agent | 复用方式 |
|----------------|---------------|---------|
| `story-architect` | Director + Architect | Director 做全局优化，Architect 做章节规划 |
| `character-designer` | 无独立 Agent | 角色设定由 Architect 在 Phase 2 完成 |
| `narrative-writer` | Chapter Writer | 直接对应，prompt 需重写 |
| `consistency-checker` | Continuity Checker | 直接对应 |
| `story-explorer` | 子代理工具集 | 用 SubAgentLLMRunner 的工具调用替代 |
| `story-researcher` | 无独立 Agent | 可选，后续扩展 |

### 12. 质量门控流程

> **Prompt 对应**：12 步检查中需要语义理解的部分（一致性检查、去AI味审查）的 prompt 规则见 [oh-story-core-prompts.md](./2026-07-04-oh-story-core-prompts.md) 三、Continuity Checker 和四、Style Cleaner。

oh-story 的 Phase 5 质量检查有 12 步，映射到 AWP 的质量门控：

```
oh-story 的 12 步检查:
1. 禁用词扫描       → NovelQualityPipeline.check_banned_words()
2. 标题去重检查     → NovelQualityPipeline.check_title_duplicates()
3. 正文元信息扫描   → NovelQualityPipeline.check_metadata_leak()
4. 钩子检查         → NovelQualityPipeline.check_chapter_hook()
5. 对照细纲核对     → NovelQualityPipeline.check_plan_alignment()
6. 伏笔盘点         → NovelQualityPipeline.check_foreshadowing()
7. AI句式脚本复扫   → NovelQualityPipeline.check_ai_patterns()
8. 标点归一化       → NovelQualityPipeline.normalize_punctuation()
9. 退化防护         → NovelQualityPipeline.check_degeneration()
10. 一致性检查       → ContinuityChecker Agent (LLM)
11. 去AI味审查       → StyleCleaner Agent (LLM)
12. 字数验证         → NovelQualityPipeline.check_word_count()
```

### 13. 日更批量工作流

oh-story 的 `workflow-daily.md` 映射到 AWP 的 `batch_write()`：

```python
# runtime/novel_engine.py

async def batch_write(
    self,
    *,
    project_id: str,
    chapter_start: int,
    chapter_end: int,
    on_chapter_complete: Callable | None = None,
) -> list[ChapterDraft]:
    """
    批量连续生成。对齐 oh-story 的 workflow-daily.md。

    关键约束（从 oh-story 吸收）：
    - 串行执行，不并发（上一章正文是下一章的输入）
    - 每章写完立即更新 Ledger（伏笔/时间线/角色状态）
    - 每 3 章做一次中途快照
    - 细纲不存在时自动补建
    """
    drafts = []
    for chapter_index in range(chapter_start, chapter_end + 1):
        # 1. 检查细纲是否存在
        plan = self._registry.novel_chapter_plan_store.load_by_index(
            project_id, chapter_index
        )
        if plan is None:
            plan = self.plan_chapter(project_id=project_id, chapter_index=chapter_index)

        # 2. 写正文
        draft = self.write_chapter(
            project_id=project_id, chapter_index=chapter_index
        )
        drafts.append(draft)

        # 3. 每章写完更新 Ledger
        # （write_chapter 内部已调用 Ledger Curator）

        # 4. 每 3 章做中途快照
        if (chapter_index - chapter_start + 1) % 3 == 0:
            self._save_progress_snapshot(project_id, chapter_index)

        # 5. 回调
        if on_chapter_complete:
            on_chapter_complete(chapter_index, draft)

    return drafts
```

---

## 不能直接用的（需要重新设计）

### 14. 文件系统 vs SQLite

oh-story 用文件系统管理所有状态（.md 文件），AWP 用 SQLite。两者的转换：

| oh-story 文件 | AWP SQLite 表 | 说明 |
|--------------|--------------|------|
| `设定/角色/{名}.md` | `novel_characters` 表 | 需要新建 |
| `大纲/细纲_第N章.md` | `novel_chapter_plans` 表 | 已规划 |
| `正文/第N章_章名.md` | `novel_chapter_drafts` 表 | 已规划 |
| `追踪/伏笔.md` | `novel_ledger_items` 表（section=foreshadowing） | 已规划 |
| `追踪/时间线.md` | `novel_ledger_items` 表（section=timeline） | 已规划 |
| `追踪/角色状态.md` | `novel_ledger_items` 表（section=character_state） | 已规划 |
| `追踪/上下文.md` | `novel_progress_snapshot` 表 | 需要新建 |
| `对标/{书名}/` | `novel_reference_books` 表 | 需要新建 |

### 15. Markdown 导入/导出

oh-story 的 Markdown 目录结构是它的"API"。AWP 的导入/导出器必须能读写这个格式：

```python
# runtime/novel_markdown_exporter.py

class NovelMarkdownExporter:
    """导出为 oh-story 兼容的目录结构。"""

    def export_project(self, project_id: str, output_dir: str) -> None:
        """
        导出结构：
        {书名}/
        ├── 设定/
        │   ├── 世界观/{主题}.md
        │   ├── 角色/{名}.md
        │   ├── 势力/{名}.md
        │   ├── 关系.md
        │   └── 题材定位.md
        ├── 大纲/
        │   ├── 大纲.md
        │   ├── 卷纲_第X卷.md
        │   └── 细纲_第XXX章.md
        ├── 正文/
        │   └── 第XXX章_章名.md
        ├── 追踪/
        │   ├── 伏笔.md
        │   ├── 时间线.md
        │   ├── 角色状态.md
        │   └── 上下文.md
        └── 对标/
            └── {书名}/
        """
        # 从 SQLite 读取数据，写入 Markdown 文件
        ...

# runtime/novel_markdown_importer.py

class NovelMarkdownImporter:
    """从 oh-story 目录结构导入。"""

    def import_project(self, project_dir: str) -> tuple[NovelProject, list[str]]:
        """导入并返回 validation_warnings。"""
        # 读取 Markdown 文件，写入 SQLite
        ...
```

---

## 文件清单更新

吸收 oh-story 后，新增以下文件：

```
runtime/
├── novel_write_packet_builder.py    # 写前三步（状态筛选→模块召回→意图确认）
├── novel_degeneration_checker.py    # 退化检测（复读/截断/AI拒绝/工程词泄露）
├── novel_punctuation_normalizer.py  # 标点归一化
└── novel_filler_detector.py         # 水字数检测

contracts/
├── novel_reference.py               # ReferenceBook, EmotionModule, RhythmProfile
└── novel_character.py               # NovelCharacter（角色管理）

presets/
├── banned_words_tier1.txt           # 一级禁用词（从 oh-story 搬入）
├── banned_words_tier2.txt           # 二级禁用词
├── banned_patterns.txt              # 禁用句式
└── quality_checklist.md             # 质量检查清单
```

修改文件：

```
contracts/novel_chapter.py           # 扩展 ChapterPlan（+ContentSummary, PlotArrangement 等）
runtime/novel_quality_pipeline.py    # 吸收禁用词/元信息/退化/标点检查
runtime/novel_engine.py              # batch_write 吸收日更工作流约束
```

---

## 总结

oh-story-claudecode 是一份**极其详细的网文创作方法论**，AWP 要做的不是复刻它（那是 Claude Code skill 包的活），而是：

1. **搬数据**：禁用词表、质量检查清单、标点归一化规则 → 直接变成 Python 代码
2. **搬流程**：写前三步、日更批量约束、退化检测 → 工程化为运行时方法
3. **搬结构**：细纲模板、角色状态快照、追踪文件格式 → 对齐到 AWP 契约
4. **搬协议**：Markdown 目录结构、导入/导出格式 → 作为 AWP 的文件交换协议
5. **搬 prompt**：6 个 Agent 的核心指令 → 直接写入 AWP 的 system prompt（详见 [核心 Prompt 提取](./2026-07-04-oh-story-core-prompts.md)）

AWP 比 oh-story 强的地方：SQLite 持久化、幂等重放、子代理 LLM 调用、REST API、ComfyUI 集成、多会话管理。oh-story 比 AWP 强的地方：方法论极其详细、禁用词表完整、质量检查清单全面、日更工作流成熟、写作 prompt 经过实战验证。

两者结合 = **方法论 + 工程化 = 真正能用的 AI 小说写作引擎**。
