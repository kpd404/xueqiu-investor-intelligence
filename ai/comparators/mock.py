from dataclasses import dataclass

from contracts import (
    ThesisChangeType,
    ThesisComparisonInput,
    ThesisComparisonResult,
    ThesisComparisonSpec,
)


@dataclass(frozen=True, slots=True)
class MockThesisComparator:
    """Fixture-only comparator; production comparisons use a provider adapter."""

    comparison_spec: ThesisComparisonSpec
    result: ThesisComparisonResult | None = None

    async def compare(self, input_data: ThesisComparisonInput) -> ThesisComparisonResult:
        if self.result is not None:
            return self.result
        return ThesisComparisonResult(
            change_type=ThesisChangeType.INSUFFICIENT_EVIDENCE,
            confidence=0.0,
            summary="mock comparator result",
            evidence=(),
        )
