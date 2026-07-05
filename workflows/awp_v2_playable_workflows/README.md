# AWP RP Runtime V2 — 正式可玩工作流（拆分版）

这四张图刻意拆开：当前仓库的持久化节点通过 SQLite 和 `session_id` 协作，但 `PersistentBootstrap`、`PersistentFirstTurn`、`PersistentContinuationTurn`、`ContinueTurnP1` 之间没有可用于 ComfyUI 图内串行调度的类型端口。

因此，不要把它们并列塞进同一张生产图。那会让 ComfyUI 把它们视为独立根节点，不能保证 Bootstrap → First → Continue 的执行次序。

## 使用顺序

1. `01_bootstrap_session.api.json`
   - 新建会话。
   - 填 `source_path`、`session_id`、`greeting_id`。
   - 每创建一个新会话使用新的 `session_id`、`request_id`、`run_id`。

2. `02_first_turn.api.json`
   - 只在上一步成功后运行一次。
   - `session_id` 必须与 Bootstrap 完全一致。
   - 填入玩家第一句话，使用新 `turn_id`、`request_id`、`run_id`。

3. `03_send_turn.api.json`
   - 后续每次玩家正常回复使用。
   - 每次都更新 `player_input`、`turn_id`、`request_id`、`run_id`。
   - 重用同一 `turn_id` 是幂等 replay，不是新回合。

4. `04_continue_world.api.json`
   - 玩家点击 Continue、允许世界自主推进时使用。
   - 不填玩家输入。
   - 每次都更新 `turn_id`、`request_id`、`run_id`。

## 模型配置

默认：
- Director: `deepseek-v4-flash-director`
- Writer: `deepseek-v4-pro-writer`

离线 / Fake 验证可改为：
- `fake-director`
- `fake-writer`

## 重要说明

这些文件直接复用当前仓库已经封装的持久化主链：
`PersistentBootstrap / PersistentFirstTurn / PersistentContinuationTurn / ContinueTurnP1`。

没有手工重接旧版 `full_architecture_turn` 中的 Director、D1-D6、Quality、CardState Commit、Memory Commit，因此不会产生旧显式架构图里的类型错配和双提交风险。

将来若新增一个真正的 `AWPV2PlayableSessionAction` 路由节点，才适合把四张图收敛成一张 Start / Send / Continue 单入口图。
# AWP RP Runtime V2 playable workflows

## Current workflow roles

- `01_bootstrap_session.api.json`: create/bootstrap a persistent session.
- `02_first_turn.api.json`: run the first player turn after bootstrap.
- `03_send_turn.api.json`: production path for normal player turns. This uses `AWPV2PersistentContinuationTurn`, which runs the canonical persistent engine internally.
- `04_continue_world.api.json`: production path for world-advance/continue actions.
- `full_architecture_turn.graph.json`: observable equivalent of the normal turn path. It executes the same persistent continuation node once, then uses `AWPV2PersistentTurnObserver` and `AWPV2TraceDisplay` nodes to expose Director, sub-agent, Writer, quality, state, memory, and full diagnostic views. The observation nodes are read-only and do not repeat state, turn, or memory commits.

Use `03_send_turn.api.json` for normal frontend/hybrid execution. Use `full_architecture_turn.graph.json` when you want to inspect the pipeline without changing the execution semantics.
