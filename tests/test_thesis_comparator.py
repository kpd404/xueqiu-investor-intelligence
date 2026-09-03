import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from ai.comparators import OpenAICompatibleThesisComparator, ThesisComparator
from contracts import (
    LLMProviderConfig,
    OpinionDirection,
    ProviderErrorCode,
    ThesisChangeType,
    ThesisComparisonInput,
    ThesisOpinionView,
)


class _Content:
    type = "output_text"

    def __init__(self, text: str) -> None:
        self.text = text


class _Message:
    def __init__(self, text: str) -> None:
        self.content = [_Content(text)]


class _Response:
    status = "completed"
    id = "thesis-response"
    model = "comparison-model"
    usage = type("Usage", (), {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})()

    def __init__(self, payload: object | None = None, *, raw_text: str | None = None) -> None:
        text = raw_text if raw_text is not None else json.dumps(payload, ensure_ascii=False)
        self.output = [_Message(text)] if text else []
        self.output_text = text


class _Responses:
    def __init__(self, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class _Client:
    def __init__(self, responses: _Responses) -> None:
        self.responses = responses


def _config() -> LLMProviderConfig:
    return LLMProviderConfig(
        provider_id="test-provider",
        base_url="https://gateway.example.test/v1",
        api_key="test-key",
        model="comparison-model-v1",
    )


def _opinion(*, day: int, text: str, direction: OpinionDirection) -> ThesisOpinionView:
    return ThesisOpinionView(
        opinion_id=uuid4(),
        event_id=uuid4(),
        investor_id=uuid4(),
        asset_id=uuid4(),
        analysis_version="opinion-analysis-v3:active",
        asset_name="Test Asset",
        market="SH",
        symbol="000001",
        direction=direction,
        strength=70,
        confidence=0.8,
        thesis=("cash flow",),
        catalysts=(),
        risks=(),
        time_horizon=None,
        published_time=datetime(2026, 9, day, tzinfo=UTC),
        generated_time=datetime(2026, 9, day, 1, tzinfo=UTC),
        current_author_text=text,
    )


def _input() -> ThesisComparisonInput:
    asset_id = uuid4()
    investor_id = uuid4()
    previous = _opinion(day=1, text="旧作者文本", direction=OpinionDirection.BULLISH).model_copy(
        update={"asset_id": asset_id, "investor_id": investor_id}
    )
    current = _opinion(day=2, text="新作者文本", direction=OpinionDirection.BULLISH).model_copy(
        update={"asset_id": asset_id, "investor_id": investor_id}
    )
    return ThesisComparisonInput(
        asset_id=asset_id,
        asset_name="Test Asset",
        market="SH",
        symbol="000001",
        previous=previous,
        current=current,
    )


def _result_payload(change_type: str = ThesisChangeType.THESIS_EXTENDED.value) -> dict[str, object]:
    return {
        "change_type": change_type,
        "confidence": 0.82,
        "summary": "new supporting dimension",
        "evidence": ["current author text"],
    }


def test_comparator_is_provider_neutral_and_uses_independent_spec() -> None:
    responses = _Responses(_Response(_result_payload()))
    comparator = OpenAICompatibleThesisComparator(
        _config(),
        client=_Client(responses),
        prompt_text="comparison prompt",
    )

    assert isinstance(comparator, ThesisComparator)
    result = asyncio.run(comparator.compare(_input()))

    assert result.change_type is ThesisChangeType.THESIS_EXTENDED
    assert comparator.comparison_spec.comparison_policy_version == "thesis-comparison-policy-v1"
    assert comparator.comparison_spec.prompt_version == "thesis-comparison-v1"
    assert comparator.comparison_spec.comparison_version.startswith("thesis-comparison-policy-v1:")
    call = responses.calls[0]
    assert call["model"] == "comparison-model-v1"
    assert call["text"]["format"]["type"] == "json_schema"
    assert call["text"]["format"]["name"] == "ThesisComparisonResult"


def test_comparator_request_contains_only_safe_comparison_fields() -> None:
    responses = _Responses(_Response(_result_payload()))
    comparator = OpenAICompatibleThesisComparator(
        _config(),
        client=_Client(responses),
        prompt_text="comparison prompt",
    )
    input_data = _input()
    asyncio.run(comparator.compare(input_data))

    request = str(responses.calls[0]["input"])
    assert "旧作者文本" in request
    assert "新作者文本" in request
    assert str(input_data.current.opinion_id) not in request
    assert str(input_data.current.event_id) not in request


def test_comparator_missing_usage_is_allowed() -> None:
    response = _Response(_result_payload())
    response.usage = None
    responses = _Responses(response)
    comparator = OpenAICompatibleThesisComparator(
        _config(),
        client=_Client(responses),
        prompt_text="comparison prompt",
    )

    result = asyncio.run(comparator.compare(_input()))

    assert result.change_type is ThesisChangeType.THESIS_EXTENDED
    assert comparator.last_provider_metadata["total_tokens"] is None


@pytest.mark.parametrize(
    ("error_type", "code", "retryable"),
    [
        ("AuthenticationError", ProviderErrorCode.AUTHENTICATION_ERROR, False),
        ("RateLimitError", ProviderErrorCode.RATE_LIMITED, True),
        ("APITimeoutError", ProviderErrorCode.TIMEOUT, True),
    ],
)
def test_comparator_maps_provider_errors(
    error_type: str,
    code: ProviderErrorCode,
    retryable: bool,
) -> None:
    sdk_error = type(error_type, (Exception,), {})
    comparator = OpenAICompatibleThesisComparator(
        _config(),
        client=_Client(_Responses(error=sdk_error("secret request failed"))),
        prompt_text="comparison prompt",
    )

    with pytest.raises(Exception) as raised:
        asyncio.run(comparator.compare(_input()))

    assert raised.value.code is code
    assert raised.value.retryable is retryable
    assert "secret" not in str(raised.value)


def test_comparator_rejects_invalid_structured_result() -> None:
    comparator = OpenAICompatibleThesisComparator(
        _config(),
        client=_Client(_Responses(_Response(None, raw_text="{broken"))),
        prompt_text="comparison prompt",
    )

    with pytest.raises(Exception) as raised:
        asyncio.run(comparator.compare(_input()))

    assert raised.value.code is ProviderErrorCode.INVALID_STRUCTURED_OUTPUT
