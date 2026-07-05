"""Deterministic emotional summary for older accepted turns."""

from __future__ import annotations

from ..contracts.turn_record import TurnRecord


class EmotionalSummarizer:
    """Compress older full turns into compact continuity lines."""

    def summarize(self, turns: list[TurnRecord]) -> str:
        if not turns:
            return ""
        ordered = sorted(turns, key=lambda turn: turn.turn_index)
        return "\n".join(self._summarize_turn(turn) for turn in ordered)

    def _summarize_turn(self, turn: TurnRecord) -> str:
        player = self._first_sentence(turn.player_input)
        writer = self._first_sentence(turn.writer_output)
        emotion = self._emotion_cue(f"{turn.player_input}\n{turn.writer_output}")
        parts = [f"Turn {turn.turn_index}"]
        if player:
            parts.append(f"player={player}")
        if writer:
            parts.append(f"outcome={writer}")
        if emotion:
            parts.append(f"emotion={emotion}")
        return ": " + "; ".join(parts) if len(parts) == 1 else parts[0] + ": " + "; ".join(parts[1:])

    def _first_sentence(self, text: str) -> str:
        text = " ".join(str(text or "").split())
        if not text:
            return ""
        for sep in ("。", "！", "？", ".", "!", "?"):
            if sep in text:
                head = text.split(sep, 1)[0].strip()
                return head + sep if head else ""
        return text

    def _emotion_cue(self, text: str) -> str:
        cues = {
            "fear": ("害怕", "恐惧", "颤抖", "怕", "惊慌"),
            "anger": ("愤怒", "生气", "怒", "恨"),
            "sadness": ("悲伤", "难过", "哭", "泪", "失望"),
            "trust": ("信任", "安心", "靠近", "承诺"),
            "tension": ("犹豫", "沉默", "紧张", "拉扯"),
            "joy": ("开心", "快乐", "喜悦", "笑"),
        }
        for cue, keywords in cues.items():
            if any(keyword in text for keyword in keywords):
                return cue
        return ""
