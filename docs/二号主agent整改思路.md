# 二号主Agent（Writer）整改思路

## 一、原有架构存在的问题

### 1.1 优先级幻觉

**问题描述**：
将 `PRESET` 放在 System Prompt 最前面，并标注 `(highest priority)`，紧接着塞入 `SYSTEM_PROMPT_WRITER`。

**根本原因**：
- Transformer的注意力机制对序列末尾的指令更敏感（recency bias）
- DeepSeek的System Prompt处理实际上是拼接在messages最前面，离生成点最远
- 标注的`(highest priority)`在模型眼里只是一串普通token，没有任何语义特权

**后果**：
当Preset要求"极简白描"，而基础系统提示词要求"丰富感官细节"时，模型处理的是线性拼接的上下文，而不是声明的"覆盖逻辑"。输出是两种指令的随机插值，而不是预设覆盖。

---

### 1.2 截断暴政

**问题描述**：
代码中充斥硬编码的字符截断：玩家输入`500字符`、历史回合`400字`、活跃记忆`8条×160字`、RAG`6条×160字`。

**根本原因**：
- 假设信息均匀分布在文本中，但叙事文本的信息密度是高度不均匀的
- 混淆了"压缩"和"截断"——压缩保留语义，截断保留位置

**后果**：
- 叙事历史的关键转折点可能发生在第401个字符，直接切掉
- RAG召回的第7条记忆可能是解开当前谜题的钥匙，因"长度限制"直接丢弃
- 这不是上下文压缩，是上下文阉割

---

### 1.3 缓存失效噩梦

**问题描述**：
将Worldbook + Opening固定在"Stable Block"用于Provider Prefix Caching。

**根本原因**：
- 假设"稳定=有用"，但不变的内容可能已经过时
- Worldbook在RP中更新频率极高（角色受伤、物品丢失、地图解锁）

**后果**：
- 一旦Worldbook有一条更新，整个Stable Block的Hash前缀改变，整段缓存全部作废
- 为了保缓存而死守过时设定（OOC），或为了保剧情而频繁冲刷缓存（性能崩盘）
- 开场白在第50轮时仍然占据缓存窗口，但信息增益为零

---

### 1.4 修订循环无防御能力

**问题描述**：
修订逻辑仅检查`长度 < 1000`或`> 1600`字符，或检测"格式错误"。

**根本原因**：
- 把"可量化的简单指标"当作"质量的代理变量"
- 这些指标和真正的叙事质量之间的相关性很弱

**后果**：
- 角色崩坏（OOC）→ 字数可能完美，但角色行为完全错误
- 情节悖论 → 格式可能正确，但逻辑自相矛盾
- 前后吃书 → 不会触发任何现有检查
- 错误的输出被保存为`Recent Turns`，成为下一轮的上下文，错误被放大

---

### 1.5 数据沙拉式拼接

**问题描述**：
User Prompt里的动态区块罗列了`Scene`、`Turn goal`、`Must preserve`、`Risks`、`Recent Turns`、`Memories`、`RAG`、`Sub_agent`，全部用`---`分隔符平铺。

**根本原因**：
- 假设模型会"理解"分隔符背后的语义层级
- 模型看到的只是token序列，没有元认知能力去推断"这段比那段更重要"

**后果**：
- `Must preserve`（硬约束）和`Opportunities`（软建议）在prompt里的视觉权重完全一样
- Director的核心约束落在动态区块的中前部，正好是"Lost-in-the-Middle"的危险区
- 模型无法区分"法律条文"和"天气预告"

---

### 1.6 子代理噪音污染

**问题描述**：
子代理（D1-D5）产出的建议经过`SuggestionMerger`合并后，直接截断8条×200字符塞给Writer。

**根本原因**：
- 假设"所有子代理建议都是正向增益"
- 完全没考虑负向噪音干扰
- 冲突检测是基于`proposed_state_changes`的路径冲突，不是语义冲突

**后果**：
- D1说"角色A应该警惕"，D4说"角色A应该信任" → 两条建议都被采纳
- Writer收到矛盾信号，写出"既要...又要...还要..."的讨好型人格段落
- 角色不像活人，像在开董事会表决

---

### 1.7 RP核心要素缺失

