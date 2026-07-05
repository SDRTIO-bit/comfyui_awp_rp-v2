# 参考文档

## 原始架构记录

本目录包含项目的原始架构记录文档：

- [RP ComfyUI 双主Agent、记忆与动态子Agent 架构记录 v0.1](RP_ComfyUI_双主Agent_记忆与动态子Agent_架构记录_v0.1.md)

  **版本：** v0.1（讨论归档 / 后续开发指引）
  **日期：** 2026-06-27
  **定位：** 记录当前已经形成的系统级共识，避免"让世界活起来"的关键想法在后续开发中丢失。

## 架构文档体系

当前公开仓库的可审计架构依据：

| 文档 | 位置 | 内容 |
|------|------|------|
| 系统总览 | [docs/architecture/overview-v1.md](../architecture/overview-v1.md) | 项目目标、双主 Agent、确定性状态、三层记忆 |
| 系统架构图 | [docs/architecture/system-overview.md](../architecture/system-overview.md) | 七层架构、数据流 |
| 回合生命周期 v1 | [docs/architecture/turn-lifecycle-v1.md](../architecture/turn-lifecycle-v1.md) | 完整主链、Wave A/B、D6 位置、retry/idempotency |
| 回合生命周期 | [docs/architecture/turn-lifecycle.md](../architecture/turn-lifecycle.md) | 分阶段详细流程 |
| Agent 权限边界 | [docs/architecture/agent-boundaries-v1.md](../architecture/agent-boundaries-v1.md) | D1～D6 职责、输入、输出、工具、降级 |
| 记忆治理 | [docs/architecture/memory-governance-v1.md](../architecture/memory-governance-v1.md) | 三层记忆、accepted-only、D6 触发、幂等 |
| 冲突治理 | [docs/architecture/conflict-governance-v1.md](../architecture/conflict-governance-v1.md) | 证据优先级、玩家代理权、事实泄漏防护 |
| 状态与存储 | [docs/architecture/state-and-memory.md](../architecture/state-and-memory.md) | SQLite schema、事务边界 |
| 重试与幂等 | [docs/architecture/retry-and-replay.md](../architecture/retry-and-replay.md) | 重试/回放/幂等策略 |
| 迁移策略 | [docs/architecture/migration-policy.md](../architecture/migration-policy.md) | V1→V2 clean-room 策略 |

## 当前活跃计划

| 文档 | 内容 |
|------|------|
| [前端节点/工作流集成计划](../superpowers/plans/2026-06-29-frontend-node-workflow-integration.md) | 15-Task 双轨执行引擎计划 |
| [前端集成设计 spec](../superpowers/specs/2026-06-29-frontend-node-workflow-integration-design.md) | 设计文档 |
| [管线流式观察窗 spec](../superpowers/specs/2026-06-30-pipeline-stream-drawer-design.md) | PipelineStreamDrawer 设计 |
| [二号主 Agent 改造计划](../二号主agent改造计划.md) | Writer agent 改革 |
| [二号主 Agent 整改思路](../二号主agent整改思路.md) | 问题分析与改革思路 |

## 测试与安全

| 文档 | 内容 |
|------|------|
| [AI 故障分类](../testing/ai-failure-triage-v1.md) | AI triage 准则 |
| [自治测试架构](../testing/autonomous-workflow-testing-v1.md) | ScenarioFixtureFactory、确定性断言 |
| [安全策略](../security.md) | 密钥管理、测试隔离 |
| [贡献指南](../contributing.md) | 分支/测试/schema 约定 |

## 归档文档

已完成的里程碑交接文档、交付报告和过时文档已移至 [docs/archive/](../archive/README.md)。

| 类别 | 内容 |
|------|------|
| 过时文档 | alpha-status-v0.1、contracts-v1、delegation-policy（内容已脱节） |
| 交付报告 | M1、C1 交付报告 |
| Handoffs | D1～D6、P1、P2、P-Observability、P-CardSession、P-FirstTurn、P-RealProvider、P-Canonical、P-Persistent 等全部阶段交接 |
| Decisions | card-import-v1-scope ADR |
