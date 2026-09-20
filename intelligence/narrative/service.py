"""Deterministic, read-only narrative projection over Discovery candidates."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from contracts import IntelligenceEventType
from intelligence.discovery.service import (
    DiscoveryAssetNotFoundError,
    IntelligenceDiscoveryService,
)
from intelligence.narrative.schemas import (
    IntelligenceNarrativeView,
    NarrativeAssetIdentity,
)
from intelligence.read_scope import AssetIntelligenceReadScope
from intelligence.schemas.discovery import IntelligenceDiscoveryCandidate


class IntelligenceNarrativeService:
    """Render observed Discovery facts without adding semantic inference."""

    def __init__(self, discovery_service: IntelligenceDiscoveryService) -> None:
        self._discovery_service = discovery_service

    def get_asset_narrative(self, asset_id: UUID) -> IntelligenceNarrativeView:
        candidate = self._discovery_service.get_candidate_by_asset(asset_id)
        if candidate is not None:
            return self.get_candidate_narrative(candidate)
        asset = self._discovery_service.get_asset_identity(asset_id)
        return self._empty_narrative(
            NarrativeAssetIdentity(
                asset_id=asset.asset_id,
                name=asset.name,
                market=asset.market,
                symbol=asset.symbol,
            )
        )

    def get_candidate_narrative(
        self,
        candidate: IntelligenceDiscoveryCandidate,
    ) -> IntelligenceNarrativeView:
        asset = NarrativeAssetIdentity(
            asset_id=candidate.asset.asset_id,
            name=candidate.asset.name,
            market=candidate.asset.market,
            symbol=candidate.asset.symbol,
        )
        activity = candidate.activity_summary
        event_types = set(candidate.event_summary.event_types)
        reasons = set(candidate.discovery_reasons)
        asset_name = asset.name

        attention_summary = (
            f"The active evidence chain includes activity from {activity.investor_count} "
            f"distinct monitored investor(s)."
        )
        thesis_summary = (
            f"An INVESTOR_VIEW_CHANGE event is present for {asset_name}."
            if IntelligenceEventType.INVESTOR_VIEW_CHANGE in event_types
            else "No INVESTOR_VIEW_CHANGE event is present in this active candidate."
        )
        cross_investor_summary = (
            f"A CROSS_INVESTOR_DISCOVERY event is present for {asset_name}."
            if IntelligenceEventType.CROSS_INVESTOR_DISCOVERY in event_types
            else "No CROSS_INVESTOR_DISCOVERY event is present in this active candidate."
        )
        consensus_summary = (
            f"A CONSENSUS_STATE_CHANGE event is present for {asset_name}."
            if IntelligenceEventType.CONSENSUS_STATE_CHANGE in event_types
            else "No CONSENSUS_STATE_CHANGE event is present in this active candidate."
        )
        reason_text = ", ".join(candidate.discovery_reasons)
        headline = f"Observed intelligence activity around {asset_name}"
        summary = (
            f"In the current observed sample, {asset_name} is associated with "
            f"{activity.investor_count} monitored investor(s), "
            f"{activity.event_count} aggregate event(s), "
            f"{activity.signal_count} Signal(s), and "
            f"{activity.feed_count} ACTIVE FeedItem(s)."
        )
        evidence_summary = (
            f"Observed event types: {self._join_or_none(value.value for value in event_types)}. "
            f"Discovery reasons: {reason_text or 'none'}; "
            f"distinct Signals: {activity.signal_count}; "
            f"distinct aggregate Events: {activity.event_count}; "
            f"ACTIVE FeedItems: {activity.feed_count}."
        )
        timeline_summary = (
            "Observed time range: "
            f"{candidate.timeline.first_observed_at.isoformat()} to "
            f"{candidate.timeline.latest_observed_at.isoformat()}."
        )
        limitations = self._limitations()
        # Keep the local variable explicit: reason presence is a fact-only
        # template input, not a hidden score or recommendation calculation.
        if "MULTI_INVESTOR_ACTIVITY" in reasons:
            attention_summary += " MULTI_INVESTOR_ACTIVITY is present in the candidate reasons."

        return IntelligenceNarrativeView(
            asset=asset,
            headline=headline,
            summary=summary,
            attention_summary=attention_summary,
            thesis_summary=thesis_summary,
            cross_investor_summary=cross_investor_summary,
            consensus_summary=consensus_summary,
            evidence_summary=evidence_summary,
            timeline_summary=timeline_summary,
            limitations=limitations,
        )

    def get_scope_narrative(
        self,
        scope: AssetIntelligenceReadScope,
        candidate: IntelligenceDiscoveryCandidate | None,
    ) -> IntelligenceNarrativeView:
        if candidate is not None:
            return self.get_candidate_narrative(candidate)
        return self._empty_narrative(
            NarrativeAssetIdentity(
                asset_id=scope.asset.asset_id,
                name=scope.asset.name,
                market=scope.asset.market,
                symbol=scope.asset.symbol,
            )
        )

    def batch_generate(
        self,
        candidates: Iterable[IntelligenceDiscoveryCandidate] | None = None,
        *,
        limit: int = 100,
        event_type: IntelligenceEventType | None = None,
    ) -> tuple[IntelligenceNarrativeView, ...]:
        if candidates is None:
            candidates = self._discovery_service.get_candidates(
                limit=limit,
                event_type=event_type,
            ).items
        return tuple(self.get_candidate_narrative(candidate) for candidate in candidates)

    @staticmethod
    def _empty_narrative(asset: NarrativeAssetIdentity) -> IntelligenceNarrativeView:
        return IntelligenceNarrativeView(
            asset=asset,
            headline=f"No active intelligence activity observed for {asset.name}",
            summary=(
                "No ACTIVE FeedItem source is available for this Asset in the current "
                "observed sample."
            ),
            attention_summary="No active attention evidence is available in this projection.",
            thesis_summary="No active thesis activity evidence is available in this projection.",
            cross_investor_summary=(
                "No active cross-investor activity evidence is available in this projection."
            ),
            consensus_summary=(
                "No active consensus-state activity evidence is available in this projection."
            ),
            evidence_summary="Active evidence counts are zero for this narrative projection.",
            timeline_summary="No active observed time range is available.",
            limitations=[
                "No ACTIVE FeedItem source is available.",
                "Observed evidence only; no absence inference is made.",
                "Available collection provenance does not establish historical completeness.",
                "This view does not describe holdings, conviction, influence, or advice.",
            ],
        )

    @staticmethod
    def _limitations() -> list[str]:
        return [
            "Observed evidence only.",
            "Historical completeness is UNKNOWN.",
            "Available collection provenance does not establish historical completeness.",
            "Absence inference is unsupported.",
            "This view does not describe holdings, conviction, influence, or advice.",
        ]

    @staticmethod
    def _join_or_none(values: Iterable[str]) -> str:
        ordered = sorted(values)
        return ", ".join(ordered) if ordered else "none"


__all__ = [
    "DiscoveryAssetNotFoundError",
    "IntelligenceNarrativeService",
]
