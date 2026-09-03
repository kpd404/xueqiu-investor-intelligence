import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from ai.comparators.base import ThesisComparator
from config import Settings, get_production_thesis_comparison_policy, get_settings
from contracts import (
    LLMProviderConfig,
    LLMProviderError,
    ProviderErrorCode,
    StructuredOutputMode,
    ThesisComparisonInput,
    ThesisComparisonResult,
    ThesisComparisonSpec,
)

PROMPT_RESOURCE = Path("prompts/thesis_comparison/v1.md")


class ResponsesResource(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class OpenAICompatibleClient(Protocol):
    responses: ResponsesResource


class OpenAICompatibleThesisComparator(ThesisComparator):
    """Provider-neutral Responses + JSON Schema thesis comparator."""

    def __init__(
        self,
        config: LLMProviderConfig,
        *,
        client: OpenAICompatibleClient | None = None,
        comparison_spec: ThesisComparisonSpec | None = None,
        prompt_text: str | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._comparison_spec = comparison_spec or self._local_spec(config)
        self._prompt_text = prompt_text if prompt_text is not None else self._load_prompt()
        self._last_provider_metadata: dict[str, object] = {}

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "OpenAICompatibleThesisComparator":
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
            production_policy = get_production_thesis_comparison_policy(resolved)
            comparison_spec = ThesisComparisonSpec.from_analysis_spec(production_policy.active_spec)
        except LLMProviderError:
            raise
        except AttributeError as exc:
            raise cls._configuration_error("LLM provider settings are unavailable") from exc
        except ValidationError as exc:
            raise cls._configuration_error("invalid LLM provider configuration") from exc
        return cls(config, comparison_spec=comparison_spec)

    @property
    def comparison_spec(self) -> ThesisComparisonSpec:
        return self._comparison_spec

    @property
    def config(self) -> LLMProviderConfig:
        return self._config

    @property
    def last_provider_metadata(self) -> dict[str, object]:
        return dict(self._last_provider_metadata)

    async def compare(self, input_data: ThesisComparisonInput) -> ThesisComparisonResult:
        try:
            client = self._client or self._build_client()
            response = await asyncio.to_thread(
                client.responses.create,
                model=self._config.model,
                instructions=self._prompt_text,
                input=self._request_input(input_data),
                text=self._structured_output_config(),
            )
        except LLMProviderError:
            raise
        except Exception as exc:
            raise self._map_sdk_error(exc) from exc

        self._validate_response_status(response)
        result = self._parse_structured_response(response)
        self._last_provider_metadata = self._provider_metadata(response)
        return result

    @staticmethod
    def _local_spec(config: LLMProviderConfig) -> ThesisComparisonSpec:
        from contracts import (
            THESIS_COMPARISON_POLICY_VERSION,
            THESIS_COMPARISON_PROMPT_VERSION,
            THESIS_COMPARISON_SCHEMA_VERSION,
            AnalysisSpec,
        )

        return ThesisComparisonSpec.from_analysis_spec(
            AnalysisSpec.for_provider(
                provider_id=config.provider_id,
                model_version=config.model,
                prompt_version=THESIS_COMPARISON_PROMPT_VERSION,
                schema_version=THESIS_COMPARISON_SCHEMA_VERSION,
                analysis_policy_version=THESIS_COMPARISON_POLICY_VERSION,
            )
        )

    def _build_client(self) -> OpenAICompatibleClient:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise self._configuration_error(
                "OpenAI-compatible SDK is not installed",
                provider=self._config.provider_id,
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
        path = Path(__file__).resolve().parents[2] / PROMPT_RESOURCE
        try:
            prompt = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LLMProviderError(
                "thesis comparison prompt is unavailable",
                code=ProviderErrorCode.CONFIGURATION_ERROR,
                retryable=False,
                provider="unknown",
            ) from exc
        if not prompt.strip():
            raise LLMProviderError(
                "thesis comparison prompt is empty",
                code=ProviderErrorCode.CONFIGURATION_ERROR,
                retryable=False,
                provider="unknown",
            )
        return prompt

    @classmethod
    def _request_input(cls, input_data: ThesisComparisonInput) -> str:
        def opinion_block(label: str, opinion: object | None) -> str:
            if opinion is None:
                return f"{label}=NONE"
            return (
                f"{label}:\n"
                f"direction={opinion.direction.value}\n"
                f"strength={opinion.strength}\n"
                f"confidence={opinion.confidence}\n"
                f"thesis={list(opinion.thesis)}\n"
                f"catalysts={list(opinion.catalysts)}\n"
                f"risks={list(opinion.risks)}\n"
                f"time_horizon={opinion.time_horizon}\n"
                f"published_time={opinion.published_time.isoformat()}\n"
                f"current_author_text={opinion.current_author_text}"
            )

        return (
            f"asset_name={input_data.asset_name}\n"
            f"market={input_data.market}\n"
            f"symbol={input_data.symbol}\n"
            f"{opinion_block('previous', input_data.previous)}\n"
            f"{opinion_block('current', input_data.current)}"
        )

    @classmethod
    def _structured_output_config(cls) -> dict[str, object]:
        schema = ThesisComparisonResult.model_json_schema()
        cls._make_strict_schema(schema)
        return {
            "format": {
                "type": StructuredOutputMode.JSON_SCHEMA.value,
                "name": "ThesisComparisonResult",
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
                OpenAICompatibleThesisComparator._make_strict_schema(value)
        elif isinstance(node, list):
            for value in node:
                OpenAICompatibleThesisComparator._make_strict_schema(value)

    def _validate_response_status(self, response: Any) -> None:
        status = str(self._value(response, "status") or "completed").lower()
        if status == "completed":
            pass
        elif status == "failed":
            raise self._provider_error(
                "provider response failed",
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                retryable=True,
            )
        else:
            raise self._provider_error(
                f"provider response was {status}",
                ProviderErrorCode.INCOMPLETE_RESPONSE,
                retryable=False,
            )
        for item in self._value(response, "output") or []:
            for content in self._value(item, "content") or []:
                if self._value(content, "type") in {"refusal", "output_refusal"}:
                    raise self._provider_error(
                        "provider refused the comparison request",
                        ProviderErrorCode.REFUSED,
                        retryable=False,
                    )

    def _parse_structured_response(self, response: Any) -> ThesisComparisonResult:
        output_text = self._output_text(response)
        if not output_text:
            raise self._provider_error(
                "provider returned no structured output",
                ProviderErrorCode.INVALID_STRUCTURED_OUTPUT,
                retryable=False,
            )
        try:
            payload = json.loads(output_text)
            return ThesisComparisonResult.model_validate(payload)
        except (TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise self._provider_error(
                "provider output failed Thesis Comparison contract validation",
                ProviderErrorCode.INVALID_STRUCTURED_OUTPUT,
                retryable=False,
            ) from exc

    @classmethod
    def _output_text(cls, response: Any) -> str | None:
        fragments: list[str] = []
        for item in cls._value(response, "output") or []:
            for content in cls._value(item, "content") or []:
                if cls._value(content, "type") == "output_text":
                    value = cls._value(content, "text")
                    if isinstance(value, str):
                        fragments.append(value)
        if fragments:
            return "\n".join(fragments)
        value = cls._value(response, "output_text")
        return value if isinstance(value, str) else None

    def _provider_metadata(self, response: Any) -> dict[str, object]:
        usage = self._value(response, "usage")
        return {
            "provider": self._config.provider_id,
            "model": self._value(response, "model") or self._config.model,
            "provider_response_id": self._value(response, "id"),
            "input_tokens": self._value(usage, "input_tokens"),
            "output_tokens": self._value(usage, "output_tokens"),
            "total_tokens": self._value(usage, "total_tokens"),
        }

    @staticmethod
    def _value(source: object, key: str) -> object:
        if isinstance(source, Mapping):
            return source.get(key)
        return getattr(source, key, None)

    def _provider_error(
        self,
        message: str,
        code: ProviderErrorCode,
        *,
        retryable: bool,
    ) -> LLMProviderError:
        return LLMProviderError(
            message,
            code=code,
            retryable=retryable,
            provider=self._config.provider_id,
        )

    @staticmethod
    def _configuration_error(message: str, *, provider: str) -> LLMProviderError:
        return LLMProviderError(
            message,
            code=ProviderErrorCode.CONFIGURATION_ERROR,
            retryable=False,
            provider=provider,
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
        elif "badrequest" in name or status_code in {400, 404, 422}:
            code, retryable = ProviderErrorCode.INVALID_REQUEST, False
        elif "connection" in name or (isinstance(status_code, int) and status_code >= 500):
            code, retryable = ProviderErrorCode.PROVIDER_UNAVAILABLE, True
        else:
            code, retryable = ProviderErrorCode.PROVIDER_UNAVAILABLE, True
        return self._provider_error(
            self._safe_error_message(error, code),
            code,
            retryable=retryable,
        )

    @staticmethod
    def _safe_error_message(error: Exception, code: ProviderErrorCode) -> str:
        status_code = getattr(error, "status_code", None)
        detail = type(error).__name__
        if isinstance(status_code, int):
            detail += f" status={status_code}"
        return f"LLM provider {code.value.lower()}: {detail}"
