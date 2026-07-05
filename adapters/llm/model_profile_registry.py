"""Model Profile Registry — controlled model configuration.

Profiles replace free-form model strings.  Each profileId resolves to a
fixed (provider, model, baseUrl, timeout, token_budget, retry_policy)
tuple.  Unknown profileIds fail closed.  API workflows cannot override
api_key, base_url, or token hard limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelProfile:
    """Immutable model configuration profile."""

    profile_id: str
    provider: str  # "deepseek", "openai", "fake"
    model: str
    base_url: str
    timeout_seconds: int = 60
    default_max_tokens: int = 4000
    max_retries: int = 1
    api_key_env: str = ""  # env var name — never the actual key
    token_hard_limit: int = 50_000  # per-turn cumulative

    def to_safe_dict(self) -> dict[str, Any]:
        """Export without secrets."""
        return {
            "profile_id": self.profile_id,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "default_max_tokens": self.default_max_tokens,
            "max_retries": self.max_retries,
            "api_key_env": self.api_key_env,
            "token_hard_limit": self.token_hard_limit,
        }


# ── Canonical whitelist ─────────────────────────────────────────────────────

_PROFILES: dict[str, ModelProfile] = {}


def _register(profile: ModelProfile) -> None:
    _PROFILES[profile.profile_id] = profile


# DeepSeek production profiles
# NOTE: Director uses Flash (fast, thinking-enabled) for cheap planning.
# Writer uses Pro (capable, thinking-disabled) for quality narrative.
_register(ModelProfile(
    profile_id="deepseek-v4-flash-director",
    provider="deepseek",
    model="deepseek-v4-flash",
    base_url="https://api.deepseek.com",
    timeout_seconds=120,
    default_max_tokens=4000,
    max_retries=2,
    api_key_env="DEEPSEEK_API_KEY",
    token_hard_limit=50_000,
))

_register(ModelProfile(
    profile_id="deepseek-v4-pro-writer",
    provider="deepseek",
    model="deepseek-v4-pro",
    base_url="https://api.deepseek.com",
    timeout_seconds=120,
    default_max_tokens=4000,
    max_retries=2,
    api_key_env="DEEPSEEK_API_KEY",
    token_hard_limit=50_000,
))

# Legacy profiles (kept for backward compatibility)
_register(ModelProfile(
    profile_id="deepseek-v4-pro-director",
    provider="deepseek",
    model="deepseek-v4-pro",
    base_url="https://api.deepseek.com",
    timeout_seconds=120,
    default_max_tokens=4000,
    max_retries=2,
    api_key_env="DEEPSEEK_API_KEY",
    token_hard_limit=50_000,
))

_register(ModelProfile(
    profile_id="deepseek-v4-flash-writer",
    provider="deepseek",
    model="deepseek-v4-flash",
    base_url="https://api.deepseek.com",
    timeout_seconds=60,
    default_max_tokens=4000,
    max_retries=1,
    api_key_env="DEEPSEEK_API_KEY",
    token_hard_limit=50_000,
))

# Simulated player profile (low-cost model, isolated token budget).
# Used ONLY by the user-simulation harness, never by the RP turn pipeline.
_register(ModelProfile(
    profile_id="simulated-player-v1",
    provider="deepseek",
    model="deepseek-v4-flash",
    base_url="https://api.deepseek.com",
    timeout_seconds=60,
    default_max_tokens=1000,
    max_retries=1,
    api_key_env="DEEPSEEK_API_KEY",
    token_hard_limit=20_000,
))

# Fake simulated player for offline harness tests
_register(ModelProfile(
    profile_id="fake-player",
    provider="fake",
    model="fake_player_v1",
    base_url="",
    timeout_seconds=5,
    default_max_tokens=0,
    max_retries=0,
    api_key_env="",
    token_hard_limit=0,
))

# OpenCode Zen provider — unified OpenAI-compatible gateway for all upstream models
# (Qwen/GLM/Kimi/MiMo/MiniMax/DeepSeek). Set OPENCODE_API_KEY env to use these.
# Base URL: https://opencode.ai/zen/go/v1  (OpenAI SDK appends /chat/completions)
# Recommend qwen3.7-max or glm-5.2 for creative Chinese writing (less "DeepSeek 八股").
_OPC_BASE = "https://opencode.ai/zen/go/v1"
_OPC_ENV = "OPENCODE_API_KEY"
_OPC_MAX_OUT = 4000
_OPC_TIMEOUT = 120
_OPC_RETRY = 2
_OPC_BUDGET = 50_000

# WARN: qwen3.7-plus 价格分段 — ≤256K tokens: $0.40/$1.60 in/out;
# >256K tokens: $1.20/$4.80 (3x spike).
# token_hard_limit 目前是声明字段,运行时未强制截断。长会话累积超 256K
# 时单价飙升。需要后续在 prompt assembler 层加截断逻辑,或限制 max_turn_history。
# 短会话(<10 回合)安全;长会话建议用 qwen-max-writer 或定期重置会话。
_register(ModelProfile(
    profile_id="opencode-qwen-plus-writer",
    provider="openai",
    model="qwen3.7-plus",
    base_url=_OPC_BASE,
    timeout_seconds=_OPC_TIMEOUT,
    default_max_tokens=_OPC_MAX_OUT,
    max_retries=_OPC_RETRY,
    api_key_env=_OPC_ENV,
    token_hard_limit=_OPC_BUDGET,  # 声明值,运行时未强制;见上方 WARN
))

_register(ModelProfile(
    profile_id="opencode-qwen-max-writer",
    provider="openai",
    model="qwen3.7-max",
    base_url=_OPC_BASE,
    timeout_seconds=_OPC_TIMEOUT,
    default_max_tokens=_OPC_MAX_OUT,
    max_retries=_OPC_RETRY,
    api_key_env=_OPC_ENV,
    token_hard_limit=_OPC_BUDGET,
))

_register(ModelProfile(
    profile_id="opencode-glm-52-writer",
    provider="openai",
    model="glm-5.2",
    base_url=_OPC_BASE,
    timeout_seconds=_OPC_TIMEOUT,
    default_max_tokens=_OPC_MAX_OUT,
    max_retries=_OPC_RETRY,
    api_key_env=_OPC_ENV,
    token_hard_limit=_OPC_BUDGET,
))

_register(ModelProfile(
    profile_id="opencode-kimi-code-writer",
    provider="openai",
    model="kimi-k2.7-code",
    base_url=_OPC_BASE,
    timeout_seconds=_OPC_TIMEOUT,
    default_max_tokens=_OPC_MAX_OUT,
    max_retries=_OPC_RETRY,
    api_key_env=_OPC_ENV,
    token_hard_limit=_OPC_BUDGET,
))

_register(ModelProfile(
    profile_id="opencode-mimo-pro-writer",
    provider="openai",
    model="mimo-v2.5-pro",
    base_url=_OPC_BASE,
    timeout_seconds=_OPC_TIMEOUT,
    default_max_tokens=_OPC_MAX_OUT,
    max_retries=_OPC_RETRY,
    api_key_env=_OPC_ENV,
    token_hard_limit=_OPC_BUDGET,
))

_register(ModelProfile(
    profile_id="opencode-minimax-m3-writer",
    provider="openai",
    model="minimax-m3",
    base_url=_OPC_BASE,
    timeout_seconds=_OPC_TIMEOUT,
    default_max_tokens=_OPC_MAX_OUT,
    max_retries=_OPC_RETRY,
    api_key_env=_OPC_ENV,
    token_hard_limit=_OPC_BUDGET,
))

# Fake profiles for testing
_register(ModelProfile(
    profile_id="fake-director",
    provider="fake",
    model="fake_director_v1",
    base_url="",
    timeout_seconds=5,
    default_max_tokens=0,
    max_retries=0,
    api_key_env="",
    token_hard_limit=0,
))

_register(ModelProfile(
    profile_id="fake-writer",
    provider="fake",
    model="fake_writer_v1",
    base_url="",
    timeout_seconds=5,
    default_max_tokens=0,
    max_retries=0,
    api_key_env="",
    token_hard_limit=0,
))


class ModelProfileRegistry:
    """Resolve profileId → ModelProfile.  Fail closed on unknown."""

    @staticmethod
    def resolve(profile_id: str) -> ModelProfile:
        """Resolve a profile ID to a ModelProfile.

        Raises ValueError for unknown profile IDs (fail closed).
        """
        profile = _PROFILES.get(profile_id)
        if profile is None:
            known = sorted(_PROFILES.keys())
            raise ValueError(
                f"Unknown model profile: '{profile_id}'. "
                f"Known profiles: {known}"
            )
        return profile

    @staticmethod
    def is_valid(profile_id: str) -> bool:
        """Check if a profile ID is in the whitelist."""
        return profile_id in _PROFILES

    @staticmethod
    def list_profiles() -> list[str]:
        """Return all registered profile IDs."""
        return sorted(_PROFILES.keys())
