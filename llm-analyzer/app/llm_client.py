from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from .models import TableAnalysisFacts, TableWarningDiagnostics
from .prompt_builder import (
    PROMPT_VERSION,
    RagChunk,
    build_table_warning_prompt,
    build_table_warning_repair_messages,
)
from .response_validator import (
    FALLBACK_DIAGNOSTICS_VERSION,
    build_inconclusive_fallback,
    parse_table_warning_diagnostics,
)


DEFAULT_LLAMA_BASE_URL = "http://llama-server:8080"
DEFAULT_LLAMA_MODEL = "local-open-source-model"
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_OUTPUT_TOKENS = 512
DEFAULT_JSON_RESPONSE_FORMAT = True
DEFAULT_REPAIR_ATTEMPTS = 1
LLAMA_PROVIDER = "llama-server"


class LlamaServerError(RuntimeError):
    pass


class LlamaServerResponseError(LlamaServerError):
    pass


@dataclass(frozen=True)
class LlamaServerConfig:
    base_url: str = DEFAULT_LLAMA_BASE_URL
    model: str = DEFAULT_LLAMA_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    json_response_format: bool = DEFAULT_JSON_RESPONSE_FORMAT
    repair_attempts: int = DEFAULT_REPAIR_ATTEMPTS

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "LlamaServerConfig":
        env = environ or os.environ
        return cls(
            base_url=_env_string(env, "LLAMA_BASE_URL", "LLAMA_SERVER_URL", default=DEFAULT_LLAMA_BASE_URL),
            model=_env_string(env, "LLAMA_MODEL", default=DEFAULT_LLAMA_MODEL),
            temperature=_env_float(env, "LLM_TEMPERATURE", default=DEFAULT_TEMPERATURE),
            timeout_seconds=_env_float(
                env,
                "LLM_TIMEOUT_SECONDS",
                "LLM_REQUEST_TIMEOUT_SECONDS",
                default=DEFAULT_TIMEOUT_SECONDS,
            ),
            max_output_tokens=_env_int(
                env,
                "LLM_MAX_OUTPUT_TOKENS",
                default=DEFAULT_MAX_OUTPUT_TOKENS,
            ),
            json_response_format=_env_bool(
                env,
                "LLM_JSON_RESPONSE_FORMAT",
                "LLM_JSON_RESPONSE_FORMAT_ENABLED",
                default=DEFAULT_JSON_RESPONSE_FORMAT,
            ),
            repair_attempts=_env_int(
                env,
                "LLM_REPAIR_ATTEMPTS",
                default=DEFAULT_REPAIR_ATTEMPTS,
            ),
        )

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/v1/chat/completions"


@dataclass(frozen=True)
class LlamaChatCompletion:
    content: str
    model: str
    raw_response: dict[str, Any]


