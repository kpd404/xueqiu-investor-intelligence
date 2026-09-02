import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from ai.extractors.base import OpinionExtractor
from config import Settings, get_settings
from contracts import (
    OPINION_ANALYSIS_POLICY_VERSION,
    OPINION_EXTRACTION_PROMPT_VERSION,
    OPINION_EXTRACTION_SCHEMA_VERSION,
    AnalysisSpec,
    CurrentAuthorEventView,
    LLMProviderConfig,
    LLMProviderError,
    OpinionExtractionResult,
    ProviderErrorCode,
    StructuredOutputMode,
)

PROMPT_VERSION = OPINION_EXTRACTION_PROMPT_VERSION
SCHEMA_VERSION = OPINION_EXTRACTION_SCHEMA_VERSION
PROMPT_RESOURCE = Path("prompts/opinion_extraction/v5.md")


class ResponsesResource(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class OpenAICompatibleClient(Protocol):
    responses: ResponsesResource


class OpenAICompatibleOpinionExtractor(OpinionExtractor):
    """Provider-neutral adapter for Responses + JSON Schema compatible endpoints."""

    def __init__(
        self,
        config: LLMProviderConfig,
        *,
        client: OpenAICompatibleClient | None = None,
        analysis_spec: AnalysisSpec | None = None,
        prompt_text: str | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._analysis_spec = analysis_spec or AnalysisSpec.for_provider(
            provider_id=config.provider_id,
            model_version=config.model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            analysis_policy_version=OPINION_ANALYSIS_POLICY_VERSION,
        )
        self._prompt_text = prompt_text if prompt_text is not None else self._load_prompt()

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "OpenAICompatibleOpinionExtractor":
        try:
            resolved = settings or get_settings()
            values = {
                "provider_id": resolved.llm_provider_id,
                "base_url": resolved.llm_base_url,
                "api_key": resolved.llm_api_key,
                "model": resolved.llm_model,
            }
            for field, value in values.items():
                if not isinstance(value, str) or not value.strip():
                    raise cls._configuration_error(f"LLM_{field.upper()} is not configured")
            config = LLMProviderConfig(
                provider_id=values["provider_id"],
                base_url=values["base_url"],
                api_key=values["api_key"],
                model=values["model"],
                api_style=resolved.llm_api_style,
                structured_output=resolved.llm_structured_output,
                timeout_seconds=resolved.llm_timeout_seconds,
                max_retries=resolved.llm_max_retries,
            )
        except LLMProviderError:
            raise
        except AttributeError as exc:
            raise cls._configuration_error("LLM provider settings are unavailable") from exc
        except ValidationError as exc:
            raise cls._configuration_error("invalid LLM provider configuration") from exc
        return cls(config)

    @property
    def provider_id(self) -> str:
        return self._config.provider_id

    @property
    def config(self) -> LLMProviderConfig:
        return self._config

    @property
    def analysis_spec(self) -> AnalysisSpec:
        return self._analysis_spec

    async def extract(self, event: CurrentAuthorEventView) -> OpinionExtractionResult:
        request_input = self._request_input(event)
        try:
            client = self._client or self._build_client()
            response = await asyncio.to_thread(
                client.responses.create,
                model=self._config.model,
                instructions=self._prompt_text,
                input=request_input,
                text=self._structured_output_config(),
            )
        except LLMProviderError:
            raise
        except Exception as exc:
            raise self._map_sdk_error(exc) from exc

        self._validate_response_status(response)
        parsed = self._parse_structured_response(response)
        metadata = self._provider_metadata(response)
        return parsed.model_copy(
            update={
                "model_version": self._analysis_spec.model_version,
                "analysis_spec": self._analysis_spec,
                "provider_metadata": metadata,
            }
        )

    def _build_client(self) -> OpenAICompatibleClient:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise self._configuration_error(
                "OpenAI-compatible SDK is not installed", provider=self._config.provider_id
            ) from exc
        try:
            client = OpenAI(
                api_key=self._config.api_key,
                base_url=self._config.base_url,
                timeout=self._config.timeout_seconds,
                max_retries=self._config.max_retries,
            )
        except Exception as exc:
            raise self._map_sdk_error(exc) from exc
        if not hasattr(client, "responses") or not hasattr(client.responses, "create"):
            raise self._configuration_error(
                "installed SDK lacks the Responses API create operation",
                provider=self._config.provider_id,
            )
        return client

    @staticmethod
    def _load_prompt() -> str:
        prompt_path = Path(__file__).resolve().parents[2] / PROMPT_RESOURCE
        try:
            prompt = prompt_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LLMProviderError(
                "opinion extraction prompt is unavailable",
                code=ProviderErrorCode.CONFIGURATION_ERROR,
                retryable=False,
                provider="unknown",
            ) from exc
        if not prompt.strip():
            raise LLMProviderError(
                "opinion extraction prompt is empty",
                code=ProviderErrorCode.CONFIGURATION_ERROR,
                retryable=False,
                provider="unknown",
            )
        return prompt

    @staticmethod
    def _request_input(event: CurrentAuthorEventView) -> str:
        return (
            "event_type="
            + event.event_type.value
            + "\nsource="
            + event.source
            + "\npublished_time="
            + event.published_time.isoformat()
            + "\ncontent=\n"
            + event.content
        )

    @classmethod
    def _structured_output_config(cls) -> dict[str, object]:
        schema = OpinionExtractionResult.model_json_schema()
        cls._make_strict_schema(schema)
        return {
            "format": {
                "type": StructuredOutputMode.JSON_SCHEMA.value,
                "name": "OpinionExtractionResult",
                "schema": schema,
                "strict": True,
            }
        }

    @staticmethod
    def _make_strict_schema(node: object) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            for value in node.values():
                OpenAICompatibleOpinionExtractor._make_strict_schema(value)
        elif isinstance(node, list):
            for value in node:
                OpenAICompatibleOpinionExtractor._make_strict_schema(value)

    def _validate_response_status(self, response: Any) -> None:
        status = str(self._value(response, "status") or "completed").lower()
        if status == "completed":
            pass
        elif status == "failed":
            error = self._value(response, "error")
            message = self._value(error, "message") or "provider response failed"
            raise LLMProviderError(
                self._safe_error_message(
                    RuntimeError(str(message)), ProviderErrorCode.PROVIDER_UNAVAILABLE
                ),
                code=ProviderErrorCode.PROVIDER_UNAVAILABLE,
                retryable=True,
                provider=self._config.provider_id,
            )
        else:
            raise LLMProviderError(
                f"provider response was {status}",
                code=ProviderErrorCode.INCOMPLETE_RESPONSE,
                retryable=False,
                provider=self._config.provider_id,
            )

        for item in self._value(response, "output") or []:
            for content in self._value(item, "content") or []:
                content_type = self._value(content, "type")
                if content_type in {"refusal", "output_refusal"}:
                    raise LLMProviderError(
                        "provider refused the extraction request",
                        code=ProviderErrorCode.REFUSED,
                        retryable=False,
                        provider=self._config.provider_id,
                    )

    def _parse_structured_response(self, response: Any) -> OpinionExtractionResult:
        output_text = self._output_text(response)
        if not output_text:
            raise self._invalid_output("provider returned no structured output")
        try:
            # The response is required to use text.format.type=json_schema.
            # This is not a free-text fallback.
            payload = json.loads(output_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise self._invalid_output("provider returned invalid JSON Schema output") from exc
        try:
            return OpinionExtractionResult.model_validate(payload)
        except ValidationError as exc:
            raise self._invalid_output(
                "provider output failed Opinion contract validation"
            ) from exc

    @classmethod
    def _output_text(cls, response: Any) -> str | None:
        fragments: list[str] = []
        for item in cls._value(response, "output") or []:
            for content in cls._value(item, "content") or []:
                if cls._value(content, "type") == "output_text":
                    text = cls._value(content, "text")
                    if isinstance(text, str):
                        fragments.append(text)
        if fragments:
            return "\n".join(fragments)
        output_text = cls._value(response, "output_text")
        return output_text if isinstance(output_text, str) else None

    def _provider_metadata(self, response: Any) -> dict[str, object]:
        usage = self._value(response, "usage")
        return {
            "provider": self._config.provider_id,
            "base_url": self._config.base_url,
            "provider_response_id": self._value(response, "id"),
            "model": self._value(response, "model") or self._config.model,
            "input_tokens": self._value(usage, "input_tokens"),
            "output_tokens": self._value(usage, "output_tokens"),
            "total_tokens": self._value(usage, "total_tokens"),
        }

    @staticmethod
    def _value(source: object, key: str) -> object:
        if isinstance(source, Mapping):
            return source.get(key)
        return getattr(source, key, None)

    def _invalid_output(self, message: str) -> LLMProviderError:
        return LLMProviderError(
            message,
            code=ProviderErrorCode.INVALID_STRUCTURED_OUTPUT,
            retryable=False,
            provider=self._config.provider_id,
        )

    def _map_sdk_error(self, error: Exception) -> LLMProviderError:
        name = type(error).__name__.lower()
        status_code = getattr(error, "status_code", None)
        if "authentication" in name or status_code in {401, 403}:
            code, retryable = ProviderErrorCode.AUTHENTICATION_ERROR, False
        elif "ratelimit" in name or status_code == 429:
            code, retryable = ProviderErrorCode.RATE_LIMITED, True
        elif "timeout" in name:
            code, retryable = ProviderErrorCode.TIMEOUT, True
        elif "responsevalidation" in name or name in {"validationerror", "pydanticvalidationerror"}:
            code, retryable = ProviderErrorCode.INVALID_STRUCTURED_OUTPUT, False
        elif "badrequest" in name or status_code in {400, 404, 422}:
            code, retryable = ProviderErrorCode.INVALID_REQUEST, False
        elif "connection" in name or (isinstance(status_code, int) and status_code >= 500):
            code, retryable = ProviderErrorCode.PROVIDER_UNAVAILABLE, True
        else:
            code, retryable = ProviderErrorCode.PROVIDER_UNAVAILABLE, True
        return LLMProviderError(
            self._safe_error_message(error, code),
            code=code,
            retryable=retryable,
            provider=self._config.provider_id,
        )

    @staticmethod
    def _safe_error_message(error: Exception, code: ProviderErrorCode) -> str:
        status_code = getattr(error, "status_code", None)
        detail = type(error).__name__
        if isinstance(status_code, int):
            detail += f" status={status_code}"
        return f"LLM provider {code.value.lower()}: {detail}"

    @staticmethod
    def _configuration_error(
        message: str,
        *,
        provider: str = "configuration",
    ) -> LLMProviderError:
        return LLMProviderError(
            message,
            code=ProviderErrorCode.CONFIGURATION_ERROR,
            retryable=False,
            provider=provider,
        )
