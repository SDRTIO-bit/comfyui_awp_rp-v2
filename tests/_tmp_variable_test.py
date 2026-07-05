"""验证 Writer 是否遵循变量更新原则。"""
import os
import time

def test_writer_follows_variable_rules():
    from awp_rp_runtime_v2.adapters.llm.deepseek_adapter import DeepSeekAdapter
    from awp_rp_runtime_v2.adapters.llm.real_writer_adapter import RealWriterV2Adapter
    from awp_rp_runtime_v2.adapters.llm.model_profile_registry import ModelProfileRegistry
    from awp_rp_runtime_v2.contracts.writer_input_bundle import WriterInputBundle

    assert os.environ.get("DEEPSEEK_API_KEY"), "需要 DEEPSEEK_API_KEY"
    profile = ModelProfileRegistry.resolve("deepseek-v4-pro-writer")
    ds = DeepSeekAdapter(model=profile.model, default_max_tokens=profile.default_max_tokens,
                         timeout_seconds=120, max_retries=1)
    adapter = RealWriterV2Adapter(ds, model=profile.model)

    # 世界书包含变量更新原则
    bundle = WriterInputBundle(
        player_input="那女子抬起头，竟是周语晴。她眼圈一红：你总算回来了。",
        final_turn_brief={
            "turn_goal": "Establish the emotional reunion",
            "scene_focus": "Zhou Yuqing's emotional state",
        },
        worldbook_context=[
            {
                "title": "信任度规则",
                "content_excerpt": "【变量更新原则】信任度初始 50，每次诚实+10，欺骗-20。当信任度<30 时，周语晴不会主动透露秘密。当信任度>=70 时，周语晴会主动分享心事。",
                "entry_kind": "constant",
                "activation_reason": "constant",
            },
            {
                "title": "周语晴",
                "content_excerpt": "周语晴，玩家青梅竹马，性格温婉但内心坚强。",
                "entry_kind": "constant",
                "activation_reason": "constant",
            },
        ],
        card_state_context={
            "scene_state": {"location": "庭院"},
            "variables": {"信任度": 60},  # 当前信任度=60
        },
    )
    t0 = time.time()
    text, receipt = adapter.generate(bundle, workflow_run_id="w", trace_id="tc", turn_id="t1", attempt_id="a1")
    elapsed = time.time() - t0
    print(f"[耗时] {elapsed:.1f}s")
    print(f"[receipt.success] {receipt.success}")
    print(f"[text length] {len(text)}")
    print(f"[text preview]\n{text[:800]}")

    # 检查变量遵循情况
    checks = []
    # 信任度=60，应该在 30-70 之间，周语晴应该有基本信任但不会主动分享心事
    if "秘密" not in text and "心事" not in text:
        checks.append("[OK] 未提及秘密或心事（信任度=60，<70）")
    else:
        checks.append("[FAIL] 提及了秘密或心事（信任度=60，<70）")

    # 检查是否反映了信任度
    if "信任" in text or "相信" in text or "怀疑" in text:
        checks.append("[OK] 反映了信任度状态")
    else:
        checks.append("[FAIL] 未反映信任度状态")

    print("\n[变量遵循检查]")
    for check in checks:
        print(f"  {check}")
