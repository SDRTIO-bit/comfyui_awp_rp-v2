"""End-to-end demo for novel mode."""

import pytest
from awp_rp_runtime_v2.runtime.novel_engine import NovelEngine
from awp_rp_runtime_v2.contracts.novel_project import NovelProject


@pytest.fixture
def reg(tmp_path):
    from awp_rp_runtime_v2.storage.sqlite.database import Database
    from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
    db = Database(str(tmp_path / "novel_test.db"))
    db.initialize()
    return SessionRuntimeStoreRegistry(db)


@pytest.fixture
def engine(reg):
    return NovelEngine(reg)


def test_novel_e2e_demo(reg, engine, capsys):
    """Full novel mode end-to-end demo."""

    # 1. 创建项目
    print('=== 1. 创建项目 ===')
    project = NovelProject(
        project_id='novel-demo',
        title='斗破苍穹',
        genre='玄幻',
        core_emotion='热血逆袭',
        one_sentence_pitch='废柴少年逆袭成帝',
    )
    reg.novel_project_store.create(project)
    loaded = reg.novel_project_store.load('novel-demo')
    print(f'项目: {loaded.title} | 类型: {loaded.genre} | 状态: {loaded.status}')

    # 2. 规划章节
    print('\n=== 2. 规划章节 ===')
    plan = engine.plan_chapter(
        project_id='novel-demo',
        chapter_index=1,
        task_description='第一章：废柴觉醒',
    )
    print(f'章节ID: {plan.chapter_id}')
    print(f'标题: {plan.title}')
    print(f'目标字数: {plan.target_chars}')

    # 3. 写章节
    print('\n=== 3. 写章节 ===')
    draft = engine.write_chapter(project_id='novel-demo', chapter_index=1)
    print(f'草稿ID: {draft.draft_id}')
    print(f'字数: {draft.char_count}')
    print(f'状态: {draft.status}')
    print(f'正文前100字: {draft.text[:100]}')

    # 4. 查看账本
    print('\n=== 4. 查看账本 ===')
    items = reg.novel_ledger_store.list_by_project('novel-demo')
    print(f'账本条目数: {len(items)}')

    # 5. 批量生成
    print('\n=== 5. 批量生成 (第2-4章) ===')
    drafts = engine.batch_write(
        project_id='novel-demo',
        chapter_start=2,
        chapter_end=4,
    )
    print(f'生成章节数: {len(drafts)}')
    for d in drafts:
        print(f'  - {d.draft_id}: {d.char_count}字, 状态={d.status}')

    # 6. 查看所有章节计划
    print('\n=== 6. 章节目录 ===')
    plans = reg.novel_chapter_plan_store.list_by_project('novel-demo')
    for p in plans:
        print(f'  第{p.chapter_index}章: {p.title}')

    # 7. 查看批量进度
    print('\n=== 7. 批量进度 ===')
    batch_list = reg.novel_batch_progress_store.list_by_project('novel-demo')
    for b in batch_list:
        print(f'  批次 {b.batch_id}: 章{b.chapter_start}-{b.chapter_end}, 状态={b.status}')

    # 8. 修订章节
    print('\n=== 8. 修订第1章 ===')
    revised = engine.revise_chapter(
        project_id='novel-demo',
        chapter_index=1,
        feedback='结尾需要更强的钩子',
    )
    print(f'修订版ID: {revised.draft_id}')
    print(f'修订版字数: {revised.char_count}')
    print(f'修订版状态: {revised.status}')

    # 9. 查看第1章所有版本
    print('\n=== 9. 第1章版本历史 ===')
    drafts_ch1 = reg.novel_chapter_draft_store.list_by_chapter(plan.chapter_id)
    for d in drafts_ch1:
        print(f'  版本{d.revision}: {d.draft_id}, {d.char_count}字, 状态={d.status}')

    print('\n=== 试运行完成 ===')

    # Assertions
    assert loaded.title == '斗破苍穹'
    assert plan.chapter_index == 1
    assert draft.char_count > 0
    assert len(drafts) == 3
    assert len(plans) == 4  # ch1-4
    assert revised.revision == 2
    assert len(drafts_ch1) == 2  # v1 + v2