**问题描述**：
代码对RP的三个核心要素——灵魂（Persona）、潜台词（Subtext）、情绪弧光（Emotional Arc）完全视而不见。

**具体表现**：

**灵魂被降级为静态预设**：
- 角色的语气（如"傲娇"、"阴郁"）被当作死板的"风格标签"贴上去
- 无法适应情绪变化：第1轮的"温柔"和第10轮的"温柔"内涵完全不同

**潜台词被截断谋杀**：
- 玩家输入截断到500字，可能丢失核心意图
- 没有保留动作/对话/内心的结构标记
- Writer无法区分"她让别人看到的"和"她藏在心里的"

**情绪弧光被轮次计数切断**：
- 5轮的"鱼缸记忆"不够
- 一个需要10轮铺垫的情绪爆发，因为超出历史窗口而失去上下文
- Writer看到爆发时的上下文是缺失的，编造平庸的理由去圆场

---

## 二、整改思路

### 2.1 核心设计哲学

**原则1：骨架与变量分离**
- 骨架（Skeleton）：不变的设定文本，可缓存
- 变量（Variables）：当前状态的精确快照，不缓存
- 边界判定：信息的"反义"会导致输出截然不同 → 它是变量

**原则2：决策整合而非信息汇聚**
- 子Agent是感官，各自感知世界的不同方面
- Director是大脑，把感官信号整合成连贯认知
- Writer是手，执行大脑的决定，不需要知道感官的原始数据

**原则3：情感驱动而非事实驱动**
- RP的核心不是"发生了什么"，而是"角色对此有什么感受"
- 保留情绪曲线，丢掉废话原文
- 时间窗口基于情绪弧光，不是轮次计数

---

### 2.2 整体架构重构

#### Prompt结构

```
┌─────────────────────────────────────────────────────────────────┐
│                        System Prompt                            │
│  角色定义 + 写作规则（400 Token，100%可缓存）                    │
├─────────────────────────────────────────────────────────────────┤
│                        User Prompt                              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  骨架（Skeleton）                                         │  │
│  │  35000字Worldbook完整保留（50000-70000 Token，100%可缓存） │  │
│  │  排序规则：constant优先 → priority降序 → source_order升序  │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  乐谱（Score）                                            │  │
│  │  Director整合后的可执行指导（300 Token，每轮变化）         │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  5轮完整历史（12000-16000 Token，每轮变化）               │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  旧历史摘要（500-1000 Token，每轮变化）                   │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  变量快照（100 Token，每轮变化）                          │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  玩家输入（750-1000 Token，每轮变化）                     │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

### 2.3 模块详解

#### 模块1：System Prompt（角色定义层）

**职责**：定义Writer的身份、工作流、输出规则

**内容**：
```
You are a creative roleplay writer.

=== WRITING WORKFLOW ===
Before writing, work through:
1. Inner State — What is the character feeling right now?
2. Sensory Environment — What does the character see, hear, smell?
3. Player Action — What did the player just do? What is the immediate consequence?
4. Emotional Beat — What emotional arc are you advancing?

