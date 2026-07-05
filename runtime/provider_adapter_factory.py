"""Provider adapter factory — resolves ModelProfile → real/fake adapters.

Single controlled entry point for building Director/Writer/Player adapters
inside the persistent turn nodes.

Rules:
  - fake profile → fake adapter (offline tests, no API key).
  - real profile → real DeepSeek-backed adapter via the existing
    RealDirectorV2Adapter / RealWriterV2Adapter. No silent fallback to fake.
  - real profile with missing API key / provider call failure → structured
    ProviderFailure returned to the caller. The caller records it in
    diagnostics and never downgrades to fake.
  - API keys are NEVER stored in code, traces, or the database. Only the env
    var name (from the profile) is referenced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..adapters.llm.model_profile_registry import ModelProfile, ModelProfileRegistry
from ..contracts.director_plan import DirectorPlan
from ..contracts.final_turn_brief import FinalTurnBrief
from ..contracts.round_snapshot import RoundSnapshot
from ..contracts.writer_draft import WriterDraft
from ..contracts.writer_input_bundle import WriterInputBundle


@dataclass
class AdapterOutcome:
    """Outcome of building + running an adapter.

    Either the adapter was built (and may be run), or building failed with a
    structured failure code/message. Never contains API keys.
    """

    is_real: bool
    provider: str  # "deepseek" | "fake"
    model: str
    profile_id: str
    api_key_env: str  # env var NAME only, never the value
    built: bool
    failure_code: str = ""
    failure_message: str = ""


def _resolve_api_key_env(profile: ModelProfile) -> str:
    """Determine the api_key env var from the profile."""
    return profile.api_key_env or "DEEPSEEK_API_KEY"


def _check_api_key(profile: ModelProfile) -> tuple[str, AdapterOutcome | None]:
    """Check if the profile's api key env var is set.

    Returns (api_key_env, None) on success, (api_key_env, failure_outcome) on failure.
    """
    import os
    api_key_env = _resolve_api_key_env(profile)
    if not os.environ.get(api_key_env, ""):
        return api_key_env, AdapterOutcome(
            is_real=True,
            provider=profile.provider,
            model=profile.model,
            profile_id=profile.profile_id,
            api_key_env=api_key_env,
            built=False,
            failure_code="NOT_CONFIGURED",
            failure_message=f"API key env var '{api_key_env}' is not set",
        )
    return api_key_env, None


def _build_deepseek_adapter(profile: ModelProfile):
    """Construct a DeepSeekAdapter from a real profile.

    Returns (adapter, outcome). Does NOT raise on missing key — returns a
    structured failure so the caller can fail closed.
    """
    api_key_env, failure = _check_api_key(profile)
    if failure is not None:
        return None, failure

    from ..adapters.llm.deepseek_adapter import DeepSeekAdapter
    adapter = DeepSeekAdapter(
        model=profile.model,
        default_max_tokens=profile.default_max_tokens,
        timeout_seconds=profile.timeout_seconds,
        max_retries=profile.max_retries,
    )
    return adapter, AdapterOutcome(
        is_real=True,
        provider=profile.provider,
        model=profile.model,
        profile_id=profile.profile_id,
        api_key_env=api_key_env,
        built=True,
    )


def _build_openai_compatible_adapter(profile: ModelProfile):
    """Construct an OpenAICompatibleAdapter for Qwen/GLM/etc.

    Quietly falls back to DeepSeekAdapter when base_url matches DeepSeek.
    """
    api_key_env, failure = _check_api_key(profile)
    if failure is not None:
        return None, failure

    from ..adapters.llm.openai_compatible import OpenAICompatibleAdapter
    adapter = OpenAICompatibleAdapter(
        model=profile.model,
        base_url=profile.base_url,
        api_key_env=api_key_env,
        default_max_tokens=profile.default_max_tokens,
        timeout_seconds=profile.timeout_seconds,
        max_retries=profile.max_retries,
    )
    return adapter, AdapterOutcome(
        is_real=True,
        provider=profile.provider,
        model=profile.model,
        profile_id=profile.profile_id,
        api_key_env=api_key_env,
        built=True,
    )


def _select_adapter(profile: ModelProfile):
    """Route profile to the correct adapter builder.

    - fake provider → handled by the caller (Director/WriterFactory)
    - deepseek provider → DeepSeekAdapter
    - openai provider → OpenAICompatibleAdapter (Qwen, GLM, etc.)
    """
    if profile.provider == "deepseek":
        return _build_deepseek_adapter(profile)
    return _build_openai_compatible_adapter(profile)


class DirectorAdapterFactory:
    """Builds a Director adapter from a profile id.

    fake-director → FakeDirectorV2Adapter (deterministic).
    real profile  → RealDirectorV2Adapter backed by DeepSeek.
    unknown       → fail closed (ModelProfileRegistry raises ValueError).
    """

    @staticmethod
    def build(profile_id: str) -> tuple[Any, AdapterOutcome]:
        profile = ModelProfileRegistry.resolve(profile_id)

        if profile.provider == "fake":
            from ..runtime.director_v2_runtime import FakeDirectorV2Adapter
            return FakeDirectorV2Adapter(), AdapterOutcome(
                is_real=False, provider="fake", model=profile.model,
                profile_id=profile.profile_id, api_key_env="", built=True,
            )

        ds, outcome = _select_adapter(profile)
        if not outcome.built:
            return None, outcome
        from ..adapters.llm.real_director_adapter import RealDirectorV2Adapter
        return RealDirectorV2Adapter(ds, model=profile.model), outcome


class WriterAdapterFactory:
    """Builds a Writer adapter from a profile id."""

    @staticmethod
    def build(profile_id: str, preset_text: str = "") -> tuple[Any, AdapterOutcome]:
        profile = ModelProfileRegistry.resolve(profile_id)

        if profile.provider == "fake":
            from ..runtime.writer_v2_runtime import FakeWriterV2Adapter
            return FakeWriterV2Adapter(), AdapterOutcome(
                is_real=False, provider="fake", model=profile.model,
                profile_id=profile.profile_id, api_key_env="", built=True,
            )

        ds, outcome = _select_adapter(profile)
        if not outcome.built:
            return None, outcome
        from ..adapters.llm.real_writer_adapter import RealWriterV2Adapter
        return RealWriterV2Adapter(ds, model=profile.model, preset_text=preset_text), outcome


def run_director(
    adapter: Any,
    outcome: AdapterOutcome,
    snapshot: RoundSnapshot,
    workflow_run_id: str,
    trace_id: str,
    turn_id: str,
    attempt_id: str,
) -> tuple[DirectorPlan | None, dict[str, Any]]:
    """Run the director adapter. Returns (plan_or_None, provider_receipt_dict).

    On real-provider failure returns (None, failure_receipt) so the caller can
    fail closed. Fake adapters never fail here.
    """
    if not outcome.is_real:
        # Fake path: existing fake director plan signature
        try:
            plan = adapter.generate_plan(snapshot)
            return plan, {}
        except Exception as e:  # pragma: no cover - defensive
            return None, {"success": False, "failure_code": "ADAPTER_ERROR",
                          "failure_message": str(e)[:200]}

    # Real path
    plan, receipt = adapter.generate_plan(
        snapshot,
        workflow_run_id=workflow_run_id,
        trace_id=trace_id,
        turn_id=turn_id,
        attempt_id=attempt_id,
    )
    receipt_dict = receipt.to_dict() if hasattr(receipt, "to_dict") else dict(receipt)
    if not receipt_dict.get("success", False):
        return None, receipt_dict
    if plan is None or (hasattr(plan, "turn_goal") and not plan.turn_goal):
        # Empty plan from a "successful" but empty response
        return None, {**receipt_dict, "failure_code": "EMPTY_RESPONSE",
                       "failure_message": "Director produced empty plan"}
    return plan, receipt_dict


def run_writer(
    adapter: Any,
    outcome: AdapterOutcome,
    bundle: WriterInputBundle,
    workflow_run_id: str,
    trace_id: str,
    turn_id: str,
    attempt_id: str,
    snapshot: RoundSnapshot | None = None,
) -> tuple[str, dict[str, Any]]:
    """Run the writer adapter. Returns (text, provider_receipt_dict).

    Empty text on real-provider failure returns ("", failure_receipt).
    """
    if not outcome.is_real:
        try:
            text = adapter.generate(bundle)
            return text, {}
        except Exception as e:  # pragma: no cover - defensive
            return "", {"success": False, "failure_code": "ADAPTER_ERROR",
                        "failure_message": str(e)[:200]}

    text, receipt = adapter.generate(
        bundle,
        workflow_run_id=workflow_run_id,
        trace_id=trace_id,
        turn_id=turn_id,
        attempt_id=attempt_id,
        snapshot=snapshot,
    )
    receipt_dict = receipt.to_dict() if hasattr(receipt, "to_dict") else dict(receipt)
    if not receipt_dict.get("success", False):
        return "", receipt_dict
    if not text.strip():
        return "", {**receipt_dict, "failure_code": "EMPTY_RESPONSE",
                    "failure_message": "Writer produced empty text"}
    return text, receipt_dict
