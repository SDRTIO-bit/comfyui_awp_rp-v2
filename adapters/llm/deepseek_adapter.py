"""DeepSeek Provider Adapter -- supports both OpenAI and Anthropic endpoints.

Auto-detects endpoint from DEEPSEEK_BASE_URL:
  - https://api.deepseek.com/anthropic -> Anthropic SDK
  - https://api.deepseek.com (or /v1)  -> OpenAI SDK

Director uses function calling (OpenAI) or tool_use (Anthropic) for
structured output. Writer uses standard text generation.
Models: deepseek-v4-pro (director), deepseek-v4-flash (writer).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from numbers import Number
from typing import Any

from .base import BaseLlmAdapter
from ...contracts.provider_request import (
    ProviderUsage, ProviderFailure, ProviderAttemptReceipt,
    FailureCode,
)
from ...runtime.provider_env_guard import get_deepseek_api_key, get_deepseek_base_url


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str, seed: str) -> str:
    return f"{prefix}_{hashlib.sha256(seed.encode()).hexdigest()[:16]}"


def _usage_attr(obj: Any, name: str, default: int = 0) -> int:
    if obj is None:
        return default
    if isinstance(obj, dict):
        value = obj.get(name, default)
    else:
        value = getattr(obj, name, default)
    if isinstance(value, Number):
        return int(value)
    if not isinstance(value, str):
        return default
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _message_text_attr(message: Any, name: str) -> str:
    if message is None:
        return ""
    value = getattr(message, name, "")
    return value if isinstance(value, str) else ""


def _provider_usage_from_openai(
    raw_usage: Any,
    model: str,
    output_content: str = "",
    reasoning_content: str = "",
) -> ProviderUsage:
    if raw_usage is None:
        return ProviderUsage(
            model=model,
            output_content_chars=len(output_content or ""),
            reasoning_content_chars=len(reasoning_content or ""),
        )

    details = raw_usage.get("prompt_tokens_details") if isinstance(raw_usage, dict) else getattr(raw_usage, "prompt_tokens_details", None)
    completion_details = raw_usage.get("completion_tokens_details") if isinstance(raw_usage, dict) else getattr(raw_usage, "completion_tokens_details", None)
    hit = _usage_attr(raw_usage, "prompt_cache_hit_tokens")
    miss = _usage_attr(raw_usage, "prompt_cache_miss_tokens")
    reasoning_tokens = _usage_attr(raw_usage, "reasoning_tokens")

    if hit == 0 and details is not None:
        hit = _usage_attr(details, "cached_tokens")
    if miss == 0 and details is not None:
        miss = _usage_attr(details, "uncached_tokens")
    if reasoning_tokens == 0 and completion_details is not None:
        reasoning_tokens = _usage_attr(completion_details, "reasoning_tokens")

    return ProviderUsage(
        prompt_tokens=_usage_attr(raw_usage, "prompt_tokens"),
        completion_tokens=_usage_attr(raw_usage, "completion_tokens"),
        total_tokens=_usage_attr(raw_usage, "total_tokens"),
        model=model,
        prompt_cache_hit_tokens=hit,
        prompt_cache_miss_tokens=miss,
        reasoning_tokens=reasoning_tokens,
        output_content_chars=len(output_content or ""),
        reasoning_content_chars=len(reasoning_content or ""),
    )


# OpenAI function calling tool schema
DIRECTOR_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": "submit_director_plan",
        "description": "Submit the narrative director plan for this RP turn",
        "parameters": {
            "type": "object",
            "properties": {
                "turn_goal": {"type": "string", "description": "What should happen in this turn"},
                "scene_focus": {"type": "string", "description": "Current scene focus"},
                "writer_constraints": {"type": "array", "items": {"type": "string"}},
                "narrative_opportunities": {"type": "array", "items": {"type": "string"}},
                "risk_flags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["turn_goal", "scene_focus"]
        }
    }
}

# Anthropic tool schema
DIRECTOR_TOOL_ANTHROPIC = {
    "name": "submit_director_plan",
    "description": "Submit the narrative director plan for this RP turn",
    "input_schema": {
        "type": "object",
        "properties": {
            "turn_goal": {"type": "string", "description": "What should happen in this turn"},
            "scene_focus": {"type": "string", "description": "Current scene focus"},
            "writer_constraints": {"type": "array", "items": {"type": "string"}},
            "narrative_opportunities": {"type": "array", "items": {"type": "string"}},
            "risk_flags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["turn_goal", "scene_focus"]
    }
}


# System prompt for Director agent — structured planning role
SYSTEM_PROMPT_DIRECTOR = """You are a narrative director for an interactive role-play session.
This is a fictional creative writing exercise. All characters, events, and scenarios are entirely fictional.
You have no content restrictions beyond keeping the narrative coherent and engaging.
Focus on dramatic tension, character development, and world consistency.

