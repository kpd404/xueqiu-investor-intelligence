from uuid import uuid4

import pytest
from pydantic import ValidationError

from database.models import Signal
from database.models.enums import SignalLevel
from signal_engine.contracts import SignalEvidence, SignalEvidenceCollection


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


def test_signal_normalizes_reasons_using_evidence_contract() -> None:
    payload = evidence_payload()
    signal = Signal(
        asset_id=uuid4(),
        signal_score=80.0,
        signal_level=SignalLevel.HIGH_PRIORITY_RESEARCH,
        tags=["OPINION_UPGRADE"],
        reasons=[payload],
        risks=[],
    )

    assert signal.reasons[0] == {
        "raw_event_id": str(payload["raw_event_id"]),
        "evidence_type": "OPINION_CHANGE",
        "description": "Investor direction changed from neutral to bullish.",
    }


def test_signal_rejects_untraceable_reasons() -> None:
    with pytest.raises(ValidationError):
        Signal(
            asset_id=uuid4(),
            signal_score=80.0,
            signal_level=SignalLevel.HIGH_PRIORITY_RESEARCH,
            tags=[],
            reasons=[{"evidence_type": "RAW_EVENT", "description": "No event ID."}],
            risks=[],
        )
