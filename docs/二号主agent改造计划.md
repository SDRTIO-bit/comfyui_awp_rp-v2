# 二号主Agent改造计划

## 一、改造范围

### 1.1 需要新增的模块

| 模块 | 文件路径 | 职责 |
|------|----------|------|
| PromptAssembler | `runtime/prompt_assembler.py` | 组装最终的Prompt（骨架+乐谱+历史+变量+玩家输入） |
| ScoreGenerator | `runtime/score_generator.py` | 生成乐谱（Director整合子Agent建议后的可执行指导） |
| EmotionalSummarizer | `runtime/emotional_summarizer.py` | 生成历史的情绪摘要 |
| OOCDetector | `runtime/ooc_detector.py` | 检测角色崩坏 |
| ContinuityChecker | `runtime/continuity_checker.py` | 检测情节连贯性 |

### 1.2 需要改造的模块

| 模块 | 文件路径 | 改造内容 |
|------|----------|----------|
| RealWriterAdapter | `adapters/llm/real_writer_adapter.py` | 重构Prompt拼接逻辑，使用PromptAssembler |
| SuggestionMerger | `runtime/suggestion_merger.py` | 从"排序器"变成"矛盾检测器" |
| DirectorRuntime | `runtime/director_runtime.py` | 新增integrate()方法，生成乐谱 |
| WriterInputBundle | `contracts/writer_input_bundle.py` | 新增score字段 |
| WriterInputBundleV2Builder | `runtime/writer_input_bundle_v2_builder.py` | 构建包含乐谱的Bundle |
| PersistentTurnEngine | `runtime/persistent_turn_engine.py` | 集成新的Prompt组装流程 |

---

## 二、详细改造计划

### 2.1 Phase 1：PromptAssembler（核心模块）

**文件**：`runtime/prompt_assembler.py`

**职责**：组装最终的Prompt，分离骨架和变量

**类设计**：
```python
class PromptAssembler:
    """组装Writer的最终Prompt"""

    def __init__(self, worldbook_entries: list[dict]):
        """
        Args:
            worldbook_entries: 完整的世界书条目列表（35000字）
        """
        self.skeleton = self._build_skeleton(worldbook_entries)

    def assemble(
        self,
        score: str,  # 乐谱
        recent_turns: list[dict],  # 最近5轮完整历史
        older_turns_summary: str,  # 更早轮次的情绪摘要
        variable_snapshot: dict,  # 变量快照
        player_input: str,  # 玩家输入
    ) -> tuple[str, str]:
        """
        组装最终的System Prompt和User Prompt

        Returns:
            (system_prompt, user_prompt)
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            score, recent_turns, older_turns_summary,
            variable_snapshot, player_input
        )
        return system_prompt, user_prompt

    def _build_skeleton(self, worldbook_entries: list[dict]) -> str:
        """构建骨架（不可变的Worldbook）"""
        # 按照排序规则：constant优先 → priority降序 → source_order升序
        sorted_entries = self._sort_worldbook(worldbook_entries)
        return self._format_skeleton(sorted_entries)

    def _build_system_prompt(self) -> str:
        """构建System Prompt（纯指令，无内容）"""
        return """You are a creative roleplay writer.

=== WRITING WORKFLOW ===
Before writing, work through:
1. Inner State — What is the character feeling right now?
2. Sensory Environment — What does the character see, hear, smell?
3. Player Action — What did the player just do? What is the immediate consequence?
4. Emotional Beat — What emotional arc are you advancing?

=== OUTPUT RULES ===
- Write narrative prose only. No labels, no prefixes, no meta-text.
- Target 1600 characters minimum. Prioritize quality over exact length.
- End at a natural pause point that invites player response.
- Never write the player's thoughts or dialogue. Only write what they see, hear, and feel."""

    def _build_user_prompt(
        self,
        score: str,
        recent_turns: list[dict],
        older_turns_summary: str,
        variable_snapshot: dict,
        player_input: str,
    ) -> str:
        """构建User Prompt"""
        parts = []

        # 1. 骨架（可缓存）
        parts.append(f"=== SKELETON (immutable setting) ===\n{self.skeleton}")

        # 2. 乐谱（每轮变化）
        parts.append(f"=== SCORE (Director's integrated direction) ===\n{score}")

        # 3. 5轮完整历史（每轮变化）
        if recent_turns:
            history_text = self._format_recent_turns(recent_turns)
            parts.append(f"=== RECENT HISTORY (full) ===\n{history_text}")

        # 4. 旧历史摘要（每轮变化）
        if older_turns_summary:
            parts.append(f"=== EARLIER HISTORY (emotional summary) ===\n{older_turns_summary}")

        # 5. 变量快照（每轮变化）
        if variable_snapshot:
            snapshot_text = self._format_variable_snapshot(variable_snapshot)
            parts.append(f"=== CURRENT STATE (volatile) ===\n{snapshot_text}")

        # 6. 玩家输入（每轮变化）
        parts.append(f"=== PLAYER INPUT ===\n{player_input}")

        return "\n\n".join(parts)
```

