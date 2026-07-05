"""Tests for novel mode storage layer."""

import pytest
from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
from awp_rp_runtime_v2.contracts.novel_project import NovelProject
from awp_rp_runtime_v2.contracts.novel_volume import VolumePlan
from awp_rp_runtime_v2.contracts.novel_chapter import ChapterPlan, BeatDetail, ContentSummary
from awp_rp_runtime_v2.contracts.novel_draft import ChapterDraft
from awp_rp_runtime_v2.contracts.novel_ledger import LedgerItem
from awp_rp_runtime_v2.contracts.novel_character import NovelCharacter, CharacterRelationship
from awp_rp_runtime_v2.contracts.novel_batch import BatchProgress
from awp_rp_runtime_v2.contracts.novel_reference import ReferenceBook


@pytest.fixture
def reg(tmp_path):
    from awp_rp_runtime_v2.storage.sqlite.database import Database
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    return SessionRuntimeStoreRegistry(db)


class TestNovelProjectStore:
    def test_create_and_load(self, reg):
        p = NovelProject(project_id="p1", title="测试小说", genre="玄幻")
        reg.novel_project_store.create(p)
        loaded = reg.novel_project_store.load("p1")
        assert loaded.title == "测试小说"
        assert loaded.genre == "玄幻"

    def test_list_all(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1", title="A"))
        reg.novel_project_store.create(NovelProject(project_id="p2", title="B"))
        assert len(reg.novel_project_store.list_all()) == 2

    def test_update(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1", title="旧"))
        reg.novel_project_store.update(NovelProject(project_id="p1", title="新"))
        assert reg.novel_project_store.load("p1").title == "新"

    def test_delete(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_project_store.delete("p1")
        assert reg.novel_project_store.load("p1") is None

    def test_load_nonexistent(self, reg):
        assert reg.novel_project_store.load("nope") is None


class TestNovelVolumeStore:
    def test_save_and_load(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        v = VolumePlan(volume_id="v1", project_id="p1", index=1, title="第一卷")
        reg.novel_volume_store.save(v)
        loaded = reg.novel_volume_store.load("v1")
        assert loaded.title == "第一卷"

    def test_list_by_project(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_volume_store.save(VolumePlan(volume_id="v1", project_id="p1", index=1))
        reg.novel_volume_store.save(VolumePlan(volume_id="v2", project_id="p1", index=2))
        assert len(reg.novel_volume_store.list_by_project("p1")) == 2

    def test_delete(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_volume_store.save(VolumePlan(volume_id="v1", project_id="p1"))
        reg.novel_volume_store.delete("v1")
        assert reg.novel_volume_store.load("v1") is None


class TestNovelChapterPlanStore:
    def test_save_and_load(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        plan = ChapterPlan(chapter_id="ch1", project_id="p1", chapter_index=1, title="第一章")
        reg.novel_chapter_plan_store.save(plan)
        loaded = reg.novel_chapter_plan_store.load("ch1")
        assert loaded.title == "第一章"

    def test_load_by_index(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_chapter_plan_store.save(ChapterPlan(chapter_id="ch1", project_id="p1", chapter_index=1))
        loaded = reg.novel_chapter_plan_store.load_by_index("p1", 1)
        assert loaded.chapter_id == "ch1"

    def test_get_next_index(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        assert reg.novel_chapter_plan_store.get_next_index("p1") == 1
        reg.novel_chapter_plan_store.save(ChapterPlan(chapter_id="ch1", project_id="p1", chapter_index=1))
        assert reg.novel_chapter_plan_store.get_next_index("p1") == 2

    def test_list_by_project(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_chapter_plan_store.save(ChapterPlan(chapter_id="ch1", project_id="p1", chapter_index=1))
        reg.novel_chapter_plan_store.save(ChapterPlan(chapter_id="ch2", project_id="p1", chapter_index=2))
        plans = reg.novel_chapter_plan_store.list_by_project("p1")
        assert len(plans) == 2
        assert plans[0].chapter_index == 1


class TestNovelChapterDraftStore:
    def test_save_and_load(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_chapter_plan_store.save(ChapterPlan(chapter_id="ch1", project_id="p1"))
        d = ChapterDraft(draft_id="d1", chapter_id="ch1", text="正文内容", char_count=4)
        reg.novel_chapter_draft_store.save(d)
        loaded = reg.novel_chapter_draft_store.load("d1")
        assert loaded.text == "正文内容"

    def test_load_latest(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_chapter_plan_store.save(ChapterPlan(chapter_id="ch1", project_id="p1"))
        reg.novel_chapter_draft_store.save(ChapterDraft(draft_id="d1", chapter_id="ch1", revision=1))
        reg.novel_chapter_draft_store.save(ChapterDraft(draft_id="d2", chapter_id="ch1", revision=2))
        latest = reg.novel_chapter_draft_store.load_latest("ch1")
        assert latest.revision == 2

    def test_list_by_chapter(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_chapter_plan_store.save(ChapterPlan(chapter_id="ch1", project_id="p1"))
        reg.novel_chapter_draft_store.save(ChapterDraft(draft_id="d1", chapter_id="ch1", revision=1))
        reg.novel_chapter_draft_store.save(ChapterDraft(draft_id="d2", chapter_id="ch1", revision=2))
        drafts = reg.novel_chapter_draft_store.list_by_chapter("ch1")
        assert len(drafts) == 2


class TestNovelLedgerStore:
    def test_upsert_and_load(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        item = LedgerItem(item_id="li1", project_id="p1", section="foreshadowing", entity="金锁", content="埋设伏笔")
        reg.novel_ledger_store.upsert(item)
        loaded = reg.novel_ledger_store.load("li1")
        assert loaded.entity == "金锁"

    def test_list_by_project_section(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_ledger_store.upsert(LedgerItem(item_id="li1", project_id="p1", section="foreshadowing"))
        reg.novel_ledger_store.upsert(LedgerItem(item_id="li2", project_id="p1", section="timeline"))
        assert len(reg.novel_ledger_store.list_by_project("p1", "foreshadowing")) == 1
        assert len(reg.novel_ledger_store.list_by_project("p1")) == 2

    def test_resolve(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_ledger_store.upsert(LedgerItem(item_id="li1", project_id="p1", status="active"))
        reg.novel_ledger_store.resolve("li1")
        assert reg.novel_ledger_store.load("li1").status == "resolved"

    def test_search(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_ledger_store.upsert(LedgerItem(item_id="li1", project_id="p1", entity="金锁", content="重要道具"))
        results = reg.novel_ledger_store.search("p1", "金锁")
        assert len(results) == 1


class TestNovelCharacterStore:
    def test_save_and_load(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        c = NovelCharacter(character_id="c1", project_id="p1", name="主角", role="protagonist")
        reg.novel_character_store.save(c)
        loaded = reg.novel_character_store.load("c1")
        assert loaded.name == "主角"

    def test_list_by_project(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_character_store.save(NovelCharacter(character_id="c1", project_id="p1", name="A"))
        reg.novel_character_store.save(NovelCharacter(character_id="c2", project_id="p1", name="B"))
        assert len(reg.novel_character_store.list_by_project("p1")) == 2

    def test_delete(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_character_store.save(NovelCharacter(character_id="c1", project_id="p1"))
        reg.novel_character_store.delete("c1")
        assert reg.novel_character_store.load("c1") is None


class TestNovelBatchProgressStore:
    def test_save_and_load(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        bp = BatchProgress(batch_id="b1", project_id="p1", chapter_start=1, chapter_end=5)
        reg.novel_batch_progress_store.save(bp)
        loaded = reg.novel_batch_progress_store.load("b1")
        assert loaded.chapter_end == 5

    def test_list_by_project(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_batch_progress_store.save(BatchProgress(batch_id="b1", project_id="p1"))
        reg.novel_batch_progress_store.save(BatchProgress(batch_id="b2", project_id="p1"))
        assert len(reg.novel_batch_progress_store.list_by_project("p1")) == 2


class TestNovelReferenceBookStore:
    def test_save_and_load(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        b = ReferenceBook(book_id="rb1", project_id="p1", name="斗破苍穹", role="primary")
        reg.novel_reference_book_store.save(b)
        loaded = reg.novel_reference_book_store.load("rb1")
        assert loaded.name == "斗破苍穹"

    def test_list_by_project(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_reference_book_store.save(ReferenceBook(book_id="rb1", project_id="p1"))
        assert len(reg.novel_reference_book_store.list_by_project("p1")) == 1

    def test_delete(self, reg):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_reference_book_store.save(ReferenceBook(book_id="rb1", project_id="p1"))
        reg.novel_reference_book_store.delete("rb1")
        assert reg.novel_reference_book_store.load("rb1") is None
