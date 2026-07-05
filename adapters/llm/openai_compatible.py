"""OpenAI-compatible LLM adapter.

Supports any OpenAI-compatible API endpoint (Qwen DashScope, GLM BigModel, etc.).
API keys are NEVER stored in code, traces, or the database.
Reads api_key from the env var named in ``api_key_env``.
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


def _message_text(message: Any) -> str:
    """Extract text from an OpenAI-format chat completion message."""
    if message is None:
        return ""
    if isinstance(message, dict):
        return message.get("content", "") or ""
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""


def _provider_usage_from_openai(
    raw_usage: Any,
    model: str,
    output_content: str = "",
) -> ProviderUsage:
    if raw_usage is None:
        return ProviderUsage(
            model=model,
            output_content_chars=len(output_content or ""),
        )
    return ProviderUsage(
        prompt_tokens=_usage_attr(raw_usage, "prompt_tokens"),
        completion_tokens=_usage_attr(raw_usage, "completion_tokens"),
        total_tokens=_usage_attr(raw_usage, "total_tokens"),
        model=model,
        output_content_chars=len(output_content or ""),
    )


# DeepSeek-specific extra_body keys that other providers may not understand.
# We strip these to avoid 400 errors from Qwen/GLM/etc.
_DEEPSEEK_ONLY_KEYS = frozenset({"thinking"})


class OpenAICompatibleAdapter(BaseLlmAdapter):
    """Generic OpenAI-compatible LLM adapter for Qwen, GLM, and similar providers.

    Reads ``api_key`` from the env var named in ``api_key_env``.
    Uses ``base_url`` and ``model`` from the ModelProfile at construction.
    """

    def __init__(
        self,
        model: str = "qwen-max",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env: str = "DASHSCOPE_API_KEY",
        default_max_tokens: int = 4000,
        timeout_seconds: int = 120,
        max_retries: int = 2,
    ):
        self._model = model
        self._base_url = base_url
        self._api_key_env = api_key_env
        self._default_max_tokens = default_max_tokens
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._call_count = 0
        self._total_tokens = 0
        self._receipts: list[ProviderAttemptReceipt] = []
        self._client = None

    def _init_client(self):
        """Lazily initialize the OpenAI SDK client."""
        if self._client is not None:
            return
        api_key = os.environ.get(self._api_key_env, "")
        if not api_key:
            raise RuntimeError(
                f"API key env var '{self._api_key_env}' is not set. "
                f"Cannot initialize adapter for model '{self._model}' at {self._base_url}."
            )
        from openai import OpenAI
        self._client = OpenAI(
            api_key=api_key,
            base_url=self._base_url,
            timeout=self._timeout,
            max_retries=self._max_retries,
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def is_available(self) -> bool:
        api_key = os.environ.get(self._api_key_env, "")
        return bool(api_key)

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
        extra_body: dict[str, Any] | None = None,
        system_prompt: str | None = None,
    ) -> tuple[str, ProviderAttemptReceipt]:
        """Generate text via the OpenAI-compatible chat completions endpoint.

        Signature matches DeepSeekAdapter.generate_text so this adapter is a
        drop-in replacement in RealWriterV2Adapter / RealDirectorV2Adapter.
        DeepSeek-specific extra_body keys (e.g. ``thinking``) are stripped.
        """
        if not max_tokens:
            max_tokens = self._default_max_tokens
        use_model = model or self._model
        request_id = _id("preq", f"{turn_id}:{attempt_id}:{self._call_count}")
        started_at = _now()
        start_time = time.time()

        try:
            self._init_client()

            messages: list[dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            kwargs: dict[str, Any] = {
                "model": use_model,
                "messages": messages,
                "max_tokens": max_tokens,
            }

            # Strip DeepSeek-only keys so Qwen/GLM don't reject the request
            if extra_body:
                filtered = {
                    k: v for k, v in extra_body.items()
                    if k not in _DEEPSEEK_ONLY_KEYS
                }
                if filtered:
                    kwargs["extra_body"] = filtered

            response = self._client.chat.completions.create(**kwargs)

        except Exception as exc:
            failure = ProviderFailure(
                failure_code=FailureCode.CONNECTION_ERROR,
                failure_message=f"OpenAI-compatible API call failed: {exc}",
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
                latency_ms=int((time.time() - start_time) * 1000),
                success=False,
                failure=failure.to_dict(),
            )
            self._receipts.append(receipt)
            return "", receipt

        text = _message_text(
            response.choices[0].message if response.choices else None
        )
        usage = _provider_usage_from_openai(
            getattr(response, "usage", None),
            use_model,
            text,
        )
        self._call_count += 1
        latency_ms = int((time.time() - start_time) * 1000)
        self._total_tokens += usage.total_tokens

        success = bool(text.strip())
        failure_dict: dict[str, Any] = {}
        if not success:
            failure = ProviderFailure(
                failure_code=FailureCode.EMPTY_RESPONSE,
                failure_message="Empty content in response",
            )
            failure_dict = failure.to_dict()

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
            failure=failure_dict,
        )
        self._receipts.append(receipt)
        return text, receipt

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int = 4000,
        provider_role: str = "director",
        workflow_run_id: str = "",
        trace_id: str = "",
        turn_id: str = "",
        attempt_id: str = "",
    ) -> tuple[dict[str, Any] | None, ProviderAttemptReceipt]:
        """Generate structured JSON output using response_format=json_object."""
        if not max_tokens:
            max_tokens = self._default_max_tokens
        use_model = self._model
        request_id = _id("preq", f"{turn_id}:{attempt_id}:{self._call_count}")
        started_at = _now()
        start_time = time.time()

        try:
            self._init_client()

            messages = [
                {
                    "role": "user",
                    "content": f"{prompt}\n\nReturn JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False)}",
                },
            ]
            response = self._client.chat.completions.create(
                model=use_model,
                messages=messages,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )

        except Exception as exc:
            failure = ProviderFailure(
                failure_code=FailureCode.CONNECTION_ERROR,
                failure_message=f"Structured call failed: {exc}",
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
                latency_ms=int((time.time() - start_time) * 1000),
                success=False,
                failure=failure.to_dict(),
            )
            self._receipts.append(receipt)
            return None, receipt

        text = _message_text(
            response.choices[0].message if response.choices else None
        )
        usage = _provider_usage_from_openai(
            getattr(response, "usage", None),
            use_model,
            text,
        )
        self._call_count += 1
        latency_ms = int((time.time() - start_time) * 1000)
        self._total_tokens += usage.total_tokens

        result: dict[str, Any] | None = None
        if text:
            try:
                result = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                result = None

        success = result is not None
        failure_dict: dict[str, Any] = {}
        if not success:
            failure = ProviderFailure(
                failure_code=FailureCode.INVALID_JSON,
                failure_message="Failed to parse JSON from response",
            )
            failure_dict = failure.to_dict()

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
            failure=failure_dict,
        )
        self._receipts.append(receipt)
        return result, receipt