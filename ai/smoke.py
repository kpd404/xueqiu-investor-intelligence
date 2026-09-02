import argparse
import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from ai.extractors.openai_compatible import OpenAICompatibleOpinionExtractor
from config import get_settings
from contracts import CurrentAuthorEventView, EventType, LLMProviderError, RawEventDTO

DEFAULT_TEXT = (
    "腾讯AI商业化空间正在扩大，广告恢复也可能推动盈利改善，"
    "如果后续AI应用进一步落地，我认为腾讯还有明显的重估空间。"
)


def build_event_view(content: str) -> CurrentAuthorEventView:
    investor_id = uuid4()
    dto = RawEventDTO.build(
        investor_id=investor_id,
        event_type=EventType.POST,
        source="manual-smoke",
        url="https://example.test/llm-smoke/1",
        published_time=datetime.now(UTC),
        content=content,
    )
    return CurrentAuthorEventView(
        event_type=dto.event_type,
        source=dto.source,
        published_time=dto.published_time,
        content=dto.content,
    )


async def run(content: str) -> int:
    try:
        extractor = OpenAICompatibleOpinionExtractor.from_settings(get_settings())
        result = await extractor.extract(build_event_view(content))
    except LLMProviderError as exc:
        print(
            f"Provider error: code={exc.code.value} retryable={exc.retryable} "
            f"provider={exc.provider} message={exc}"
        )
        return 2

    metadata = result.provider_metadata
    print(f"Provider: {metadata.get('provider')}")
    print(f"Base URL: {metadata.get('base_url')}")
    print(f"Model: {metadata.get('model')}")
    print(f"API Style: {extractor.config.api_style.value}")
    print(f"Structured Output: {extractor.config.structured_output.value}")
    print(f"Analysis Policy Version: {result.analysis_spec.analysis_policy_version}")
    print(f"Analysis Version: {result.analysis_spec.analysis_version}")
    print(f"Investment Related: {result.investment_related}")
    for opinion in result.opinions:
        print(
            f"Asset: {opinion.asset_name} / {opinion.symbol} / {opinion.market}\n"
            f"Direction: {opinion.direction.value}\n"
            f"Strength: {opinion.strength:g}\n"
            f"Confidence: {opinion.confidence:g}\n"
            f"Thesis: {', '.join(opinion.thesis) or '(none)'}"
        )
    for unresolved in result.unresolved_assets:
        print(f"Unresolved Asset: {unresolved.asset_name} ({unresolved.reason})")
    print(
        "Usage: "
        f"input_tokens={metadata.get('input_tokens')} "
        f"output_tokens={metadata.get('output_tokens')} "
        f"total_tokens={metadata.get('total_tokens')}"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Generic LLM Opinion extraction smoke test")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.text)))


if __name__ == "__main__":
    main()