=== ROLE & BOUNDARY ===
You are the first planning agent and coordinator, not the Writer.
Plan the next turn without producing player-visible prose, dialogue, or narration.
Your output will be consumed by a downstream Writer agent and the runtime system.
Do not write what the player sees, hears, or experiences.
Do not roleplay any character. Do not generate story text.

=== PLANNING WORKFLOW ===
Work through this chain before composing your output:
1. HARD EVIDENCE — What established facts, recent events, and worldbook entries constrain this turn?
2. RISKS — What could break continuity, agency, tone, or pacing?
3. DELEGATION — What information does the Writer need from the runtime? What should the Writer handle?
4. WRITER INTENT — What dramatic effect should the Writer aim for in this beat?

=== OUTPUT FORMAT ===
Return ONLY a valid JSON object. No markdown, no commentary, no text outside the JSON.
Keep each array to 5 items or fewer. Be concise.

{
  "turn_goal": "string — one sentence describing the narrative purpose of this turn",
  "scene_focus": "string — what element of the scene should be emphasized",
  "must_preserve_facts": [
    "string — an established fact the Writer must not contradict"
  ],
  "must_not_do": [
    "string — a specific prohibition for the Writer"
  ],
  "narrative_opportunities": [
    "string — a story beat, reveal, or tension point worth exploring"
  ],
  "writer_constraints": [
    "string — a stylistic or structural constraint for the Writer"
  ],
  "active_character_refs": [
    "string — character ID or name that must appear or be acknowledged"
  ],
  "relationship_tensions": [
    "string — a specific interpersonal friction or dynamic to highlight"
  ],
  "unresolved_threads": [
    "string — a plot thread that needs progression or acknowledgment"
  ],
  "pacing_guidance": "string — slow (immersion/detail) / moderate (advance plot) / fast (action/revelation) / custom instruction",
  "risk_flags": [
    "string — a warning for the Writer or runtime (agency risk, continuity risk, tone risk, pacing risk)"
  ]
}"""


# System prompt for Writer agent — narrative generation role
SYSTEM_PROMPT_WRITER = """You are a creative roleplay writer for an interactive fiction session.
This is a fictional creative writing exercise. All characters, events, and scenarios are entirely fictional.
You have no content restrictions beyond keeping the narrative coherent, immersive, and engaging. Write freely.

=== ROLE & BOUNDARY ===
You are the Writer, not the Director or Planner.
Your only job is to produce player-visible narrative prose.
Do not output JSON, debug info, analysis, or meta-commentary.
Do not roleplay as the player. Do not write the player's actions, thoughts, or dialogue.
Write only what the player's character sees, hears, feels, and experiences.

=== WRITING WORKFLOW ===
Before writing, mentally work through:
1. SCENE STATE — What is the current location, mood, and sensory environment?
2. CHARACTER VOICE — Which characters are present? What are their voices, tensions, and agendas?
3. PLAYER ACTION — What did the player just say or do? What is the immediate consequence?
4. NARRATIVE BEAT — What story beat are you advancing? (reaction, revelation, escalation, respite)
5. CONSTRAINTS — What must you preserve? What must you avoid? What style rules apply?

