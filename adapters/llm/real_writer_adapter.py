"""Real Writer Adapter using the configured provider."""

from __future__ import annotations

from typing import Any

from .deepseek_adapter import DeepSeekAdapter
from ...contracts.provider_request import ProviderAttemptReceipt
from ...contracts.writer_input_bundle import WriterInputBundle
from ...runtime.ooc_detector import OOCDetector
from ...runtime.prompt_assembler import PromptAssembler, WRITER_SYSTEM_PROMPT


class RealWriterV2Adapter:
    """Real Writer adapter using DeepSeek."""

    def __init__(self, deepseek: DeepSeekAdapter, model: str = "", preset_text: str = ""):
        self._llm = deepseek
        self._model = model
        self._preset_text = preset_text
        # Writer uses Pro model — disable thinking for faster, more direct output
        self._extra_body = {"thinking": {"type": "disabled"}}

    def set_preset(self, preset_text: str) -> None:
        self._preset_text = preset_text

    def generate(
        self,
        bundle: WriterInputBundle,
        workflow_run_id: str = "",
        trace_id: str = "",
        turn_id: str = "",
        attempt_id: str = "",
        snapshot: Any = None,
    ) -> tuple[str, ProviderAttemptReceipt]:
        """Generate narrative text with a deterministic revise loop."""
        _ = snapshot
        max_revisions = 2
        system_prompt = self._build_writer_system_prompt()
        user_prompt = self._build_writer_user_prompt(bundle)

        text, receipt = self._llm.generate_text(
            user_prompt,
            provider_role="writer",
            workflow_run_id=workflow_run_id,
            trace_id=trace_id,
            model=self._model,
            turn_id=turn_id,
            attempt_id=attempt_id,
            extra_body=self._extra_body,
            system_prompt=system_prompt,
        )

        for rev in range(max_revisions):
            issues = self._check_output(text, bundle)
            if not issues:
                break
            revise_prompt = self._build_revise_prompt(user_prompt, text, issues, rev + 1)
            revised_text, rev_receipt = self._llm.generate_text(
                revise_prompt,
                provider_role="writer_revise",
                workflow_run_id=workflow_run_id,
                trace_id=trace_id,
                model=self._model,
                turn_id=turn_id,
                attempt_id=f"{attempt_id}_r{rev + 1}",
                extra_body=self._extra_body,
                system_prompt=system_prompt,
            )
            if revised_text.strip():
                text = revised_text
                receipt = rev_receipt

        return text, receipt

    def _build_writer_system_prompt(self) -> str:
        """Build Writer system prompt with optional preset."""
        if self._preset_text:
            return f"""{WRITER_SYSTEM_PROMPT}

=== WRITER STYLE & CONSTRAINT PRESET ===
{self._preset_text}
=== END PRESET ==="""
        return WRITER_SYSTEM_PROMPT

    def _build_writer_prompt(self, bundle: WriterInputBundle) -> str:
        """Backward-compatible alias for _build_writer_user_prompt."""
        return self._build_writer_user_prompt(bundle)

    def _build_writer_user_prompt(self, bundle: WriterInputBundle) -> str:
        """Build user prompt for Writer text generation.

        Separates stable worldbook context from volatile turn data for provider
        prefix caching. Context budgeting is handled upstream, so this method
        preserves the selected text instead of applying character truncation.
        """
        _, user_prompt = PromptAssembler(bundle.worldbook_context).assemble(
            final_turn_brief=bundle.final_turn_brief,
            score=getattr(bundle, "score", ""),
            recent_turns=bundle.recent_turns_context,
            older_turns_summary=getattr(bundle, "older_turns_summary", ""),
            variable_snapshot=getattr(bundle, "variable_snapshot", {}),
            player_input=bundle.player_input,
            card_profile=getattr(bundle, "card_profile_context", {}),
            opening_context=bundle.opening_context,
            active_memories=bundle.active_memory_context,
            rag_memories=bundle.rag_memory_context,
            accepted_guidance=bundle.accepted_guidance,
            card_state_context=bundle.card_state_context,
        )
        return user_prompt

    def _check_output(self, text: str, bundle: WriterInputBundle | None = None) -> list[str]:
        """Run deterministic checks on generated text."""
        issues = []
        length = len(text.strip()) if text else 0
        if length < 1000:
            issues.append(
                f"WORD_COUNT_CRITICAL: only {length} characters. "
                f"Minimum is 1000, target is 1200-1600. Please expand significantly."
            )
        elif length < 1200:
            issues.append(
                f"WORD_COUNT_LOW: {length} characters. "
                f"Target is 1200-1600. Need {1200 - length} more characters. "
                f"Add more sensory details, internal monologue, or scene description."
            )
        elif length > 1600:
            issues.append(
                f"WORD_COUNT_HIGH: {length} characters. "
                f"Target is 1200-1600. Trim {length - 1600} characters."
            )

        if text.strip().startswith("#"):
            issues.append(
                "FORMAT_ERROR: Text starts with markdown heading '#'. "
                "Remove meta markers and begin with narrative prose."
            )
        if bundle is not None:
            issues.extend(OOCDetector().detect(text, getattr(bundle, "score", "")))
        return issues

    def _build_revise_prompt(
        self,
        original_prompt: str,
        current_text: str,
        issues: list[str],
        attempt: int,
    ) -> str:
        issue_text = "\n".join(f"- {item}" for item in issues)
        return (
            f"{original_prompt}\n\n"
            f"=== REVISION REQUEST (attempt {attempt}; volatile) ===\n\n"
            f"Your previous output had the following issues:\n"
            f"{issue_text}\n\n"
            f"=== YOUR PREVIOUS OUTPUT (for reference) ===\n"
            f"{current_text[:2000]}\n\n"
            f"Please rewrite the entire narrative response, fixing every issue above. "
            f"Do not add meta commentary or markdown headers."
        )