---

### 2.2 Phase 2：ScoreGenerator（乐谱生成）

**文件**：`runtime/score_generator.py`

**职责**：把子Agent建议整合成可执行的乐谱

**类设计**：
```python
class ScoreGenerator:
    """生成乐谱（Director整合后的可执行指导）"""

    def generate(
        self,
        director_plan: DirectorPlan,
        agent_suggestions: list[AgentSuggestion],
        snapshot: RoundSnapshot,
    ) -> str:
        """
        生成乐谱

        Args:
            director_plan: Director的规划
            agent_suggestions: 子Agent的建议列表
            snapshot: 当前快照

        Returns:
            乐谱文本（XML格式）
        """
        # 1. 检测矛盾
        conflicts = self._detect_conflicts(agent_suggestions)

        # 2. 做裁决
        resolutions = self._resolve_conflicts(conflicts, director_plan)

        # 3. 生成乐谱
        score = self._compose_score(
            director_plan, agent_suggestions, resolutions, snapshot
        )

        return score

    def _detect_conflicts(self, suggestions: list[AgentSuggestion]) -> list[dict]:
        """检测建议之间的矛盾"""
        conflicts = []
        # 检测语义矛盾（不是路径矛盾）
        for i, sug1 in enumerate(suggestions):
            for sug2 in suggestions[i+1:]:
                if self._are_semantically_conflicting(sug1, sug2):
                    conflicts.append({
                        "suggestion1": sug1,
                        "suggestion2": sug2,
                        "conflict_type": "semantic",
                    })
        return conflicts

    def _resolve_conflicts(
        self, conflicts: list[dict], director_plan: DirectorPlan
    ) -> list[dict]:
        """裁决矛盾（基于Director的规划）"""
        resolutions = []
        for conflict in conflicts:
            # 基于Director的规划做裁决
            resolution = self._director_decides(conflict, director_plan)
            resolutions.append(resolution)
        return resolutions

    def _compose_score(
        self,
        director_plan: DirectorPlan,
        suggestions: list[AgentSuggestion],
        resolutions: list[dict],
        snapshot: RoundSnapshot,
    ) -> str:
        """生成乐谱"""
        # 提取内在状态
        inner_state = self._extract_inner_state(director_plan, suggestions)

        # 提取行为线索
        behavioral_cue = self._extract_behavioral_cue(director_plan, suggestions)

        # 提取节奏指导
        pacing = director_plan.pacing_guidance or "moderate"

        # 提取禁忌
        constraints = director_plan.must_not_do + director_plan.writer_constraints

        # 格式化为XML
        return f"""<direction>
<inner_state>
{inner_state}
</inner_state>

<behavioral_cue>
{behavioral_cue}
</behavioral_cue>

<pacing>
{pacing}
</pacing>

<constraint>
{self._format_constraints(constraints)}
</constraint>
</direction>"""
```

---

### 2.3 Phase 3：EmotionalSummarizer（情绪摘要）

**文件**：`runtime/emotional_summarizer.py`

**职责**：把旧的历史回合压缩成情绪摘要