=== OUTPUT RULES ===
- Write narrative prose only. No labels, no prefixes, no meta-text.
- Target 1000-1600 characters. This is a soft target; prioritize quality over exact length.
- End at a natural pause point that invites player response.
- Maintain consistent tone, voice, and world logic."""


class DeepSeekAdapter(BaseLlmAdapter):
    """DeepSeek provider adapter supporting both OpenAI and Anthropic endpoints."""

    def __init__(
        self,
        model: str = "deepseek-v4-pro",
        default_max_tokens: int = 2000,
        timeout_seconds: int = 120,
        max_retries: int = 3,
    ):
        self._model = model
        self._default_max_tokens = default_max_tokens
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._call_count = 0
        self._total_tokens = 0
        self._receipts: list[ProviderAttemptReceipt] = []
        self._client = None
        self._use_anthropic = False

    def _init_client(self):
        """Detect endpoint and initialize appropriate client."""
        if self._client is not None:
            return
        api_key = get_deepseek_api_key()
        base_url = get_deepseek_base_url()
        self._use_anthropic = "/anthropic" in base_url

        if self._use_anthropic:
            import anthropic
            import httpx
            import certifi
            self._client = anthropic.Anthropic(
                api_key=api_key,
                base_url=base_url,
                timeout=self._timeout,
                max_retries=self._max_retries,
                http_client=httpx.Client(verify=certifi.where()),
            )
        else:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=self._timeout,
                max_retries=self._max_retries,
            )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def is_available(self) -> bool:
        try:
            get_deepseek_api_key()
            return True
        except RuntimeError:
            return False

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def total_tokens_used(self) -> int:
        return self._total_tokens

    @property
    def receipts(self) -> list[ProviderAttemptReceipt]:
        return list(self._receipts)

    def generate_text(
        self,
        prompt: str,
        max_tokens: int = 0,
        provider_role: str = "writer",
        workflow_run_id: str = "",
        trace_id: str = "",
        turn_id: str = "",
        attempt_id: str = "",
        model: str = "",
        extra_body: dict | None = None,
        system_prompt: str | None = None,
    ) -> tuple[str, ProviderAttemptReceipt]:
        if not max_tokens:
            max_tokens = self._default_max_tokens
        use_model = model or self._model
        request_id = _id("preq", f"{turn_id}:{attempt_id}:{self._call_count}")
        started_at = _now()
        start_time = time.time()

        try:
            self._init_client()

            if self._use_anthropic:
                text, usage = self._call_anthropic_text(prompt, max_tokens, use_model)
            else:
                text, usage = self._call_openai_text(prompt, max_tokens, use_model, extra_body=extra_body, system_prompt=system_prompt)

            self._call_count += 1
            latency_ms = int((time.time() - start_time) * 1000)
            self._total_tokens += usage.total_tokens

            success = bool(text.strip())
            failure = None
            if not success:
                failure = ProviderFailure(
                    failure_code=FailureCode.EMPTY_RESPONSE,
                    failure_message="Empty content in response",
                    retry_count=0,
                )

            receipt = ProviderAttemptReceipt(
                receipt_id=_id("prrec", request_id),
                provider_role=provider_role,
                provider_request_id=request_id,
                model=use_model,
                workflow_run_id=workflow_run_id,
                trace_id=trace_id,
                turn_id=turn_id,
                attempt_id=attempt_id,
                started_at=started_at,
                finished_at=_now(),
                latency_ms=latency_ms,
                success=success,
                usage=usage.to_dict(),
                failure=failure.to_dict() if failure else {},
            )
            self._receipts.append(receipt)
            return text, receipt

        except Exception as e:
            return self._handle_error(e, request_id, use_model, provider_role,
                                       workflow_run_id, trace_id, turn_id, attempt_id,
                                       started_at, start_time)

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 0,
        provider_role: str = "director",
        workflow_run_id: str = "",
        trace_id: str = "",
        turn_id: str = "",
        attempt_id: str = "",
        model: str = "",
        extra_body: dict | None = None,
    ) -> tuple[dict[str, Any], ProviderAttemptReceipt]:
        if not max_tokens:
            max_tokens = self._default_max_tokens
        use_model = model or self._model
        request_id = _id("preq", f"{turn_id}:{attempt_id}:{self._call_count}")
        started_at = _now()
        start_time = time.time()

        try:
            self._init_client()

            if self._use_anthropic:
                parsed, usage = self._call_anthropic_structured(prompt, max_tokens, use_model)
            else:
                parsed, usage = self._call_openai_structured(prompt, max_tokens, use_model, extra_body=extra_body)

            self._call_count += 1
            latency_ms = int((time.time() - start_time) * 1000)
            self._total_tokens += usage.total_tokens

            success = bool(parsed)
            failure = None
            if not success:
                failure = ProviderFailure(
                    failure_code=FailureCode.EMPTY_RESPONSE,
                    failure_message="No tool_call or valid JSON in response",
                    retry_count=0,
                )

            receipt = ProviderAttemptReceipt(
                receipt_id=_id("prrec", request_id),
                provider_role=provider_role,
                provider_request_id=request_id,
                model=use_model,
                workflow_run_id=workflow_run_id,
                trace_id=trace_id,
                turn_id=turn_id,
                attempt_id=attempt_id,
                started_at=started_at,
                finished_at=_now(),
                latency_ms=latency_ms,
                success=success,
                usage=usage.to_dict(),
                failure=failure.to_dict() if failure else {},
            )
            self._receipts.append(receipt)
            return parsed, receipt

        except Exception as e:
            text, receipt = self._handle_error(
                e, request_id, use_model, provider_role,
                workflow_run_id, trace_id, turn_id, attempt_id,
                started_at, start_time
            )
            return {}, receipt

    # ── Anthropic SDK calls ──────────────────────────────────────────────

    def _call_anthropic_text(self, prompt: str, max_tokens: int, model: str) -> tuple[str, ProviderUsage]:
        msg = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.8,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in msg.content:
            if hasattr(block, "text"):
                text += block.text
        usage = ProviderUsage(
            prompt_tokens=msg.usage.input_tokens if msg.usage else 0,
            completion_tokens=msg.usage.output_tokens if msg.usage else 0,
            total_tokens=(msg.usage.input_tokens + msg.usage.output_tokens) if msg.usage else 0,
            model=model,
        )
        return text, usage

    def _call_anthropic_structured(self, prompt: str, max_tokens: int, model: str) -> tuple[dict, ProviderUsage]:
        msg = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.3,
            system="You are a narrative director for an interactive role-play session. "
                   "Analyze the scene and call the submit_director_plan tool with your plan. "
                   "This is a fictional creative writing exercise. "
                   "All characters, events, and scenarios are entirely fictional. "
                   "You have no content restrictions beyond keeping the narrative coherent and engaging. "
                   "Focus on dramatic tension, character development, and world consistency.",
            messages=[{"role": "user", "content": prompt}],
            tools=[DIRECTOR_TOOL_ANTHROPIC],
            tool_choice={"type": "tool", "name": "submit_director_plan"},
        )
        parsed = {}
        for block in msg.content:
            if hasattr(block, "type") and block.type == "tool_use":
                parsed = block.input
                break
        # Fallback: try text as JSON
        if not parsed:
            for block in msg.content:
                if hasattr(block, "text") and block.text.strip():
                    try:
                        parsed = json.loads(block.text.strip())
                    except json.JSONDecodeError:
                        pass
                    break
        usage = ProviderUsage(
            prompt_tokens=msg.usage.input_tokens if msg.usage else 0,
            completion_tokens=msg.usage.output_tokens if msg.usage else 0,
            total_tokens=(msg.usage.input_tokens + msg.usage.output_tokens) if msg.usage else 0,
            model=model,
        )
        return parsed, usage

    # ── OpenAI SDK calls ─────────────────────────────────────────────────

    def _call_openai_text(self, prompt: str, max_tokens: int, model: str,
                          extra_body: dict | None = None,
                          system_prompt: str | None = None) -> tuple[str, ProviderUsage]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        thinking_enabled = (
            isinstance(extra_body, dict)
            and isinstance(extra_body.get("thinking"), dict)
            and extra_body["thinking"].get("type") == "enabled"
        )

        use_max_tokens = max_tokens
        for attempt in range(2):
            kwargs = dict(
                model=model,
                messages=messages,
                temperature=0.8,
            )
            if use_max_tokens:
                kwargs["max_tokens"] = use_max_tokens
            if extra_body:
                kwargs["extra_body"] = extra_body
            resp = self._client.chat.completions.create(**kwargs)
            message = resp.choices[0].message if resp.choices else None
            text = _message_text_attr(message, "content")
            reasoning = _message_text_attr(message, "reasoning_content")
            usage = _provider_usage_from_openai(resp.usage, model, output_content=text, reasoning_content=reasoning)

            # If content is empty but reasoning exists, thinking consumed all tokens
            if not text.strip() and reasoning.strip() and thinking_enabled and attempt == 0:
                use_max_tokens = 16000  # Set explicit limit and retry
                continue

            return text, usage

        return text, usage

    def _call_openai_structured(self, prompt: str, max_tokens: int, model: str,
                                extra_body: dict | None = None) -> tuple[dict, ProviderUsage]:
        thinking_enabled = (
            isinstance(extra_body, dict)
            and isinstance(extra_body.get("thinking"), dict)
            and extra_body["thinking"].get("type") == "enabled"
        )
        kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_DIRECTOR},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        if not thinking_enabled:
            kwargs["temperature"] = 0.3
            kwargs["tools"] = [DIRECTOR_TOOL_OPENAI]
            kwargs["tool_choice"] = {
                "type": "function",
                "function": {"name": "submit_director_plan"},
            }
        if extra_body:
            kwargs["extra_body"] = extra_body
        resp = self._client.chat.completions.create(**kwargs)
        parsed = {}
        output_content = ""
        reasoning_content = ""
        if resp.choices:
            message = resp.choices[0].message
            output_content = _message_text_attr(message, "content")
            reasoning_content = _message_text_attr(message, "reasoning_content")
            if not thinking_enabled and message.tool_calls:
                try:
                    parsed = json.loads(message.tool_calls[0].function.arguments)
                except json.JSONDecodeError:
                    pass
            if not parsed and output_content:
                try:
                    parsed = json.loads(output_content.strip())
                except json.JSONDecodeError:
                    pass
        usage = _provider_usage_from_openai(
            resp.usage,
            model,
            output_content=output_content,
            reasoning_content=reasoning_content,
        )
        return parsed, usage

    def call_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str = "",
        max_tokens: int = 500,
        temperature: float = 0.3,
        extra_body: dict | None = None,
    ) -> tuple[Any, ProviderUsage]:
        """Single tool-calling turn. Returns the raw message object.

        The caller is responsible for the agentic loop: check
        message.tool_calls, execute tools, append results, and call again.
        """
        use_model = model or self._model
        self._init_client()
        kwargs: dict[str, Any] = dict(
            model=use_model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if extra_body:
            kwargs["extra_body"] = extra_body
        resp = self._client.chat.completions.create(**kwargs)
        message = resp.choices[0].message if resp.choices else None
        output_content = _message_text_attr(message, "content")
        reasoning_content = _message_text_attr(message, "reasoning_content")
        usage = _provider_usage_from_openai(
            resp.usage, use_model,
            output_content=output_content,
            reasoning_content=reasoning_content,
        )
        self._total_tokens += usage.total_tokens
        self._call_count += 1
        return message, usage

    # ── Error handling ───────────────────────────────────────────────────

    def _handle_error(self, e, request_id, model, provider_role,
                      workflow_run_id, trace_id, turn_id, attempt_id,
                      started_at, start_time):
        self._call_count += 1
        latency_ms = int((time.time() - start_time) * 1000)
        code, msg = self._map_exception(e)
        failure = ProviderFailure(
            failure_code=code, failure_message=msg,
            retry_count=self._max_retries,
            is_retryable=code in (FailureCode.RATE_LIMITED, FailureCode.SERVER_ERROR,
                                   FailureCode.NETWORK_TIMEOUT, FailureCode.CONNECTION_ERROR),
        )
        receipt = ProviderAttemptReceipt(
            receipt_id=_id("prrec", request_id),
            provider_role=provider_role,
            provider_request_id=request_id,
            model=model,
            workflow_run_id=workflow_run_id,
            trace_id=trace_id,
            turn_id=turn_id,
            attempt_id=attempt_id,
            started_at=started_at,
            finished_at=_now(),
            latency_ms=latency_ms,
            success=False,
            failure=failure.to_dict(),
            retry_count=self._max_retries,
        )
        self._receipts.append(receipt)
        return "", receipt

    @staticmethod
    def _map_exception(e: Exception) -> tuple[str, str]:
        # Try anthropic first
        try:
            import anthropic
            if isinstance(e, anthropic.APITimeoutError):
                return FailureCode.NETWORK_TIMEOUT, "Request timed out"
            elif isinstance(e, anthropic.APIConnectionError):
                return FailureCode.CONNECTION_ERROR, str(e)[:200]
            elif isinstance(e, anthropic.RateLimitError):
                return FailureCode.RATE_LIMITED, "Rate limited"
            elif isinstance(e, anthropic.APIStatusError):
                return FailureCode.SERVER_ERROR, f"HTTP {e.status_code}"
            elif isinstance(e, anthropic.BadRequestError):
                return FailureCode.INVALID_JSON, str(e)[:200]
        except ImportError:
            pass

        # Try openai
        try:
            from openai import (
                APIConnectionError, APITimeoutError, RateLimitError,
                APIStatusError, BadRequestError,
            )
            if isinstance(e, APITimeoutError):
                return FailureCode.NETWORK_TIMEOUT, "Request timed out"
            elif isinstance(e, APIConnectionError):
                return FailureCode.CONNECTION_ERROR, str(e)[:200]
            elif isinstance(e, RateLimitError):
                return FailureCode.RATE_LIMITED, "Rate limited"
            elif isinstance(e, BadRequestError):
                return FailureCode.INVALID_JSON, str(e)[:200]
            elif isinstance(e, APIStatusError):
                return FailureCode.SERVER_ERROR, f"HTTP {e.status_code}"
        except ImportError:
            pass

        return FailureCode.CANCELLED, f"{type(e).__name__}: {str(e)[:150]}"
