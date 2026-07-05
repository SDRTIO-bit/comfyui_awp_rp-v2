"""Demo: Write first 3 chapters of a novel (~6000 words total)."""

import pytest
from awp_rp_runtime_v2.runtime.novel_engine import NovelEngine
from awp_rp_runtime_v2.contracts.novel_project import NovelProject
from awp_rp_runtime_v2.contracts.novel_character import NovelCharacter, CharacterRelationship


@pytest.fixture
def reg(tmp_path):
    from awp_rp_runtime_v2.storage.sqlite.database import Database
    from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
    db = Database(str(tmp_path / "novel_demo.db"))
    db.initialize()
    return SessionRuntimeStoreRegistry(db)


@pytest.fixture
def engine(reg):
    return NovelEngine(reg)


def test_write_3_chapters(reg, engine, capsys):
    """Write first 3 chapters of a novel."""

    # === 1. 创建项目 ===
    print('\n' + '='*60)
    print('创建小说项目')
    print('='*60)

    project = NovelProject(
        project_id='demo-novel',
        title='深渊之上',
        genre='都市悬疑',
        core_emotion='压抑→觉醒→爆发',
        one_sentence_pitch='一个被冤入狱十年的法医，出狱后用专业知识追查真凶，却发现真凶一直就在身边。',
        target_reader='25-40岁，喜欢悬疑推理、反转剧情',
    )
    reg.novel_project_store.create(project)

    # === 2. 创建角色 ===
    print('\n创建角色...')

    protagonist = NovelCharacter(
        character_id='char-chen',
        project_id='demo-novel',
        name='陈默',
        aliases=('陈法医', '老陈'),
        role='protagonist',
        personality='沉默寡言，观察力极强，内心有执念但外表平静',
        voice_style='短句，很少用形容词，偶尔冷幽默',
        pov_eligible=True,
        core_motivation='找到当年陷害自己的真凶，为死去的搭档翻案',
        weakness='对真相的执念可能伤害身边的人',
        relationships=(
            CharacterRelationship(
                target_character_id='char-lin',
                target_name='林晚',
                relation_type='前同事/暧昧',
                description='当年的搭档，十年来从未放弃为他翻案',
                tension='medium',
            ),
            CharacterRelationship(
                target_character_id='char-zhou',
                target_name='周远',
                relation_type='仇人',
                description='当年的上司，陈默认为是他陷害了自己',
                tension='high',
            ),
        ),
        current_state={
            'identity': '刚出狱的前法医',
            'ability': '法医学知识、反侦察意识',
            'location': '城中村出租屋',
            'emotion': '压抑但平静',
        },
        arc_phase='setup',
        first_appearance=1,
    )

    antagonist = NovelCharacter(
        character_id='char-zhou',
        project_id='demo-novel',
        name='周远',
        aliases=('周局',),
        role='antagonist',
        personality='表面温和儒雅，实则心狠手辣，善于伪装',
        voice_style='官腔，喜欢用反问句，从不直接回答问题',
        pov_eligible=False,
        core_motivation='维护自己的地位和秘密',
        weakness='过于自信，低估陈默的能力',
        relationships=(
            CharacterRelationship(
                target_character_id='char-chen',
                target_name='陈默',
                relation_type='前下属/仇人',
                description='十年前亲手把陈默送进监狱',
                tension='high',
            ),
        ),
        current_state={
            'identity': '市公安局副局长',
            'ability': '权力、人脉、信息控制',
            'location': '市公安局',
            'emotion': '表面平静，暗中紧张',
        },
        arc_phase='setup',
        first_appearance=1,
    )

    support = NovelCharacter(
        character_id='char-lin',
        project_id='demo-novel',
        name='林晚',
        aliases=('小林', '林姐'),
        role='supporting',
        personality='外刚内柔，正义感强，有韧性',
        voice_style='干脆利落，偶尔露出柔软',
        pov_eligible=False,
        core_motivation='为陈默翻案，找出当年的真相',
        weakness='感情用事，有时不够冷静',
        relationships=(
            CharacterRelationship(
                target_character_id='char-chen',
                target_name='陈默',
                relation_type='前搭档/暧昧',
                description='十年来一直暗中调查当年的案子',
                tension='medium',
            ),
        ),
        current_state={
            'identity': '刑警队副队长',
            'ability': '刑侦经验、人脉',
            'location': '市公安局刑警队',
            'emotion': '期待又紧张',
        },
        arc_phase='setup',
        first_appearance=1,
    )

    reg.novel_character_store.save(protagonist)
    reg.novel_character_store.save(antagonist)
    reg.novel_character_store.save(support)
    print(f'  角色: {protagonist.name}({protagonist.role}), {antagonist.name}({antagonist.role}), {support.name}({support.role})')

    # === 3. 批量规划 + 写作 ===
    print('\n' + '='*60)
    print('开始批量生成 (第1-3章)')
    print('='*60)

    drafts = engine.batch_write(
        project_id='demo-novel',
        chapter_start=1,
        chapter_end=3,
        on_chapter_complete=lambda idx, d: print(f'\n  ✅ 第{idx}章完成: {d.char_count}字, 状态={d.status}'),
    )

    # === 4. 输出结果 ===
    print('\n' + '='*60)
    print('生成结果')
    print('='*60)

    total_chars = 0
    for draft in drafts:
        plan = reg.novel_chapter_plan_store.load(draft.chapter_id)
        print(f'\n--- 第{plan.chapter_index}章: {plan.title} ---')
        print(f'字数: {draft.char_count} | 状态: {draft.status}')
        print(f'目标情绪: {plan.target_emotion}')
        print(f'章节定位: {plan.chapter_position}')
        print(f'\n正文:')
        print(draft.text)
        total_chars += draft.char_count

    print(f'\n{"="*60}')
    print(f'总计: {len(drafts)} 章, {total_chars} 字')
    print(f'{"="*60}')

    # Assertions
    assert len(drafts) == 3
    assert total_chars > 0
