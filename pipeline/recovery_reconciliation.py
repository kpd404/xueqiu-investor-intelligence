from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from contracts import (
    AssetRecoveryResult,
    AttentionOccurrenceRebuildResult,
    BehaviorReconciliationResult,
    StateUpdateResult,
)


class RecoveryPort(Protocol):
    def recover(
        self,
        *,
        analysis_id: UUID | None = None,
        event_id: UUID | None = None,
        analysis_version: str | None = None,
    ) -> AssetRecoveryResult: ...


class StateRebuildPort(Protocol):
    def update(self, opinion_id: UUID) -> StateUpdateResult: ...


class AttentionRebuildPort(Protocol):
    def rebuild_event(self, event_id: UUID) -> AttentionOccurrenceRebuildResult: ...


class RecoveryReconciliationService:
    """Coordinate deterministic recovery, state replay, and attention refresh."""

    def __init__(
        self,
        recovery: RecoveryPort,
        state_updater: StateRebuildPort,
        attention_rebuilder: AttentionRebuildPort,
    ) -> None:
        self._recovery = recovery
        self._state_updater = state_updater
        self._attention_rebuilder = attention_rebuilder

    def reconcile(
        self,
        *,
        analysis_id: UUID | None = None,
        event_id: UUID | None = None,
        analysis_version: str | None = None,
    ) -> BehaviorReconciliationResult:
        calculated_at = datetime.now(UTC)
        recovery = self._recovery.recover(
            analysis_id=analysis_id,
            event_id=event_id,
            analysis_version=analysis_version,
        )

        state_updates: list[StateUpdateResult] = []
        skipped: list[UUID] = []
        for opinion_id in sorted(recovery.opinion_ids, key=lambda value: value.int):
            try:
                state_updates.append(self._state_updater.update(opinion_id))
            except LookupError:
                skipped.append(opinion_id)

        attention = self._attention_rebuilder.rebuild_event(recovery.event_id)
        affected_asset_ids = tuple(
            sorted(
                {
                    *(update.after.asset_id for update in state_updates),
                    *attention.affected_asset_ids,
                },
                key=lambda value: value.int,
            )
        )
        return BehaviorReconciliationResult(
            recovery=recovery,
            state_updates=tuple(state_updates),
            attention=attention,
            affected_asset_ids=affected_asset_ids,
            skipped_inactive_opinion_ids=tuple(skipped),
            calculated_at=calculated_at,
        )
