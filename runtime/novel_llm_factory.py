"""Novel LLM Factory —— shared DeepSeek adapter instances for novel mode.

Provides configured DeepSeekAdapter instances for each novel agent role.
Thinking is controlled via extra_body, not ModelProfile.

max_tokens 与计划文档一致（plan 1040-1047 行）。之前误设为 0 会触发
DeepSeekAdapter 的 "thinking 吃光 content 后 max_tokens=16000 重试" 分支，
单次调用烧 1-3 万 token。务必保持显式上界。
"""

from __future__ import annotations

from typing import Any

from ..adapters.llm.deepseek_adapter import DeepSeekAdapter

# Thinking configurations per agent role
THINKING_HIGH = {"thinking": {"type": "enabled", "reasoning_effort": "high"}}
THINKING_MEDIUM = {"thinking": {"type": "enabled", "reasoning_effort": "medium"}}
THINKING_LOW = {"thinking": {"type": "enabled", "reasoning_effort": "low"}}
THINKING_DISABLED = {"thinking": {"type": "disabled"}}

# Model configurations per agent role
# max_tokens 对齐 plan 表格，避免无限消耗。
ROLE_CONFIGS = {
    "director":          {"model": "deepseek-v4-pro",   "max_tokens": 8000, "thinking": THINKING_HIGH},
    "architect":         {"model": "deepseek-v4-pro",   "max_tokens": 6000, "thinking": THINKING_HIGH},
    "writer":            {"model": "deepseek-v4-pro",   "max_tokens": 4000, "thinking": THINKING_MEDIUM},
    "continuity_checker": {"model": "deepseek-v4-flash", "max_tokens": 4000, "thinking": THINKING_DISABLED},
    "style_cleaner":     {"model": "deepseek-v4-flash", "max_tokens": 2000, "thinking": THINKING_DISABLED},
    "ledger_curator":    {"model": "deepseek-v4-flash", "max_tokens": 4000, "thinking": THINKING_DISABLED},
}


class NovelLLMFactory:
    """Factory for creating LLM adapter instances for novel agents.

    Provider selection (env-driven, default = deepseek to preserve tests):
      NOVEL_LLM_PROVIDER=opencode  -> OpenAICompatibleAdapter @ OpenCode Zen gateway
      NOVEL_LLM_PROVIDER=deepseek  -> DeepSeekAdapter (default)
      unset or other              -> DeepSeekAdapter (default)
    """

    _instance: NovelLLMFactory | None = None
    _adapters: dict[str, Any] = {}

    @classmethod
    def get_instance(cls) -> NovelLLMFactory:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _provider_choice() -> str:
        import os
        return (os.environ.get("NOVEL_LLM_PROVIDER") or "deepseek").lower()

    def get_adapter(self, role: str):
        """Get or create an adapter for the given role.

        Provider is chosen from env NOVEL_LLM_PROVIDER. DeepSeek-only
        extra_body keys (e.g. ``thinking``) are stripped by OpenAICompatibleAdapter.
        """
        if role not in self._adapters:
            config = ROLE_CONFIGS.get(role, ROLE_CONFIGS["writer"])
            provider = self._provider_choice()

            if provider == "mimo":
                from ..adapters.llm.openai_compatible import OpenAICompatibleAdapter
                import os
                self._adapters[role] = OpenAICompatibleAdapter(
                    model=os.environ.get("NOVEL_LLM_MODEL", "mimo-v2.5-pro"),
                    base_url=os.environ.get(
                        "NOVEL_LLM_BASE_URL",
                        "https://token-plan-cn.xiaomimimo.com/v1",
                    ),
                    api_key_env=os.environ.get(
                        "NOVEL_LLM_API_KEY_ENV", "MIMO_API_KEY",
                    ),
                    default_max_tokens=config["max_tokens"],
                    timeout_seconds=180,
                    max_retries=2,
                )
            elif provider == "opencode":
                from ..adapters.llm.openai_compatible import OpenAICompatibleAdapter
                import os
                self._adapters[role] = OpenAICompatibleAdapter(
                    model=config["model"],
                    base_url=os.environ.get(
                        "NOVEL_LLM_BASE_URL",
                        "https://opencode.ai/zen/go/v1",
                    ),
                    api_key_env=os.environ.get(
                        "NOVEL_LLM_API_KEY_ENV", "OPENCODE_API_KEY",
                    ),
                    default_max_tokens=config["max_tokens"],
                    timeout_seconds=120,
                    max_retries=2,
                )
            else:
                self._adapters[role] = DeepSeekAdapter(
                    model=config["model"],
                    default_max_tokens=config["max_tokens"],
                )
        return self._adapters[role]

    def _role_config(self, role: str) -> dict[str, Any]:
        """Return the merged role config, applying OpenCode model overrides when
        NOVEL_LLM_PROVIDER=opencode is set.

        Default behavior (no env or provider=deepseek) returns ROLE_CONFIGS
        unchanged so all existing tests pass.
        """
        base = ROLE_CONFIGS.get(role, ROLE_CONFIGS["writer"])
        if self._provider_choice() not in ("opencode", "mimo"):
            return base

        provider = self._provider_choice()
        import os

        if provider == "mimo":
            default_map = {
                "director":           "mimo-v2.5-pro",
                "architect":          "mimo-v2.5-pro",
                "writer":             "mimo-v2.5-pro",
                "continuity_checker": "mimo-v2.5-pro",
                "style_cleaner":      "mimo-v2.5-pro",
                "ledger_curator":     "mimo-v2.5-pro",
            }
            model_id = os.environ.get(f"NOVEL_LLM_MODEL_{role.upper()}", default_map.get(role, "mimo-v2.5-pro"))
            return {**base, "model": model_id}

        # Override model names with OpenCode-available ids.
        # 2026-07-05: max 长程一致性暴露问题（8K 输出窗内同句重复、48h→72h 自相矛盾），
        # 且单次调用价格是 plus 的数倍。短篇/中篇 plus 实测更稳。
        # max 仍可通过 NOVEL_LLM_MODEL_WRITER=qwen3.7-max 显式覆盖。
        default_map = {
            "director":           "qwen3.7-plus",
            "architect":          "qwen3.7-plus",
            "writer":             "qwen3.7-plus",
            "continuity_checker": "qwen3.7-plus",
            "style_cleaner":      "qwen3.7-plus",
            "ledger_curator":     "qwen3.7-plus",
        }
        model_id = os.environ.get(f"NOVEL_LLM_MODEL_{role.upper()}", default_map.get(role, "qwen3.7-max"))
        return {**base, "model": model_id}

    def get_thinking_config(self, role: str) -> dict[str, Any]:
        config = self._role_config(role)
        return config["thinking"]

    def get_model(self, role: str) -> str:
        config = self._role_config(role)
        return config["model"]

    def get_max_tokens(self, role: str) -> int:
        config = self._role_config(role)
        return config["max_tokens"]

    def is_available(self) -> bool:
        try:
            adapter = self.get_adapter("writer")
            return adapter.is_available
        except Exception:
            return False

    def reset(self) -> None:
        """Reset all adapters (for testing)."""
        self._adapters.clear()