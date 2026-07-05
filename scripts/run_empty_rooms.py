"""实战脚本：《空房间》——用 OpenCode Zen + qwen3.7-max 写3章。

题材：都市怪谈 + 心理悬疑
核心情绪：压抑 → 恐惧 → 接纳
作者构思：失眠三年的插画师搬进一栋废弃医院改建的廉租房，
        房东是三十年前就该死的护士，走廊里那些住户的脸，
        和她三年里"接走"的病人长得一模一样。
"""

import os
import sys
import time
from pathlib import Path

# 切到 OpenCode provider
os.environ["NOVEL_LLM_PROVIDER"] = "opencode"
# 已设 OPENCODE_API_KEY；可选：覆盖 writer 模型为 glm-5.2 对比
# os.environ["NOVEL_LLM_MODEL_WRITER"] = "glm-5.2"

sys.path.insert(0, r"F:\12\语英")

from awp_rp_runtime_v2.storage.sqlite.database import Database
from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
from awp_rp_runtime_v2.runtime.novel_engine import NovelEngine
from awp_rp_runtime_v2.contracts.novel_project import NovelProject
from awp_rp_runtime_v2.contracts.novel_character import (
    NovelCharacter, CharacterRelationship,
)


def main() -> int:
    out_dir = Path("qingmei_out/empty_rooms")
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(out_dir / "empty_rooms.db")

    db = Database(db_path)
    db.initialize()
    reg = SessionRuntimeStoreRegistry(db)
    engine = NovelEngine(reg)

    # 1. 项目
    print("=" * 60)
    print("【1/4】创建项目：空房间")
    print("=" * 60)
    project = NovelProject(
        project_id="empty-rooms",
        title="空房间",
        genre="都市怪谈",
        target_platform="番茄短篇",
        target_reader="22-35岁，喜欢心理悬疑、都市怪谈、压抑反转",
        core_emotion="压抑 → 恐惧 → 接纳",
        one_sentence_pitch=(
            "一个失眠三年、每晚梦到同一栋废弃医院的女插画师，"
            "在现实里收到那栋医院原址的廉租房广告搬了进去，"
            "房东是三十年前就该死的护士，走廊里的住户们"
            "和她在急诊科三年里眼睁睁送走的病人长着同一张脸。"
        ),
        status="writing",
    )
    reg.novel_project_store.create(project)
    print("  title:", project.title, "| genre:", project.genre)
    print("  pitch:", project.one_sentence_pitch)

    # 2. 角色
    print()
    print("=" * 60)
    print("【2/4】创建角色")
    print("=" * 60)

    lin = NovelCharacter(
        character_id="char-lin",
        project_id="empty-rooms",
        name="林知夏",
        aliases=("知夏", "插画师"),
        role="protagonist",
        personality="失眠三年，靠咖啡因和画板过活。话不多，但心里台词密集。"
                    "在医院当过三年临终关怀义工，把病人一支支画下来再一个个送走。",
        voice_style="短句。自嘲优先。问到失眠只说「习惯了」，问到家人就换话题。",
        pov_eligible=True,
        core_motivation="搞清楚自己为什么每晚都梦到同一栋医院——然后活下去。",
        weakness="分不清梦境和现实。看到住户的脸会信错人。",
        relationships=(
            CharacterRelationship(
                target_character_id="char-yuan",
                target_name="袁护士",
                relation_type="房东／潜在威胁",
                description="搬进去见到的第一个活人，自称退休护士，手凉得像停尸房抽屉。",
                tension="high",
            ),
            CharacterRelationship(
                target_character_id="char-404",
                target_name="404号住户",
                relation_type="梦的引子",
                description="戴白帽子的小孩。每次出现都不说话，只是把一摞画纸推到林知夏脚边。",
                tension="medium",
            ),
        ),
        current_state={
            "identity": "失眠三年的自由插画师",
            "ability": "画，看，记住每一张脸",
            "location": "刚搬进医院改建的廉租房403室",
            "emotion": "压抑，好奇，靠着失眠维持的警觉",
        },
        arc_phase="setup",
        first_appearance=1,
    )

    yuan = NovelCharacter(
        character_id="char-yuan",
        project_id="empty-rooms",
        name="袁护士",
        aliases=("袁姐", "房东"),
        role="antagonist",
        personality="五十岁，皱纹柔和，会一边和你说笑一边把病房灯关到只剩一盏。"
                    "称谓切换极快——刚叫你「知夏」转头就成「那个孩子」。",
        voice_style="长句。喜欢用「我跟你讲」开头，再不给对方插话的机会。",
        pov_eligible=False,
        core_motivation="让每一个搬进来的住户都「认领」一段本不属于他们的记忆。",
        weakness="只在林知夏失眠最严重的凌晨三点出现。她没法在清醒的人面前起作用。",
        relationships=(
            CharacterRelationship(
                target_character_id="char-lin",
                target_name="林知夏",
                relation_type="新房客／目标",
                description="三年里送走过同一批病人的最后一个人。",
                tension="high",
            ),
        ),
        current_state={
            "identity": "廉租房房东，自称退休护士",
            "ability": "用记忆制造归属感",
            "location": "403室对面的值班室",
            "emotion": "等待了三十年的耐心",
        },
        arc_phase="setup",
        first_appearance=1,
    )

    kid = NovelCharacter(
        character_id="char-404",
        project_id="empty-rooms",
        name="404号住户",
        aliases=("戴白帽子的小孩",),
        role="supporting",
        personality="七八岁。沉默，动作慢，递画纸时会等对方先接住才松手。",
        voice_style="不说话。",
        pov_eligible=False,
        core_motivation="给林知夏看一幅她画过但忘了的画。",
        weakness="只能存在于林知夏没合眼的时段里。",
        relationships=(
            CharacterRelationship(
                target_character_id="char-lin",
                target_name="林知夏",
                relation_type="梦的引子",
                description="反复出现在林知夏梦里的男孩。",
                tension="low",
            ),
        ),
        current_state={
            "identity": "404号住户，其实是记忆残片",
            "ability": "递画",
            "location": "走廊尽头",
            "emotion": "等了很久",
        },
        arc_phase="setup",
        first_appearance=2,
    )

    reg.novel_character_store.save(lin)
    reg.novel_character_store.save(yuan)
    reg.novel_character_store.save(kid)
    print("  主角:", lin.name, "|", lin.personality[:40])
    print("  反派:", yuan.name, "|", yuan.personality[:40])
    print("  支线:", kid.name, "|", kid.personality[:40])

    # 3. 批量规划 + 写作
    print()
    print("=" * 60)
    print("【3/4】开始批量生成 (第1-3章)")
    print("=" * 60)

    t0 = time.time()
    last_save = {"chapter": -1, "count": 0}

    def on_done(idx: int, draft) -> None:
        last_save["chapter"] = idx
        last_save["count"] = draft.char_count
        print(f"\n  📝 第{idx}章完成: {draft.char_count}字, 状态={draft.status}")
        # 即时落盘,防止超时丢稿
        try:
            plan = reg.novel_chapter_plan_store.load(draft.chapter_id)
        except Exception:
            plan = None
        out_file = out_dir / f"chapter_{idx:02d}.txt"
        with out_file.open("w", encoding="utf-8") as f:
            if plan is not None:
                f.write(f"第{plan.chapter_index}章：{plan.title}\n")
                f.write(f"目标情绪：{getattr(plan, 'target_emotion', '')}\n")
                f.write(f"章节定位：{getattr(plan, 'chapter_position', '')}\n")
                f.write("=" * 60 + "\n\n")
            f.write((draft.text or "").strip() + "\n")
        print(f"     已保存 -> {out_file}")

    drafts = engine.batch_write(
        project_id="empty-rooms",
        chapter_start=1,
        chapter_end=3,
        on_chapter_complete=on_done,
    )

    elapsed = time.time() - t0
    print()
    print(f"批量生成完成,用时 {elapsed:.1f}s,产章数: {len(drafts)}")

    # 4. 输出结果
    print()
    print("=" * 60)
    print("【4/4】生成结果")
    print("=" * 60)

    total_chars = 0
    for draft in drafts:
        try:
            plan = reg.novel_chapter_plan_store.load(draft.chapter_id)
            title = plan.title
            emo = getattr(plan, "target_emotion", "")
            pos = getattr(plan, "chapter_position", "")
        except Exception:
            title = f"第{draft.chapter_id}"
            emo = pos = "(无计划)"
        print(f"\n--- 第{draft.chapter_id}章: {title} ---")
        print(f"字数: {draft.char_count} | 状态: {draft.status}")
        print(f"目标情绪: {emo} | 章节定位: {pos}")
        print()
        text = (draft.text or "").strip()
        # 控制台预览前 800 字
        preview = text[:800] + ("..." if len(text) > 800 else "")
        print(preview)
        total_chars += draft.char_count

    # 汇总落盘
    summary_path = out_dir / "all_3_chapters.txt"
    with summary_path.open("w", encoding="utf-8") as f:
        f.write(f"# 《空房间》首批3章试写\n")
        f.write(f"# 总字数: {total_chars} | 用时 {elapsed:.1f}s\n\n")
        for draft in drafts:
            try:
                plan = reg.novel_chapter_plan_store.load(draft.chapter_id)
                title = plan.title
                emo = getattr(plan, "target_emotion", "")
            except Exception:
                title = f"第{draft.chapter_id}"
                emo = ""
            f.write("=" * 60 + "\n")
            f.write(f"第{draft.chapter_id}章：{title} | 目标情绪: {emo}\n")
            f.write("=" * 60 + "\n\n")
            f.write((draft.text or "").strip() + "\n\n\n")

    print()
    print("=" * 60)
    print(f"总计: {len(drafts)} 章, {total_chars} 字, 用时 {elapsed:.1f}s")
    print(f"汇总文件: {summary_path}")
    print("=" * 60)

    return 0 if drafts else 1


if __name__ == "__main__":
    raise SystemExit(main())