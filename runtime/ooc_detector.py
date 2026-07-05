"""Deterministic semantic checks for Writer output."""

from __future__ import annotations

import re


class OOCDetector:
    """Detect direct violations of Director score constraints."""

    def detect(self, writer_output: str, score: str = "") -> list[str]:
        output = str(writer_output or "")
        constraints = self._extract_constraints(score)
        issues = []
        for constraint in constraints:
            violation = self._direct_violation(output, constraint)
            if violation:
                issues.append(f"SCORE_VIOLATION: {violation}")
        return issues

    def _extract_constraints(self, score: str) -> list[str]:
        text = str(score or "")
        if not text:
            return []
        blocks = re.findall(r"<constraint>\s*(.*?)\s*</constraint>", text, flags=re.DOTALL | re.IGNORECASE)
        source = "\n".join(blocks) if blocks else text
        constraints = []
        for raw_line in source.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("-"):
                line = line[1:].strip()
            if line:
                constraints.append(line)
        return constraints

    def _direct_violation(self, output: str, constraint: str) -> str:
        phrase = self._forbidden_phrase(constraint)
        if phrase and phrase in output:
            return phrase
        return ""

    def _forbidden_phrase(self, constraint: str) -> str:
        text = str(constraint or "").strip()
        prefixes = ("不要", "不能", "禁止", "不得", "must not ", "do not ", "never ")
        lowered = text.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix):
                phrase = text[len(prefix):].strip(" ：:，,。.")
                for causative in ("让", "使"):
                    if phrase.startswith(causative):
                        phrase = phrase[len(causative):].strip()
                return phrase
        return ""