**类设计**：
```python
class EmotionalSummarizer:
    """生成历史的情绪摘要"""

    def summarize(
        self,
        turns: list[TurnRecord],
        max_turns_per_group: int = 5,
    ) -> str:
        """
        生成情绪摘要

        Args:
            turns: 旧的历史回合列表（按时间倒序）
            max_turns_per_group: 每组最多包含的轮次数

        Returns:
            情绪摘要文本
        """
        if not turns:
            return ""

        # 按组分组（每组5轮）
        groups = self._group_turns(turns, max_turns_per_group)

        # 为每组生成摘要
        summaries = []
        for group in groups:
            summary = self._summarize_group(group)
            summaries.append(summary)

        return "\n".join(summaries)

    def _summarize_group(self, turns: list[TurnRecord]) -> str:
        """为一组轮次生成情绪摘要"""
        # 提取关键情绪词
        emotions = []
        for turn in turns:
            emotion = self._extract_emotion(turn)
            if emotion:
                emotions.append(emotion)

        # 生成摘要
        if not emotions:
            return f"Turn {turns[0].turn_index}-{turns[-1].turn_index}: (no significant emotional content)"

        # 合并情绪词
        emotion_text = " → ".join(emotions)
        return f"Turn {turns[0].turn_index}-{turns[-1].turn_index}: {emotion_text}"

    def _extract_emotion(self, turn: TurnRecord) -> str:
        """从轮次中提取情绪"""
        # 简单的关键词提取（可以后续用LLM增强）
        text = turn.writer_output or ""
        emotion_keywords = {
            "happy": ["开心", "快乐", "喜悦", "笑"],
            "sad": ["悲伤", "难过", "哭", "泪"],
            "angry": ["愤怒", "生气", "怒", "恨"],
            "fear": ["害怕", "恐惧", "颤抖", "怕"],
            "surprise": ["惊讶", "震惊", "意外"],
            "disgust": ["厌恶", "恶心", "讨厌"],
        }

        for emotion, keywords in emotion_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    return emotion

        return ""
```

---

### 2.4 Phase 4：OOCDetector（角色崩坏检测）

**文件**：`runtime/ooc_detector.py`

**职责**：检测Writer输出是否符合乐谱的指导

**类设计**：
```python
class OOCDetector:
    """检测角色崩坏"""

    def detect(
        self,
        writer_output: str,
        score: str,
        previous_turn: TurnRecord | None = None,
    ) -> list[str]:
        """
        检测角色崩坏

        Args:
            writer_output: Writer的输出文本
            score: 乐谱
            previous_turn: 上一轮的TurnRecord（用于连贯性检查）

        Returns:
            问题列表（空列表表示没有问题）
        """
        issues = []

        # 1. 检测乐谱遵守
        score_violations = self._check_score_compliance(writer_output, score)
        issues.extend(score_violations)

        # 2. 检测连贯性
        if previous_turn:
            continuity_issues = self._check_continuity(writer_output, previous_turn)
            issues.extend(continuity_issues)

        return issues

    def _check_score_compliance(self, output: str, score: str) -> list[str]:
        """检查是否遵守乐谱"""
        issues = []

        # 提取乐谱中的约束
        constraints = self._extract_constraints(score)

        # 检查每个约束
        for constraint in constraints:
            if self._violates_constraint(output, constraint):
                issues.append(f"SCORE_VIOLATION: {constraint}")

        return issues

    def _check_continuity(self, output: str, previous_turn: TurnRecord) -> list[str]:
        """检查连贯性"""
        issues = []

        # 提取上一轮的事实
        previous_facts = self._extract_facts(previous_turn.writer_output)

        # 检查当前输出是否与上一轮矛盾
        current_facts = self._extract_facts(output)

        for fact in previous_facts:
            if self._contradicts(fact, current_facts):
                issues.append(f"CONTINUITY_BREAK: {fact}")

        return issues
```

---

### 2.5 Phase 5：改造RealWriterAdapter

**文件**：`adapters/llm/real_writer_adapter.py`

**改造内容**：

1. **删除** `_build_writer_system_prompt()` 中的Preset拼接逻辑
2. **删除** `_build_writer_user_prompt()` 中的平铺直叙拼接逻辑
3. **新增** `generate()` 方法，使用PromptAssembler组装Prompt

