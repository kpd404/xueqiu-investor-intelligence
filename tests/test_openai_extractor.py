import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from openai import OpenAI
from pydantic import ValidationError

from ai.extractors import (
    OpenAICompatibleOpinionExtractor,
    OpenAIOpinionExtractor,
    OpinionExtractor,
)
from config import Settings
from contracts import (
    EventType,
    LLMProviderConfig,
    LLMProviderError,
    OpinionDirection,
    ProviderCapabilities,
    ProviderErrorCode,
    RawEventView,
)


class FakeUsage:
    input_tokens = 111
    output_tokens = 37
    total_tokens = 148


class FakeContent:
    type = "output_text"

    def __init__(self, text: str) -> None:
        self.text = text


class FakeMessage:
    type = "message"

    def __init__(self, text: str) -> None:
        self.content = [FakeContent(text)]


class FakeResponse:
    status = "completed"
    id = "resp_fake_123"
    model = "runtime-model"
    usage = FakeUsage()

    def __init__(self, payload: object | None = None, *, raw_text: str | None = None) -> None:
        text = raw_text if raw_text is not None else json.dumps(payload, ensure_ascii=False)
        self.output = [FakeMessage(text)] if text else []
        self.output_text = text


class FakeResponses:
    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses


def raw_event() -> RawEventView:
    return RawEventView(
        id=uuid4(),
        investor_id=uuid4(),
        event_type=EventType.POST,
        source="manual",
        url="https://example.test/events/1",
        published_time=datetime(2026, 8, 27, 8, 0, tzinfo=UTC),
        content="腾讯AI商业化空间正在扩大，广告业务恢复也可能推动盈利改善。",
        raw_data={"cookie": "must-not-be-sent"},
        hash="a" * 64,
        collected_time=datetime(2026, 8, 27, 8, 1, tzinfo=UTC),
    )


def config(
    *,
    provider_id: str = "test-provider",
    model: str = "my-custom-model-v123",
    base_url: str = "https://gateway.example.test/v1",
    capabilities: ProviderCapabilities | None = None,
) -> LLMProviderConfig:
    return LLMProviderConfig(
        provider_id=provider_id,
        base_url=base_url,
        api_key="test-secret",
        model=model,
        capabilities=capabilities or ProviderCapabilities(),
    )


def bullish_payload(model_version: str = "ignored-by-adapter") -> dict[str, object]:
    return {
        "investment_related": True,
        "opinions": [
            {
                "asset_name": "Tencent",
                "symbol": "00700",
                "market": "HK",
                "direction": OpinionDirection.BULLISH.value,
                "strength": 88,
                "confidence": 0.76,
                "thesis": ["AI商业化空间扩大", "广告业务恢复"],
                "catalysts": ["AI应用落地"],
                "risks": [],
                "time_horizon": "LONG_TERM",
            }
        ],
        "model_version": model_version,
        "analysis_spec": None,
        "provider_metadata": {},
        "unresolved_assets": [],
    }


def extractor(
    fake_responses: FakeResponses,
    *,
    provider_id: str = "test-provider",
    model: str = "my-custom-model-v123",
) -> OpenAICompatibleOpinionExtractor:
    return OpenAICompatibleOpinionExtractor(
        config(provider_id=provider_id, model=model),
        client=FakeClient(fake_responses),
        prompt_text="test prompt",
    )


def test_generic_adapter_implements_port_and_old_name_is_thin_alias() -> None:
    assert isinstance(extractor(FakeResponses()), OpinionExtractor)
    assert OpenAIOpinionExtractor is OpenAICompatibleOpinionExtractor


def test_generic_adapter_uses_standard_responses_json_schema() -> None:
    responses = FakeResponses(FakeResponse(bullish_payload()))
    provider = extractor(responses)
    event = raw_event()

    result = asyncio.run(provider.extract(event))

    assert result.investment_related is True
    assert result.opinions[0].direction == OpinionDirection.BULLISH
    assert result.analysis_spec.provider_id == "test-provider"
    assert result.analysis_spec.model_version == "my-custom-model-v123"
    assert result.analysis_spec.analysis_version.startswith("opinion-analysis-v2:")
    assert result.provider_metadata == {
        "provider": "test-provider",
        "base_url": "https://gateway.example.test/v1",
        "provider_response_id": "resp_fake_123",
        "model": "runtime-model",
        "input_tokens": 111,
        "output_tokens": 37,
        "total_tokens": 148,
    }

    call = responses.calls[0]
    assert call["model"] == "my-custom-model-v123"
    assert "text_format" not in call
    text_config = call["text"]
    assert isinstance(text_config, dict)
    format_config = text_config["format"]
    assert isinstance(format_config, dict)
    assert format_config["type"] == "json_schema"
    assert format_config["strict"] is True
    assert format_config["name"] == "OpinionExtractionResult"
    assert format_config["schema"]["additionalProperties"] is False
    assert "腾讯AI商业化" in str(call["input"])
    assert str(event.id) not in str(call["input"])
    assert str(event.investor_id) not in str(call["input"])
    assert "must-not-be-sent" not in str(call["input"])