class LlamaServerClient:
    def __init__(
        self,
        config: LlamaServerConfig | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config or LlamaServerConfig.from_env()
        self._client = http_client or httpx.Client()
        self._owns_client = http_client is None

    def create_chat_completion(
        self,
        messages: Sequence[Mapping[str, str]],
    ) -> LlamaChatCompletion:
        payload = {
            "model": self.config.model,
            "messages": list(messages),
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
        }
        if self.config.json_response_format:
            payload["response_format"] = {"type": "json_object"}

        response = self._client.post(
            self.config.chat_completions_url,
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        try:
            response_payload = response.json()
        except ValueError as exc:
            raise LlamaServerResponseError("llama-server returned non-JSON response") from exc

        content = _extract_message_content(response_payload)
        model = response_payload.get("model") or self.config.model
        if not isinstance(model, str) or not model:
            model = self.config.model

        return LlamaChatCompletion(
            content=content,
            model=model,
            raw_response=response_payload,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "LlamaServerClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def analyze_table_warning_with_llm(
    facts: TableAnalysisFacts,
    *,
    rag_chunks: Sequence[RagChunk | Mapping[str, Any]] | None = None,
    client: LlamaServerClient | None = None,
    config: LlamaServerConfig | None = None,
) -> TableWarningDiagnostics:
    prompt = build_table_warning_prompt(facts, rag_chunks)
    active_config = config or (client.config if client is not None else LlamaServerConfig.from_env())
    active_client = client or LlamaServerClient(active_config)
    owns_client = client is None

    try:
        try:
            completion = active_client.create_chat_completion(prompt.messages)
        except httpx.TimeoutException:
            return build_inconclusive_fallback(
                facts,
                reason="llama-server request timed out.",
                provider=LLAMA_PROVIDER,
                model=active_config.model,
                prompt_version=prompt.prompt_version,
                rag_context_ids=prompt.rag_context_ids,
            )
        except (httpx.HTTPError, LlamaServerError):
            return build_inconclusive_fallback(
                facts,
                reason="llama-server request failed.",
                provider=LLAMA_PROVIDER,
                model=active_config.model,
                prompt_version=prompt.prompt_version,
                rag_context_ids=prompt.rag_context_ids,
            )

        diagnostics = parse_table_warning_diagnostics(
            completion.content,
            facts,
            provider=LLAMA_PROVIDER,
            model=completion.model,
            prompt_version=prompt.prompt_version,
            rag_context_ids=prompt.rag_context_ids,
        )
        if not _should_repair(diagnostics, active_config):
            return diagnostics

        try:
            repair_completion = active_client.create_chat_completion(
                build_table_warning_repair_messages(
                    prompt,
                    invalid_content=completion.content,
                    validation_error=diagnostics.observed_behavior,
                )
            )
        except httpx.TimeoutException:
            return build_inconclusive_fallback(
                facts,
                reason="llama-server repair request timed out.",
                provider=LLAMA_PROVIDER,
                model=active_config.model,
                prompt_version=prompt.prompt_version,
                rag_context_ids=prompt.rag_context_ids,
            )
        except (httpx.HTTPError, LlamaServerError):
            return build_inconclusive_fallback(
                facts,
                reason="llama-server repair request failed.",
                provider=LLAMA_PROVIDER,
                model=active_config.model,
                prompt_version=prompt.prompt_version,
                rag_context_ids=prompt.rag_context_ids,
            )

        return parse_table_warning_diagnostics(
            repair_completion.content,
            facts,
            provider=LLAMA_PROVIDER,
            model=repair_completion.model,
            prompt_version=prompt.prompt_version,
            rag_context_ids=prompt.rag_context_ids,
        )
    finally:
        if owns_client:
            active_client.close()


def _extract_message_content(response_payload: Mapping[str, Any]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LlamaServerResponseError("llama-server response did not include choices")

    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        raise LlamaServerResponseError("llama-server choice was not an object")

    message = first_choice.get("message")
    if isinstance(message, Mapping):
        content = message.get("content")
        if isinstance(content, str):
            return content

    text = first_choice.get("text")
    if isinstance(text, str):
        return text

    raise LlamaServerResponseError("llama-server response did not include message content")


def _env_string(
    env: Mapping[str, str],
    *names: str,
    default: str,
) -> str:
    for name in names:
        value = env.get(name)
        if value and value.strip():
            return value.strip()
    return default


def _env_float(
    env: Mapping[str, str],
    *names: str,
    default: float,
) -> float:
    for name in names:
        value = env.get(name)
        if not value or not value.strip():
            continue
        try:
            return float(value)
        except ValueError:
            continue
    return default


def _env_bool(
    env: Mapping[str, str],
    *names: str,
    default: bool,
) -> bool:
    for name in names:
        value = env.get(name)
        if value is None or not value.strip():
            continue
        return value.strip().lower() in {"1", "true", "yes", "on", "y"}
    return default


def _env_int(
    env: Mapping[str, str],
    *names: str,
    default: int,
) -> int:
    for name in names:
        value = env.get(name)
        if not value or not value.strip():
            continue
        try:
            return int(value)
        except ValueError:
            continue
    return default


def _should_repair(
    diagnostics: TableWarningDiagnostics,
    config: LlamaServerConfig,
) -> bool:
    return (
        config.repair_attempts > 0
        and diagnostics.diagnostics_version == FALLBACK_DIAGNOSTICS_VERSION
    )
