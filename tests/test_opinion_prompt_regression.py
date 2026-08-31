import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

from ai.extractors.openai_compatible import (
    PROMPT_VERSION,
    OpenAICompatibleOpinionExtractor,
)
from contracts import EventType, LLMProviderConfig, OpinionDirection, RawEventView


class _Content:
    type = "output_text"

    def __init__(self, text: str) -> None:
        self.text = text


class _Message:
    def __init__(self, text: str) -> None:
        self.content = [_Content(text)]


class _Response:
    status = "completed"
    id = "prompt-regression"
    model = "test-model"
    usage = None

    def __init__(self, payload: dict[str, object]) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        self.output = [_Message(text)]
        self.output_text = text


class _Responses:
    def __init__(self, payload: dict[str, object]) -> None:
        self._response = _Response(payload)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _Response:
        self.calls.append(kwargs)
        return self._response


class _Client:
    def __init__(self, responses: _Responses) -> None:
        self.responses = responses


def _event(content: str) -> RawEventView:
    return RawEventView(
        id=uuid4(),
        investor_id=uuid4(),
        event_type=EventType.POST,
        source="manual",
        url="https://example.test/event",
        published_time=datetime(2026, 8, 31, tzinfo=UTC),
        content=content,
        raw_data={},
        hash="a" * 64,
        collected_time=datetime(2026, 8, 31, tzinfo=UTC),
    )


def _extractor(responses: _Responses) -> OpenAICompatibleOpinionExtractor:
    return OpenAICompatibleOpinionExtractor(
        LLMProviderConfig(
            provider_id="test-provider",
            base_url="https://gateway.example.test/v1",
            api_key="test-key",
            model="test-model",
        ),
        client=_Client(responses),
    )


def test_prompt_v4_prioritizes_explicit_company_over_material_category() -> None:
    responses = _Responses(
        {
            "investment_related": True,
            "opinions": [
                {
                    "asset_name": "比音勒芬",
                    "symbol": None,
                    "market": None,
                    "direction": OpinionDirection.BEARISH.value,
                    "strength": 75,
                    "confidence": 0.8,
                    "thesis": ["高价和增长"],
                    "catalysts": [],
                    "risks": ["传统布料"],
                    "time_horizon": "LONG_TERM",
                }
            ],
            "model_version": "ignored",
            "analysis_spec": None,
            "provider_metadata": {},
            "unresolved_assets": [],
        }
    )
    extractor = _extractor(responses)

    result = asyncio.run(
        extractor.extract(_event("比音勒芬的高价和增长值得关注，但传统布料可能长期承压。"))
    )

    assert PROMPT_VERSION == "opinion-extraction-v4"
    assert result.analysis_spec.prompt_version == "opinion-extraction-v4"
    assert result.opinions[0].asset_name == "比音勒芬"
    instructions = str(responses.calls[0]["instructions"])
    assert "company or security" in instructions
    assert "material" in instructions
    assert "category" in instructions
    assert "must not be placed in `unresolved_assets`" in instructions


def test_category_only_text_does_not_create_a_security_entity() -> None:
    responses = _Responses(
        {
            "investment_related": False,
            "opinions": [],
            "model_version": "ignored",
            "analysis_spec": None,
            "provider_metadata": {},
            "unresolved_assets": [],
        }
    )
    extractor = _extractor(responses)

    result = asyncio.run(extractor.extract(_event("传统布料行业需求改善。")))

    assert result.investment_related is False
    assert result.opinions == ()
    assert result.unresolved_assets == ()
