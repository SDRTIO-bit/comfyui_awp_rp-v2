"""AWPV2WriterGenerate — runs Writer to produce WRITER_DRAFT.

This is the missing node in the C1 explicit pipeline:
  WriterInputBundle → [AWPV2WriterGenerate] → WRITER_DRAFT → QualityPipeline → Reviser

Supports both fake (testing) and real (DeepSeek) adapters via profile_id.
"""

from __future__ import annotations

from typing import Any

from ..runtime.default_model_profiles import DEFAULT_WRITER_PROFILE_ID


class AWPV2WriterGenerate:
    """Run Writer agent to produce WriterDraft from WriterInputBundle.

    Supports:
      - fake-writer: deterministic fake output (no API call)
      - deepseek-v4-pro-writer / deepseek-v4-flash-writer: real DeepSeek
    """

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:
        return {
            "required": {
                "writer_input_bundle": ("WRITER_INPUT_BUNDLE",),
            },
            "optional": {
                "profile_id": ("STRING", {"default": DEFAULT_WRITER_PROFILE_ID}),
                "workflow_run_id": ("STRING", {"default": ""}),
                "trace_id": ("STRING", {"default": ""}),
                "turn_id": ("STRING", {"default": ""}),
                "attempt_id": ("STRING", {"default": ""}),
                "writer_preset_path": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("WRITER_DRAFT",)
    RETURN_NAMES = ("writer_draft",)
    FUNCTION = "execute"
    CATEGORY = "AWP V2 / Writer"

    def execute(
        self,
        writer_input_bundle: dict[str, Any],
        profile_id: str = DEFAULT_WRITER_PROFILE_ID,
        workflow_run_id: str = "",
        trace_id: str = "",
        turn_id: str = "",
        attempt_id: str = "",
        writer_preset_path: str = "",
    ) -> tuple[dict[str, Any]]:
        from ..contracts.writer_input_bundle import WriterInputBundle
        from ..runtime.writer_v2_runtime import WriterV2Runtime, FakeWriterV2Adapter

        bundle = WriterInputBundle.from_dict(writer_input_bundle)

        # Resolve adapter
        if profile_id.startswith("fake"):
            adapter = FakeWriterV2Adapter()
        else:
            from ..adapters.llm.model_profile_registry import ModelProfileRegistry
            from ..adapters.llm.deepseek_adapter import DeepSeekAdapter
            from ..adapters.llm.real_writer_adapter import RealWriterV2Adapter

            profile = ModelProfileRegistry.resolve(profile_id)
            deepseek = DeepSeekAdapter()
            adapter = RealWriterV2Adapter(
                deepseek=deepseek,
                model=profile.model,
            )
            # Load preset if provided
            if writer_preset_path:
                try:
                    from pathlib import Path
                    preset_text = Path(writer_preset_path).read_text(encoding="utf-8")
                    adapter.set_preset(preset_text)
                except Exception:
                    pass

        runtime = WriterV2Runtime(adapter)

        # Use real adapter's extended generate if available
        if hasattr(adapter, "generate") and not profile_id.startswith("fake"):
            from ..contracts.writer_draft import WriterDraft
            import uuid
            from datetime import datetime, timezone

            text, _receipt = adapter.generate(
                bundle,
                workflow_run_id=workflow_run_id,
                trace_id=trace_id,
                turn_id=turn_id,
                attempt_id=attempt_id,
            )
            now = datetime.now(timezone.utc).isoformat()
            draft = WriterDraft(
                draft_id=f"wd_{uuid.uuid4().hex[:12]}",
                trace_id=trace_id,
                snapshot_id=bundle.snapshot_id,
                writer_input_bundle_id=bundle.bundle_id,
                text=text,
                character_count=len(text),
                revision_number=0,
                created_at=now,
            )
            return (draft.to_dict(),)

        # Fake path
        draft = runtime.run(bundle)
        return (draft.to_dict(),)