**改造后的代码结构**：
```python
class RealWriterV2Adapter:
    def __init__(self, deepseek: DeepSeekAdapter, model: str = ""):
        self._llm = deepseek
        self._model = model
        self._extra_body = {"thinking": {"type": "disabled"}}
        self._prompt_assembler = None  # 延迟初始化

    def generate(
        self,
        bundle: WriterInputBundle,
        workflow_run_id: str = "",
        trace_id: str = "",
        turn_id: str = "",
        attempt_id: str = "",
        snapshot: Any = None,
    ) -> tuple[str, ProviderAttemptReceipt]:
        """生成叙事文本"""
        # 1. 初始化PromptAssembler（如果需要）
        if self._prompt_assembler is None:
            self._prompt_assembler = PromptAssembler(bundle.worldbook_context)

        # 2. 组装Prompt
        system_prompt, user_prompt = self._prompt_assembler.assemble(
            score=bundle.score,
            recent_turns=bundle.recent_turns_context,
            older_turns_summary=bundle.older_turns_summary,
            variable_snapshot=bundle.variable_snapshot,
            player_input=bundle.player_input,
        )

        # 3. 调用LLM
        text, receipt = self._llm.generate_text(
            user_prompt,
            provider_role="writer",
            workflow_run_id=workflow_run_id,
            trace_id=trace_id,
            model=self._model,
            turn_id=turn_id,
            attempt_id=attempt_id,
            extra_body=self._extra_body,
            system_prompt=system_prompt,
        )

        # 4. 修订循环（使用OOCDetector）
        for rev in range(2):
            issues = self._detect_issues(text, bundle.score, snapshot)
            if not issues:
                break
            text = self._revise(text, issues, user_prompt, rev + 1)

        return text, receipt
```

---

### 2.6 Phase 6：改造WriterInputBundle

**文件**：`contracts/writer_input_bundle.py`

**改造内容**：

新增字段：
```python
@dataclass
class WriterInputBundle:
    # ... 现有字段 ...

    # 新增字段
    score: str = ""  # 乐谱（Director整合后的可执行指导）
    variable_snapshot: dict = field(default_factory=dict)  # 变量快照
    older_turns_summary: str = ""  # 旧历史的情绪摘要
```

---

### 2.7 Phase 7：改造WriterInputBundleV2Builder

**文件**：`runtime/writer_input_bundle_v2_builder.py`

**改造内容**：

1. 新增 `score` 参数
2. 新增 `variable_snapshot` 参数
3. 新增 `older_turns_summary` 参数
4. 调整 `recent_turns_context` 的构建逻辑（只保留最近5轮）

**改造后的代码结构**：
```python
class WriterInputBundleV2Builder:
    def build(
        self,
        snapshot: RoundSnapshot,
        final_brief: FinalTurnBrief,
        merge_result: SuggestionMergeResult | None = None,
        opening_context: dict | None = None,
        worldbook_context: list[dict] | None = None,
        score: str = "",  # 新增
        older_turns_summary: str = "",  # 新增
    ) -> WriterInputBundle:
        # 构建变量快照
        variable_snapshot = self._build_variable_snapshot(snapshot)

        # 构建最近5轮历史（完整内容）
        recent_turns_context = [
            {
                "turn_id": turn.turn_id,
                "turn_index": turn.turn_index,
                "player_input": turn.player_input,
                "writer_output": turn.writer_output,
            }
            for turn in snapshot.recent_turn_records[:5]
        ]

        return WriterInputBundle(
            # ... 现有字段 ...
            score=score,
            variable_snapshot=variable_snapshot,
            older_turns_summary=older_turns_summary,
            recent_turns_context=recent_turns_context,
        )

    def _build_variable_snapshot(self, snapshot: RoundSnapshot) -> dict:
        """构建变量快照"""
        return {
            "location": snapshot.card_state.scene_state.location,
            "time_of_day": snapshot.card_state.scene_state.time_of_day,
            "variables": {
                name: entry.value
                for name, entry in snapshot.card_state.variables.items()
            },
            "event_flags": {
                name: entry.fired
                for name, entry in snapshot.card_state.event_flags.items()
            },
        }
```

---

### 2.8 Phase 8：改造PersistentTurnEngine

