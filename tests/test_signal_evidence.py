from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect

from contracts import (
    SignalCreate,
    SignalSeverity,
    SignalState,
    SignalType,
    SignalView,
)
from database.models import Asset, Investor, Signal
from signal_engine.contracts import SignalEvidence, SignalEvidenceCollection
from signal_engine.repository import SignalRepository
from signal_engine.service import SignalGenerator


def evidence_payload() -> dict[str, object]:
    return {
        "raw_event_id": uuid4(),
        "evidence_type": "OPINION_CHANGE",
        "description": "Investor direction changed from neutral to bullish.",
    }


def test_signal_evidence_json_schema_is_stable() -> None:
    schema = SignalEvidence.model_json_schema()

    assert set(schema["properties"]) == {
        "raw_event_id",
        "evidence_type",
        "description",
    }
    assert set(schema["required"]) == {
        "raw_event_id",
        "evidence_type",
        "description",
    }
    assert schema["additionalProperties"] is False
    assert schema["properties"]["evidence_type"]["pattern"] == "^[A-Z][A-Z0-9_]*$"


def test_signal_evidence_collection_serializes_to_json() -> None:
    payload = evidence_payload()
    evidence = SignalEvidenceCollection.model_validate([payload])

    serialized = evidence.model_dump(mode="json")
    assert serialized == [
        {
            "raw_event_id": str(payload["raw_event_id"]),
            "evidence_type": "OPINION_CHANGE",
            "description": "Investor direction changed from neutral to bullish.",
        }
    ]


def test_signal_evidence_rejects_missing_or_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SignalEvidence.model_validate(
            {
                "evidence_type": "RAW_EVENT",
                "description": "Missing source event.",
            }
        )

    with pytest.raises(ValidationError):
        SignalEvidence.model_validate({**evidence_payload(), "unsupported": True})


def _command(source_id=None, *, signal_type=SignalType.NEW_ATTENTION) -> SignalCreate:
    return SignalCreate(
        asset_id=uuid4(),
        investor_id=uuid4(),
        signal_type=signal_type,
        state=SignalState.ACTIVE,
        severity=SignalSeverity.LOW,
        source_type="AttentionOccurrence",
        source_id=source_id or uuid4(),
        created_at=datetime(2026, 9, 16, tzinfo=UTC),
        observed_at=datetime(2026, 9, 15, tzinfo=UTC),
        metadata={"rule": "test"},
    )


def test_signal_v0_contract_has_no_score_or_recommendation_fields() -> None:
    assert set(SignalType) == {
        SignalType.NEW_ATTENTION,
        SignalType.THESIS_CHANGE,
        SignalType.CROSS_INVESTOR_ALIGNMENT,
        SignalType.CONSENSUS_CHANGE,
    }
    assert set(SignalState) == {
        SignalState.ACTIVE,
        SignalState.RESOLVED,
        SignalState.SUPERSEDED,
    }
    assert set(SignalSeverity) == {
        SignalSeverity.LOW,
        SignalSeverity.MEDIUM,
        SignalSeverity.HIGH,
    }
    assert "signal_score" not in SignalCreate.model_fields
    assert "signal_level" not in SignalCreate.model_fields


def test_signal_repository_identity_is_idempotent(db_session) -> None:
    asset = Asset(name="Test Asset", market="SH", symbol="600000")
    investor = Investor(name="Test Investor", platform="test", platform_user_id="signal-1")
    db_session.add_all([asset, investor])
    db_session.flush()
    source_id = uuid4()
    command = _command(source_id)
    command = command.model_copy(update={"asset_id": asset.id, "investor_id": investor.id})
    repository = SignalRepository(db_session)

    first, created = repository.add_if_absent(command)
    second, reused = repository.add_if_absent(command)
    db_session.commit()

    assert created is True
    assert reused is False
    assert first.id == second.id
    assert len(repository.list()) == 1
    assert {column.name for column in inspect(Signal).columns} == {
        "id",
        "asset_id",
        "investor_id",
        "signal_type",
        "state",
        "severity",
        "source_type",
        "source_id",
        "created_at",
        "observed_at",
        "metadata",
    }


class _Reader:
    def __init__(self, candidates):
        self.candidates = tuple(candidates)

    def list_candidates(self, **kwargs):
        selected = kwargs.get("signal_types")
        if selected is None:
            return self.candidates
        return tuple(item for item in self.candidates if item.signal_type in selected)


class _Writer:
    def __init__(self):
        self.values = {}

    def get_by_identity(self, signal_type, source_id):
        return self.values.get((signal_type, source_id))

    def add_if_absent(self, command):
        key = (command.signal_type.value, command.source_id)
        existing = self.values.get(key)
        if existing is not None:
            return existing, False
        result = SignalView(
            id=uuid4(),
            **command.model_dump(),
        )
        self.values[key] = result
        return result, True


class _Uow:
    def __init__(self, candidates):
        self.source_reader = _Reader(candidates)
        self.signals = _Writer()
        self.commit_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def commit(self):
        self.commit_count += 1


def test_signal_generator_dry_run_and_generate_are_idempotent() -> None:
    candidates = (
        _command(signal_type=SignalType.NEW_ATTENTION),
        _command(signal_type=SignalType.THESIS_CHANGE),
        _command(signal_type=SignalType.CROSS_INVESTOR_ALIGNMENT),
        _command(signal_type=SignalType.CONSENSUS_CHANGE),
    )
    uow = _Uow(candidates)
    generator = SignalGenerator(lambda: uow)

    plan = generator.dry_run()
    first = generator.generate()
    second = generator.generate_many()

    assert plan.dry_run is True
    assert plan.created_count == 4
    assert plan.reused_count == 0
    assert first.created_count == 4
    assert first.reused_count == 0
    assert second.created_count == 0
    assert second.reused_count == 4
    assert second.duplicate_count == 0
    assert uow.commit_count == 2
    assert {item.signal_type for item in first.candidates} == set(SignalType)


def test_signal_generator_asset_and_type_scopes_are_explicit() -> None:
    candidate = _command(signal_type=SignalType.THESIS_CHANGE)
    uow = _Uow((candidate,))
    generator = SignalGenerator(lambda: uow)

    result = generator.dry_run(
        asset_ids=(candidate.asset_id,),
        signal_types=(SignalType.THESIS_CHANGE,),
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].signal_type is SignalType.THESIS_CHANGE
    assert generator.dry_run(signal_types=()).candidates == ()