def test_fake_openai_compatible_http_server_accepts_arbitrary_provider_and_model() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        response = {
            "id": "resp_http_fake",
            "object": "response",
            "created_at": 0,
            "model": "my-custom-model-v123",
            "output": [
                {
                    "id": "message-http-fake",
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(bullish_payload(), ensure_ascii=False),
                            "annotations": [],
                        }
                    ],
                }
            ],
            "status": "completed",
            "usage": {"input_tokens": 4, "output_tokens": 5, "total_tokens": 9},
        }
        return httpx.Response(200, request=request, json=response)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    sdk_client = OpenAI(
        api_key="test-key",
        base_url="https://fake-provider.example/v1",
        http_client=http_client,
        max_retries=0,
    )
    provider = OpenAICompatibleOpinionExtractor(
        config(
            provider_id="test-provider",
            base_url="https://fake-provider.example/v1",
            model="my-custom-model-v123",
        ),
        client=sdk_client,
        prompt_text="test prompt",
    )

    result = asyncio.run(provider.extract(raw_event()))

    assert result.opinions[0].symbol == "00700"
    assert result.provider_metadata["provider"] == "test-provider"
    assert result.provider_metadata["total_tokens"] == 9
    assert len(requests) == 1
    request_payload = json.loads(requests[0].content)
    assert requests[0].url.path == "/v1/responses"
    assert request_payload["model"] == "my-custom-model-v123"
    assert request_payload["text"]["format"]["type"] == "json_schema"
    assert request_payload["text"]["format"]["strict"] is True


def test_arbitrary_model_name_is_used_verbatim_in_request_and_metadata() -> None:
    responses = FakeResponses(FakeResponse(bullish_payload()))
    provider = extractor(responses, model="arbitrary-model-b")

    result = asyncio.run(provider.extract(raw_event()))

    assert responses.calls[0]["model"] == "arbitrary-model-b"
    assert result.analysis_spec.model_version == "arbitrary-model-b"
    assert result.provider_metadata["model"] == "runtime-model"


def test_no_opinion_is_a_valid_structured_result() -> None:
    payload = {
        "investment_related": False,
        "opinions": [],
        "model_version": "anything",
        "analysis_spec": None,
        "provider_metadata": {},
        "unresolved_assets": [],
    }
    result = asyncio.run(extractor(FakeResponses(FakeResponse(payload))).extract(raw_event()))

    assert result.investment_related is False
    assert result.opinions == ()


def test_ambiguous_asset_is_preserved_without_inventing_identity() -> None:
    payload = {
        "investment_related": True,
        "opinions": [],
        "model_version": "anything",
        "analysis_spec": None,
        "provider_metadata": {},
        "unresolved_assets": [
            {
                "asset_name": "这家AI应用公司",
                "symbol": None,
                "market": None,
                "reason": "AMBIGUOUS_ASSET",
            }
        ],
    }
    result = asyncio.run(extractor(FakeResponses(FakeResponse(payload))).extract(raw_event()))

    assert result.unresolved_assets[0].asset_name == "这家AI应用公司"
    assert result.unresolved_assets[0].symbol is None
    assert result.unresolved_assets[0].market is None


def test_missing_usage_does_not_fail_extraction() -> None:
    response = FakeResponse(bullish_payload())
    response.usage = None
    result = asyncio.run(extractor(FakeResponses(response)).extract(raw_event()))

    assert result.opinions
    assert result.provider_metadata["input_tokens"] is None
    assert result.provider_metadata["total_tokens"] is None


@pytest.mark.parametrize(
    ("error_type", "expected_code", "retryable"),
    [
        ("AuthenticationError", ProviderErrorCode.AUTHENTICATION_ERROR, False),
        ("RateLimitError", ProviderErrorCode.RATE_LIMITED, True),
        ("APITimeoutError", ProviderErrorCode.TIMEOUT, True),
        ("APIConnectionError", ProviderErrorCode.PROVIDER_UNAVAILABLE, True),
        ("BadRequestError", ProviderErrorCode.INVALID_REQUEST, False),
        ("APIResponseValidationError", ProviderErrorCode.INVALID_STRUCTURED_OUTPUT, False),
    ],
)
def test_sdk_errors_map_to_neutral_retry_contract(
    error_type: str,
    expected_code: ProviderErrorCode,
    retryable: bool,
) -> None:
    sdk_error = type(error_type, (Exception,), {})
    with pytest.raises(LLMProviderError) as raised:
        asyncio.run(
            extractor(FakeResponses(error=sdk_error("sk-secret request failed"))).extract(
                raw_event()
            )
        )

    assert raised.value.code == expected_code
    assert raised.value.retryable is retryable
    assert raised.value.provider == "test-provider"
    assert "sk-secret" not in str(raised.value)
    assert "request failed" not in str(raised.value)