=== OUTPUT RULES ===
- Write narrative prose only. No labels, no prefixes, no meta-text.
- Target 1000-1600 characters. Prioritize quality over exact length.
- End at a natural pause point that invites player response.
- Never write the player's thoughts or dialogue. Only write what they see, hear, and feel.
```

**设计原则**：
- 纯指令，无内容（内容在User Prompt里）
- 400 Token以内，100%可缓存
- 不包含任何会变化的信息

---

#### 模块2：骨架（Skeleton）

**职责**：提供不变的设定背景

**内容来源**：
- 世界观的物理法则（"魔法需要消耗生命力"）
- 历史背景（"百年前的那场大战"）
- 种族/阵营的静态描述（"精灵族长寿但傲慢"）
- 角色的核心性格特质（"他天生多疑"）

**边界判定原则**：
```
如果一个信息的"反义"会导致Writer输出截然不同 → 它是变量
如果一个信息的"反义"只是让描写稍有不同 → 它可以进骨架
```

**例子**：
- "他讨厌你" → 变量（会改变整个互动基调）
- "他是个矮人" → 骨架（只影响外貌描写）

**世界书排序规则**（已在代码中实现）：
```python
binding_entries.sort(
    key=lambda item: (
        0 if item.get("constant", False) else 1,  # constant优先
        -int(catalog_by_id.get(item.get("entry_id", ""), {}).get("priority", 0) or 0),  # priority降序
        int(catalog_by_id.get(item.get("entry_id", ""), {}).get("source_order", 0) or 0),  # source_order升序
    )
)
```

**缓存策略**：100%可缓存，版本化管理（故事重大转折时更新版本）

---

#### 模块3：乐谱（Score）

**职责**：Director整合子Agent建议后的可执行指导

**来源流程**：
```
子Agent建议 → SuggestionMerger检测矛盾 → Director做裁决 → 生成乐谱
```

**格式**：
```xml
=== SCORE (Director's integrated direction) ===

<inner_state>
她想要面对真相，但害怕真相会摧毁她精心构建的假象。
这种恐惧不是理性的，是身体层面的——胃在收缩，手在发抖。
</inner_state>

<behavioral_cue>
她伸手去碰门把手，但在触碰的瞬间缩回来。
这个"缩回来"不是决定，是本能。
然后她再次伸手，这次不缩回，但会闭上眼睛。
</behavioral_cue>

<pacing>
这个过程要慢。不要急着让她开门或离开。
让读者感受到她内心的拉扯。
</pacing>

<constraint>
不要让她 verbalize 她的恐惧。只通过肢体语言表现。
不要在这个beat里解决这个张力。让它积累。
</constraint>
```

**设计原则**：
- 可执行，不需要解读
- 内在一致，没有矛盾
- 300 Token以内
- 每轮变化

---

#### 模块4：对话历史（Recent Turns）

**职责**：提供叙事连贯性

**处理策略**：

| 时间窗口 | 处理方式 | Token预算 |
|----------|----------|-----------|
| 最近5轮 | 保留完整内容（不截断） | 12000-16000 Token |
| 6轮及更早 | 情绪摘要（每轮一句话） | 500-1000 Token |

**格式**：
```
=== RECENT HISTORY (full) ===

Turn 49 (latest):
Player: [完整内容]
Writer: [完整1600字]

Turn 48:
Player: [完整内容]
Writer: [完整1600字]

Turn 47:
Player: [完整内容]
Writer: [完整1600字]

Turn 46:
Player: [完整内容]
Writer: [完整1600字]

Turn 45:
Player: [完整内容]
Writer: [完整1600字]

=== EARLIER HISTORY (emotional summary) ===

Turn 40-44: 她从期待到失望，最后决定放弃等待。
Turn 35-39: 他开始疏远，她试图挽回但被拒绝。
Turn 30-34: 他们曾经亲密，但一次误会改变了一切。
```

**Opening处理**：
- Opening作为对话历史的第一条
- 自然衰减，不特殊对待
- 第6轮时被挤出历史窗口

**历史更新与缓存**：
- 历史区域在Prompt的末尾
- 历史的变化不影响System Prompt + 骨架的缓存
- 当第6回合出现时，第1回合变成摘要，这个变化发生在Prompt的末尾

---

#### 模块5：变量快照（Variable Snapshot）

**职责**：提供当前状态的精确信息

**内容**：
- 当前位置
- 生命值/状态
- 关系标志
- 关键物品
- 最近触发的事件

**格式**：
```
=== CURRENT STATE (volatile) ===
Location: Dragon's Nest (changed from Tavern at Turn 48)
Player HP: Critical (5/100) (was 80/100 at Turn 45)
Relationship with Kael: Hatred (flag_trust=-5, was +3 at Turn 30)
Key Item: Broken Sword (acquired at Turn 47)
Last Event: Dragon's roar echoed through the cave (Turn 49)
```

**设计原则**：
- 只输出本轮变化的变量（增量更新）
- 标注变化的时间点（"was X at Turn Y"）
- 100 Token以内
- 每轮变化

**缓存策略**：不缓存，但因为体积小，破坏的缓存长度只有100 Token

---

#### 模块6：玩家输入（Player Input）

**职责**：提供玩家的原始意图

**处理策略**：
- 完整内容，不截断
- 保留动作/对话/内心的结构标记

**格式**：
```
=== PLAYER INPUT ===

[动作] 她缓缓放下手中的酒杯，指尖微微颤抖
[对话] "没什么，只是想起一些事。"
[内心] 其实她想说的是：我恨你，但我更恨自己离不开你。
[动作] 她转身走向窗边，背对着他。
```

**结构标记的价值**：
- Writer可以区分"她让别人看到的"（放下酒杯、说"没什么"）
- 和"她藏在心里的"（恨你、离不开你）
- RP的核心张力就是**表面行为和内心真实之间的裂隙**

---

### 2.4 子Agent整合流程重构

#### 旧流程（信息汇聚）

```
子Agent → 原始建议列表 → SuggestionMerger排序 → 截断8条×200字 → 塞给Writer
```

Writer看到：
```
Sub-agent guidance:
1. 逻辑代理：此处应该开门
2. 情感代理：此处应该犹豫
3. 节奏代理：此处应该加快
```

**问题**：Writer陷入"讨好型人格"——既要...又要...还要...

#### 新流程（决策整合）

```
子Agent → SuggestionMerger检测矛盾 → Director做裁决 → 生成乐谱 → Writer
```

**SuggestionMerger的新职责**：
```python
class SuggestionMerger:
    def merge(self, suggestions):
        # 旧：按优先级排序
        # suggestions.sort(by=priority)
        # return suggestions[:8]

        # 新：检测矛盾，交给Director裁决
        conflicts = self.detect_conflicts(suggestions)
        clusters = self.cluster_by_theme(suggestions)
        return ConflictReport(conflicts, clusters)
```

**Director的新职责**：
```python
class Director:
    def integrate(self, conflict_report, context):
        # 识别核心矛盾
        core_conflict = self.identify_core_conflict(conflict_report)

        # 做裁决（不是投票，是决策）
        resolution = self.resolve(core_conflict, context)

        # 生成乐谱
        score = self.compose_score(resolution, context)

        return score
```

---

### 2.5 修订循环重构

#### 旧修订（表面检查）

```python
def _check_output(self, text):
    issues = []
    if len(text) < 1000:
        issues.append("WORD_COUNT_CRITICAL")
    if len(text) > 1600:
        issues.append("WORD_COUNT_HIGH")
    if text.startswith("#"):
        issues.append("FORMAT_ERROR")
    return issues
```

#### 新修订（语义检查）

```python
def _check_output(self, text, score, previous_turn):
    issues = []

    # 1. 长度检查（保留，但不是唯一标准）
    if len(text) < 1000:
        issues.append(("LENGTH_LOW", len(text)))
    if len(text) > 1600:
        issues.append(("LENGTH_HIGH", len(text)))

    # 2. 格式检查（保留）
    if text.startswith("#"):
        issues.append(("FORMAT_ERROR", "starts with markdown"))

    # 3. 角色一致性检查（新增）
    if self.detect_ooc(text, score):
        issues.append(("OOC_DETECTED", "character behavior contradicts inner_state"))

    # 4. 情节连贯性检查（新增）
    if self.detect_continuity_break(text, previous_turn):
        issues.append(("CONTINUITY_BREAK", "contradicts established facts"))

    # 5. 乐谱遵守检查（新增）
    if self.violates_score_constraints(text, score):
        issues.append(("SCORE_VIOLATION", "ignores Director's constraints"))

    return issues
```

**OOC检测逻辑**：
```python
def detect_ooc(self, text, score):
    # 乐谱说"她应该犹豫"
    # 但输出里"她毫不犹豫地推开门"
    # → OOC
    expected_emotion = extract_emotion(score.inner_state)
    actual_behavior = extract_behavior(text)
    return not compatible(expected_emotion, actual_behavior)
```

**情节连贯性检测**：
```python
def detect_continuity_break(self, text, previous_turn):
    # 上一轮说"他受伤了，左臂流血"
    # 这一轮说"他用左臂举起盾牌"
    # → 连贯性断裂
    facts_from_previous = extract_facts(previous_turn)
    facts_in_current = extract_facts(text)
    return has_contradiction(facts_from_previous, facts_in_current)
```

---

## 三、缓存策略

### 3.1 旧方案的问题

**旧方案**：
```
Stable Block = Worldbook全文 + Opening全文
```

**问题**：
- Worldbook更新导致整个前缀失效
- Opening在第50轮时仍然占据缓存窗口，但信息增益为零
- 缓存覆盖率不稳定

### 3.2 新方案

**新方案**：
```
可缓存 = System Prompt + 骨架（35000字Worldbook）
不可缓存 = 乐谱 + 历史 + 变量 + 玩家输入
```

**缓存覆盖率**：
- 可缓存部分：50000-70000 Token
- 不可缓存部分：13000-18000 Token
- 覆盖率：75%-85%，且**稳定**

**关键优势**：
- 骨架不变，100%命中缓存
- 变量快照只占100 Token，破坏的缓存长度极小
- 历史区域在Prompt末尾，不影响缓存

---

## 四、上下文窗口利用

### 4.1 窗口规格

- **1M上下文**：存储容量（100万Token）
- **128k注意力窗口**：模型对这部分有强注意力（128000 Token）

### 4.2 Token分配

| 模块 | Token数量 | 占注意力窗口比例 |
|------|-----------|------------------|
| 骨架 | 50000-70000 | 40%-55% |
| 乐谱 | 300 | <1% |
| 5轮完整历史 | 12000-16000 | 9%-12% |
| 旧历史摘要 | 500-1000 | <1% |
| 变量快照 | 100 | <1% |
| 玩家输入 | 750-1000 | <1% |
| **总计** | **63650-88400** | **50%-69%** |

**结论**：剩余空间足够容纳所有内容，且模型对所有内容都有强注意力。

---

## 五、实现优先级

### Phase 1：骨架/变量分离（解决缓存问题）

**任务**：
- 实现PromptAssembler
- 分离骨架和变量快照
- Opening并入对话历史

**验收标准**：
- 骨架100%可缓存
- 变量快照只占100 Token
- Opening自然衰减

---

### Phase 2：乐谱机制（解决子Agent噪音问题）

**任务**：
- 重构SuggestionMerger为矛盾检测器
- 重构Director为决策整合者
- 实现乐谱生成

**验收标准**：
- Writer看到的是可执行的乐谱，不是矛盾的建议列表
- 乐谱内在一致，没有矛盾
- 乐谱格式符合规范

---

### Phase 3：语义修订（解决质量问题）

**任务**：
- 实现OOC检测
- 实现连贯性检测
- 实现乐谱遵守检查

**验收标准**：
- 能检测角色崩坏
- 能检测情节矛盾
- 能检测乐谱违反

---

### Phase 4：情绪弧光窗口（解决记忆问题）

**任务**：
- 实现情绪摘要器
- 实现分层历史窗口
- 实现自然衰减机制

**验收标准**：
- 最近5轮完整保留
- 更早轮次变成情绪摘要
- Opening自然衰减

---

## 六、预期效果

| 问题 | 旧方案 | 新方案 |
|------|--------|--------|
| 缓存失效 | Worldbook更新导致全废 | 骨架不变，100%可缓存 |
| 子Agent噪音 | 矛盾建议直接塞给Writer | Director整合成一致的乐谱 |
| 角色崩坏 | 无检测机制 | OOC检测 + 乐谱遵守检查 |
| 情节断裂 | 硬截断丢失关键信息 | 完整5轮历史 + 情绪摘要 |
| 上下文幽灵 | Opening固定在缓存里 | Opening自然衰减 |
| 修订无效 | 只检查长度 | 语义级检查 |
| 注意力稀释 | 平铺直叙的分层 | 骨架/变量分离，乐谱整合 |

---

## 七、核心转变总结

### 从"技术驱动"到"叙事驱动"

旧方案的问题：为了缓存优化、为了工程分层、为了可量化指标，牺牲了叙事质量。

新方案的原则：**叙事质量是第一优先级，技术方案服务于叙事需求**。

### 从"信息汇聚"到"决策整合"

旧方案：子Agent → 原始建议列表 → Writer
新方案：子Agent → Director整合 → 可执行乐谱 → Writer

### 从"事实驱动"到"情感驱动"

旧方案：堆砌大量"硬事实"（Worldbook、历史、记忆）
新方案：追踪"软状态"（情绪、潜台词、关系张力）

RP的核心不是"发生了什么"，而是"角色对此有什么感受"。
