"""Tests for novel mode agent layer."""

import pytest
from awp_rp_runtime_v2.runtime.novel_style_cleaner import NovelStyleCleaner
from awp_rp_runtime_v2.runtime.novel_quality_pipeline import NovelQualityPipeline
from awp_rp_runtime_v2.runtime.novel_write_packet_builder import NovelWritePacketBuilder
from awp_rp_runtime_v2.contracts.novel_chapter import ChapterPlan, BeatDetail, ContentSummary
from awp_rp_runtime_v2.contracts.novel_ledger import LedgerItem
from awp_rp_runtime_v2.contracts.novel_director_guidance import DirectorGuidance


@pytest.fixture
def reg(tmp_path):
    from awp_rp_runtime_v2.storage.sqlite.database import Database
    from awp_rp_runtime_v2.runtime.session_runtime_registry import SessionRuntimeStoreRegistry
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    return SessionRuntimeStoreRegistry(db)


class TestNovelStyleCleaner:
    def test_banned_words_tier1(self, reg):
        cleaner = NovelStyleCleaner(reg)
        text = "他仿佛看到了一丝希望，不禁微微颤抖。"
        issues = cleaner.check_banned_words(text)
        assert len(issues) >= 4  # 仿佛, 一丝, 不禁, 微微

    def test_banned_patterns(self, reg):
        cleaner = NovelStyleCleaner(reg)
        text = "不是他不想去，而是他不能去。"
        issues = cleaner.check_banned_patterns(text)
        assert len(issues) >= 1

    def test_metadata_leak(self, reg):
        cleaner = NovelStyleCleaner(reg)
        text = "第三章开始了。\n上一章说到他走了。"
        issues = cleaner.check_metadata_leak(text)
        assert len(issues) >= 2

    def test_degeneration_repetition(self, reg):
        cleaner = NovelStyleCleaner(reg)
        text = "他慢慢地走出了房间。他慢慢地走出了房间。他慢慢地走出了房间。"
        issues = cleaner.check_degeneration(text)
        assert any(i["type"] == "repetition" for i in issues)

    def test_degeneration_truncation(self, reg):
        cleaner = NovelStyleCleaner(reg)
        # Must be > 100 chars to trigger truncation check
        text = "他推开门走了进去。房间很暗，他摸到了开关。灯亮了。" * 5 + "他走到了门"
        issues = cleaner.check_degeneration(text)
        assert any(i["type"] == "truncation" for i in issues)

    def test_degeneration_ai_refusal(self, reg):
        cleaner = NovelStyleCleaner(reg)
        text = "作为AI，我无法续写这段内容。"
        issues = cleaner.check_degeneration(text)
        assert any(i["type"] == "ai_refusal" for i in issues)

    def test_degeneration_engineering_leak(self, reg):
        cleaner = NovelStyleCleaner(reg)
        text = "这个细纲需要修改。"
        issues = cleaner.check_degeneration(text)
        assert any(i["type"] == "engineering_leak" for i in issues)

    def test_chapter_structure_weather_opening(self, reg):
        cleaner = NovelStyleCleaner(reg)
        text = "阳光明媚的早晨，微风拂过。\n" + "他起床了。\n" * 100
        issues = cleaner.check_chapter_structure(text)
        assert any("天气" in i for i in issues)

    def test_chapter_structure_summary_ending(self, reg):
        cleaner = NovelStyleCleaner(reg)
        text = "他起床了。\n" * 100 + "\n他终于明白了这一切。"
        issues = cleaner.check_chapter_structure(text)
        assert any("总结" in i for i in issues)

    def test_normalize_punctuation(self, reg):
        cleaner = NovelStyleCleaner(reg)
        text = "他走了……然后——回来了"
        normalized = cleaner.normalize_punctuation(text)
        assert "……" not in normalized
        assert "——" not in normalized

    def test_full_check(self, reg):
        cleaner = NovelStyleCleaner(reg)
        text = "他仿佛看到了一丝希望。" * 10
        result = cleaner.full_check(text)
        assert "issues" in result
        assert "blocking_count" in result
        assert result["blocking_count"] > 0


class TestNovelQualityPipeline:
    def test_pass_clean_text(self, reg):
        pipeline = NovelQualityPipeline(reg)
        text = "他推开门，走了进去。房间很暗，他摸到了开关。灯亮了。" * 100
        plan = ChapterPlan(target_chars=3000)
        decision = pipeline.check_chapter(text, plan)
        # Should pass (no blocking issues for clean text)
        assert decision.verdict.value in ("accept", "revise")  # May revise on length

    def test_fail_banned_words(self, reg):
        pipeline = NovelQualityPipeline(reg)
        text = "他仿佛看到了一丝希望，不禁微微颤抖。" * 50
        plan = ChapterPlan(target_chars=3000)
        decision = pipeline.check_chapter(text, plan)
        assert decision.verdict.value == "revise"
        assert len(decision.blocking_reasons) > 0

    def test_fail_metadata_leak(self, reg):
        pipeline = NovelQualityPipeline(reg)
        text = "第三章开始了。\n他推开门走了进去。\n" * 100
        plan = ChapterPlan(target_chars=3000)
        decision = pipeline.check_chapter(text, plan)
        assert decision.verdict.value == "revise"

    def test_fail_short_text(self, reg):
        pipeline = NovelQualityPipeline(reg)
        text = "他走了。"
        plan = ChapterPlan(target_chars=3000)
        decision = pipeline.check_chapter(text, plan)
        assert decision.verdict.value == "revise"
        assert any("字数严重不足" in r for r in decision.blocking_reasons)


class TestNovelWritePacketBuilder:
    def test_build_packet(self, reg):
        builder = NovelWritePacketBuilder(reg)
        plan = ChapterPlan(
            chapter_id="ch1",
            project_id="p1",
            chapter_index=1,
            target_chars=3000,
            content_summary=ContentSummary(cause="起因", development="发展"),
        )
        items = [
            LedgerItem(item_id="li1", project_id="p1", section="foreshadowing", entity="金锁", status="active"),
        ]
        guidance = DirectorGuidance(guidance_id="g1", pacing_strategy="紧凑")

        packet = builder.build(
            chapter_plan=plan,
            ledger_items=items,
            previous_chapter_summary="上一章摘要",
            character_states={"主角": "状态"},
            director_guidance=guidance,
        )

        assert packet.chapter_id == "ch1"
        assert len(packet.relevant_ledger_items) == 1
        assert "目标情绪" in packet.writing_intent

    def test_build_beat_packet(self, reg):
        builder = NovelWritePacketBuilder(reg)
        plan = ChapterPlan(chapter_id="ch1", project_id="p1")
        beat = BeatDetail(beat_id="b1", description="开门", budget_chars=300)
        guidance = DirectorGuidance(guidance_id="g1")

        packet = builder.build_beat_packet(
            beat=beat,
            accumulated_text="前面的内容",
            chapter_plan=plan,
            director_guidance=guidance,
            ledger_items=[],
        )

        assert packet.current_scene_beat.beat_id == "b1"
        assert packet.accumulated_text == "前面的内容"
