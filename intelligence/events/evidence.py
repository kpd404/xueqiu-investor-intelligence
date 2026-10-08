"""Shared association grouping over already validated Thesis Signal read views."""

from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from contracts import (
    IntelligenceEventEvidenceView,
    IntelligenceEventType,
    IntelligenceEventView,
    SignalState,
    SignalType,
    SignalView,
)


def group_effective_thesis_evidence(
    events: Iterable[IntelligenceEventView],
    links: Iterable[IntelligenceEventEvidenceView],
    effective_signals: Iterable[SignalView],
) -> dict[UUID, tuple[SignalView, ...]]:
    """Keep only real links matching the Event asset; no source algorithm here."""

    thesis_events = {
        event.id: event
        for event in events
        if event.event_type is IntelligenceEventType.INVESTOR_VIEW_CHANGE
    }
    signals = {
        signal.id: signal
        for signal in effective_signals
        if signal.signal_type is SignalType.THESIS_CHANGE and signal.state is SignalState.ACTIVE
    }
    grouped: dict[UUID, dict[UUID, SignalView]] = defaultdict(dict)
    for link in links:
        event = thesis_events.get(link.event_id)
        signal = signals.get(link.signal_id)
        if event is not None and signal is not None and signal.asset_id == event.asset_id:
            grouped[event.id][signal.id] = signal
    return {
        event_id: tuple(
            sorted(values.values(), key=lambda signal: (signal.observed_at, signal.id.int))
        )
        for event_id, values in grouped.items()
    }
