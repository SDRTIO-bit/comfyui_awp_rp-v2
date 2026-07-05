# P-CardImport V1 Scope Decision

**Date**: 2026-06-27
**Branch**: feat/card-import-normalization-v1
**Status**: Active

---

## 1. 本阶段实现什么

安全、可追溯、版本化的角色卡导入基础设施：

- SillyTavern V3 JSON 解析
- SillyTavern V3 PNG metadata 解析（tEXt / zTXt / iTXt chunks）
- 角色卡格式验证
- 安全扫描（JavaScript / eval / EJS / fetch / iframe / 变量脚本）
- 规范化为 CardDefinition
- 世界书 logical entry + derived chunk 切片
- Greeting 提取与安全投影
- StructureHints 提取（阶段、事件、变量、关系）
- QuarantineRecord 隔离
- 导入审核报告（CardImportReport）
- 显式批准机制（CardImportApproval → staged → ready）
- CardDefinition 版本化存储
- ComfyUI 节点注册
- 官方 workflow JSON

## 2. 本阶段明确不实现什么

- CardSessionBootstrap
- Greeting 选择 UI
- 角色卡编辑 UI
- 真实 RP 开局
- CardState 自动初始化
- 变量脚本执行
- EJS 执行
- Regex Script 执行
- 自动世界事件
- 世界书真实检索接入
- 向量化 / Embedding
- 记忆导入
- 世界书直接写入 RAG
- 角色卡自动生成 Agent
- 前端重做
- README / License / .gitignore 改动

## 3. 外部角色卡是"不可信输入"

外部角色卡来源不可控，可能包含：

- JavaScript / eval / Function 构造器
- EJS 模板
- `<script>` / `<iframe>` 标签
- `fetch` / `import()` URL 请求
- `{{setvar:}}` / `{{getvar:}}` / `{{addvar:}}` 变量写入
- Regex Script
- 变量执行语法
- 结构提示（阶段 / 事件 / 关系）≠ 自动状态切换

所有外部内容必须经过：

1. 解析 → 2. 验证 → 3. 安全扫描 → 4. 规范化 → 5. 审核 → 6. 显式批准

绝不跳过任何步骤。

## 4. CardDefinition 与 CardState 的职责边界

| 概念 | 定义 | 生命周期 |
|---|---|---|
| CardDefinition | 静态、版本化、可复用的角色卡资源包 | 导入后持久存在，不随 session 变化 |
| CardState | 某个 session 中会变化的世界与剧情真相 | 绑定 card_id + session_id，随回合变化 |

关键规则：

- 导入卡时不得写 CardState
- 导入卡时不得创建 ActiveMemory / RagMemory
- 导入卡时不得创建 TurnRecord
- 导入卡时不得执行变量脚本
- 导入卡时不得执行 EJS / JavaScript / Regex Script
- 导入卡时不得请求网络 URL
- 导入卡时不得自动启动 Agent
- 导入卡时不得自动创建 session

## 5. Worldbook、Memory、Greeting、变量、脚本的拆分边界

### Worldbook

- 外部世界书 entry → CardWorldbookEntry（logical entry）
- 长条目 → CardWorldbookChunk（derived chunk，可追溯）
- 不得把世界书自动写入 ActiveMemory 或 RagMemory
- disabled entry 保存但默认不可激活
- constant entry 不等于无预算全量注入

### Memory

- 导入阶段不涉及 ActiveMemory / RagMemory
- 记忆由 D6 Memory Curator 在回合接受后管理

### Greeting

- `first_mes` → 默认 Greeting
- `alternate_greetings` → 备用 Greeting 列表
- 包含脚本 / 变量 / EJS 的 Greeting → QuarantineRecord + 安全投影
- 不执行、不把污染内容直接写入 session

### 变量

- 变量模式只产生 variableHints
- 不写 CardState
- 不执行变量脚本

### 脚本

- JavaScript / eval / Function / fetch / iframe → QuarantineRecord
- 不执行、不忽略后静默注入 Prompt

## 6. 导入管线

```
CardSourceLoad
→ CardPayloadParse
→ CardFormatValidate
→ CardSecurityScan
→ CardNormalize
→ CardWorldbookChunkBuild
→ CardImportReview
→ CardImportApproval
→ CardDefinitionCommit
→ CardImportResult
```

导入阶段不接入：

- DynamicSubAgentPool
- SuggestionMerge
- Writer
- Quality Gate
- CardStateCommit
- TurnRecordCommit
- Memory Curator