def test_refusal_is_not_coerced_to_no_opinion() -> None:
    class RefusalContent:
        type = "refusal"

    class RefusalMessage:
        content = [RefusalContent()]

    response = FakeResponse(None)
    response.output = [RefusalMessage()]

    with pytest.raises(LLMProviderError) as raised:
        asyncio.run(extractor(FakeResponses(response)).extract(raw_event()))

    assert raised.value.code == ProviderErrorCode.REFUSED
    assert raised.value.retryable is False
    assert raised.value.provider == "test-provider"


def test_incomplete_response_is_not_success() -> None:
    response = FakeResponse(None)
    response.status = "incomplete"

    with pytest.raises(LLMProviderError) as raised:
        asyncio.run(extractor(FakeResponses(response)).extract(raw_event()))

    assert raised.value.code == ProviderErrorCode.INCOMPLETE_RESPONSE
    assert raised.value.retryable is False


@pytest.mark.parametrize("raw_text", ["{broken", "not-json"])
def test_invalid_structured_json_is_rejected(raw_text: str) -> None:
    response = FakeResponse(None, raw_text=raw_text)

    with pytest.raises(LLMProviderError) as raised:
        asyncio.run(extractor(FakeResponses(response)).extract(raw_event()))

    assert raised.value.code == ProviderErrorCode.INVALID_STRUCTURED_OUTPUT
    assert raised.value.retryable is False


def test_invalid_structured_contract_is_rejected() -> None:
    invalid = {"investment_related": True, "opinions": [], "model_version": "test-model"}

    with pytest.raises(LLMProviderError) as raised:
        asyncio.run(extractor(FakeResponses(FakeResponse(invalid))).extract(raw_event()))

    assert raised.value.code == ProviderErrorCode.INVALID_STRUCTURED_OUTPUT


def test_settings_require_neutral_provider_fields() -> None:
    complete = dict(
        llm_provider_id="test-provider",
        llm_base_url="https://gateway.example.test/v1",
        llm_api_key="test-key",
        llm_model="test-model",
    )
    for field in complete:
        values = {**complete, field: None}
        with pytest.raises(LLMProviderError) as raised:
            OpenAICompatibleOpinionExtractor.from_settings(Settings(**values))
        assert raised.value.code == ProviderErrorCode.CONFIGURATION_ERROR
        assert field.upper() in str(raised.value)


def test_unsupported_style_and_capability_are_configuration_errors() -> None:
    settings = Settings(
        llm_provider_id="test-provider",
        llm_base_url="https://gateway.example.test/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_api_style="chat_completions",
    )
    with pytest.raises(LLMProviderError) as raised:
        OpenAICompatibleOpinionExtractor.from_settings(settings)
    assert raised.value.code == ProviderErrorCode.CONFIGURATION_ERROR

    json_mode_settings = settings.model_copy(
        update={"llm_api_style": "responses", "llm_structured_output": "json_object"}
    )
    with pytest.raises(LLMProviderError) as json_mode_error:
        OpenAICompatibleOpinionExtractor.from_settings(json_mode_settings)
    assert json_mode_error.value.code == ProviderErrorCode.CONFIGURATION_ERROR

    with pytest.raises(ValidationError):
        config(capabilities=ProviderCapabilities(supports_responses_api=False))


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://gateway.example.test/v1",
        "https://user:password@gateway.example.test/v1",
        "https://gateway.example.test/v1?token=secret",
    ],
)
def test_base_url_rejects_non_public_endpoint_forms(base_url: str) -> None:
    with pytest.raises(ValidationError):
        config(base_url=base_url)


def test_provider_capability_contract_allows_missing_usage() -> None:
    provider_config = config(
        capabilities=ProviderCapabilities(supports_usage=False),
    )
    response = FakeResponse(bullish_payload())
    response.usage = None
    provider = OpenAICompatibleOpinionExtractor(
        provider_config,
        client=FakeClient(FakeResponses(response)),
        prompt_text="test prompt",
    )
    result = asyncio.run(provider.extract(raw_event()))
    assert provider_config.capabilities.supports_usage is False
    assert result.opinions
