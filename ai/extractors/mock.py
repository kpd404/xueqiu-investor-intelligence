from dataclasses import dataclass

from contracts import (
    AssetOpinionExtraction,
    CurrentAuthorEventView,
    OpinionDirection,
    OpinionExtractionResult,
)


@dataclass(frozen=True, slots=True)
class MockOpinionExtractor:
    """Fixture-only deterministic extractor for pipeline tests and local development."""

    model_version: str = "mock-opinion-v1"

    async def extract(self, event: CurrentAuthorEventView) -> OpinionExtractionResult:
        content = "".join(event.content.split())
        fixture_matches = "腾讯AI商业化空间正在扩大" in content and (
            "广告恢复也可能推动盈利改善" in content or "广告恢复可能推动盈利改善" in content
        )
        if not fixture_matches:
            return OpinionExtractionResult(
                investment_related=False,
                opinions=(),
                model_version=self.model_version,
            )

        return OpinionExtractionResult(
            investment_related=True,
            opinions=(
                AssetOpinionExtraction(
                    asset_name="Tencent",
                    symbol="00700",
                    market="HK",
                    direction=OpinionDirection.BULLISH,
                    strength=80,
                    confidence=0.9,
                    thesis=("AI商业化", "广告恢复"),
                    catalysts=("广告恢复",),
                    risks=(),
                    time_horizon="LONG_TERM",
                ),
            ),
            model_version=self.model_version,
        )