**文件**：`runtime/persistent_turn_engine.py`

**改造内容**：

1. 集成ScoreGenerator
2. 集成EmotionalSummarizer
3. 调整Writer调用流程

**改造后的流程**：
```python
def execute(self, ...):
    # ... 现有的Director和子Agent逻辑 ...

    # 1. 生成乐谱
    score_generator = ScoreGenerator()
    score = score_generator.generate(
        director_plan, agent_suggestions, snapshot
    )

    # 2. 生成旧历史摘要
    summarizer = EmotionalSummarizer()
    older_turns = snapshot.recent_turn_records[5:]  # 第6轮及更早
    older_turns_summary = summarizer.summarize(older_turns)

    # 3. 构建WriterInputBundle（包含乐谱和摘要）
    bundle = WriterInputBundleV2Builder().build(
        snapshot, brief, merge_result,
        opening_context=opening_context,
        worldbook_context=worldbook_context,
        score=score,
        older_turns_summary=older_turns_summary,
    )

    # 4. 调用Writer
    candidate_text, wrt_receipt = run_writer(
        wrt_adapter, wrt_outcome, bundle,
        workflow_run_id, trace_id, turn_id, attempt_id,
        snapshot=snapshot,
    )

    # ... 现有的Quality Gate和后续逻辑 ...
```

---

## 三、实现顺序

### 3.1 Phase 1：基础模块（1-2天）

1. **PromptAssembler**：组装最终的Prompt
2. **EmotionalSummarizer**：生成情绪摘要
3. **改造WriterInputBundle**：新增score、variable_snapshot、older_turns_summary字段

### 3.2 Phase 2：乐谱机制（2-3天）

1. **ScoreGenerator**：生成乐谱
2. **改造SuggestionMerger**：从排序器变成矛盾检测器
3. **改造DirectorRuntime**：新增integrate()方法

### 3.3 Phase 3：集成改造（2-3天）

1. **改造RealWriterAdapter**：使用PromptAssembler
2. **改造WriterInputBundleV2Builder**：构建包含乐谱的Bundle
3. **改造PersistentTurnEngine**：集成新的流程

### 3.4 Phase 4：语义检查（1-2天）

1. **OOCDetector**：检测角色崩坏
2. **ContinuityChecker**：检测连贯性
3. **改造修订循环**：使用新的检测器

---

## 四、验收标准

### 4.1 PromptAssembler

- [ ] 骨架（35000字Worldbook）100%可缓存
- [ ] 乐谱、历史、变量、玩家输入在Prompt末尾
- [ ] 历史更新不影响缓存

### 4.2 ScoreGenerator

- [ ] 能检测子Agent建议之间的语义矛盾
- [ ] 能基于Director规划做裁决
- [ ] 生成的乐谱格式符合XML规范

### 4.3 EmotionalSummarizer

- [ ] 能把旧的历史回合压缩成情绪摘要
- [ ] 摘要保留情绪弧光
- [ ] 摘要格式符合规范

### 4.4 OOCDetector

- [ ] 能检测角色崩坏
- [ ] 能检测情节矛盾
- [ ] 能检测乐谱违反

### 4.5 整体集成

- [ ] Writer看到的是可执行的乐谱，不是矛盾的建议列表
- [ ] 缓存覆盖率稳定在75%-85%
- [ ] 输出质量提升（OOC减少、连贯性提高）

---

## 五、风险评估

### 5.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| PromptAssembler性能问题 | 响应延迟增加 | 优化字符串拼接逻辑 |
| ScoreGenerator误判矛盾 | 乐谱质量下降 | 添加人工审核机制 |
| OOCDetector误报 | 修订循环次数增加 | 调整检测阈值 |

### 5.2 业务风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 输出风格变化 | 用户体验变化 | 保留旧版本作为fallback |
| 缓存命中率下降 | 成本增加 | 监控缓存覆盖率 |

---

## 六、回滚方案

如果改造后出现问题，可以快速回滚：

1. **代码回滚**：git revert 到改造前的commit
2. **配置回滚**：保留旧的Prompt拼接逻辑作为fallback
3. **渐进式上线**：先在测试环境验证，再逐步推广到生产环境
