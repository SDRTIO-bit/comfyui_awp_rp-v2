"""Tests for deterministic Writer semantic issue detection."""

from awp_rp_runtime_v2.runtime.ooc_detector import OOCDetector


class TestOOCDetector:

    def test_flags_score_constraint_violation(self):
        score = """<direction>
<constraint>
- 不要让她立刻开门
- 不要替玩家做决定
</constraint>
</direction>"""
        issues = OOCDetector().detect(
            writer_output="她立刻开门，替玩家做出了选择。",
            score=score,
        )

        assert any("SCORE_VIOLATION" in issue for issue in issues)
        assert any("立刻开门" in issue for issue in issues)

    def test_allows_output_without_direct_constraint_violation(self):
        score = """<direction>
<constraint>
- 不要让她立刻开门
</constraint>
</direction>"""
        issues = OOCDetector().detect(
            writer_output="她的手停在门把上，呼吸短促，却迟迟没有压下去。",
            score=score,
        )

        assert issues == []


class TestOOCDetectorUnicode:

    def test_flags_real_chinese_constraint_violation(self):
        score = (
            "<direction>\n<constraint>\n"
            "- \u4e0d\u8981\u8ba9\u5979\u7acb\u523b\u5f00\u95e8\n"
            "</constraint>\n</direction>"
        )
        issues = OOCDetector().detect(
            writer_output="\u5979\u7acb\u523b\u5f00\u95e8\uff0c\u50cf\u7ec8\u4e8e\u4e0b\u5b9a\u4e86\u51b3\u5fc3\u3002",
            score=score,
        )

        assert any("SCORE_VIOLATION" in issue for issue in issues)
        assert any("\u5979\u7acb\u523b\u5f00\u95e8" in issue for issue in issues)
