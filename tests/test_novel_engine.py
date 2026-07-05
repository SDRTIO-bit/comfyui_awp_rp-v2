"""Tests for NovelEngine."""

import pytest
from awp_rp_runtime_v2.runtime.novel_engine import NovelEngine
from awp_rp_runtime_v2.contracts.novel_project import NovelProject
from awp_rp_runtime_v2.contracts.novel_chapter import ChapterPlan


@pytest.fixture
def reg(tmp_path):
    from awp_rp_runtime_v2.storage.sqlite.database import Database
    from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    return SessionRuntimeStoreRegistry(db)


@pytest.fixture
def engine(reg):
    return NovelEngine(reg)


class TestNovelEngine:
    def test_plan_chapter(self, reg, engine):
        reg.novel_project_store.create(NovelProject(project_id="p1", title="测试"))
        plan = engine.plan_chapter(project_id="p1", chapter_index=1)
        assert plan.chapter_index == 1
        assert plan.project_id == "p1"
        # Verify persisted
        loaded = reg.novel_chapter_plan_store.load_by_index("p1", 1)
        assert loaded is not None

    def test_plan_chapter_no_project(self, engine):
        with pytest.raises(ValueError, match="Project not found"):
            engine.plan_chapter(project_id="nope", chapter_index=1)

    def test_write_chapter(self, reg, engine):
        reg.novel_project_store.create(NovelProject(project_id="p1", title="测试"))
        reg.novel_chapter_plan_store.save(ChapterPlan(
            chapter_id="ch1", project_id="p1", chapter_index=1, target_chars=100
        ))
        draft = engine.write_chapter(project_id="p1", chapter_index=1)
        assert draft.chapter_id == "ch1"
        assert draft.text  # Has content
        # Verify persisted
        loaded = reg.novel_chapter_draft_store.load_latest("ch1")
        assert loaded is not None

    def test_write_chapter_no_plan(self, reg, engine):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        with pytest.raises(ValueError, match="Chapter plan not found"):
            engine.write_chapter(project_id="p1", chapter_index=1)

    def test_revise_chapter(self, reg, engine):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        reg.novel_chapter_plan_store.save(ChapterPlan(
            chapter_id="ch1", project_id="p1", chapter_index=1, target_chars=100
        ))
        # Write first draft
        draft1 = engine.write_chapter(project_id="p1", chapter_index=1)
        assert draft1.revision == 1

        # Revise
        draft2 = engine.revise_chapter(project_id="p1", chapter_index=1, feedback="改进结尾")
        assert draft2.revision == 2
        assert draft2.chapter_id == "ch1"

    def test_batch_write(self, reg, engine):
        reg.novel_project_store.create(NovelProject(project_id="p1"))
        completed = []

        def on_complete(idx, draft):
            completed.append(idx)

        drafts = engine.batch_write(
            project_id="p1",
            chapter_start=1,
            chapter_end=3,
            on_chapter_complete=on_complete,
        )

        assert len(drafts) == 3
        assert completed == [1, 2, 3]
        # Verify batch progress
        progress_list = reg.novel_batch_progress_store.list_by_project("p1")
        assert len(progress_list) > 0
        assert progress_list[0].status == "completed"
