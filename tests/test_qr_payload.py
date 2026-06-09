"""Tests for normalized QR payload data."""

from __future__ import annotations

import pytest

from pds_core.qr_payload import QrPayload, QrPayloadValidationError


def test_valid_pds1_quillan_payload() -> None:
    payload = QrPayload(
        schema="PDS1",
        module="quillan",
        class_id="english12_p4",
        assignment_id="personal_narrative",
        student_id="1001",
        page=1,
        metadata={"doc": "response"},
    )

    assert payload.schema == "PDS1"
    assert payload.module == "quillan"
    assert payload.class_id == "english12_p4"
    assert payload.assignment_id == "personal_narrative"
    assert payload.student_id == "1001"
    assert payload.page == 1
    assert payload.metadata == {"doc": "response"}


def test_valid_pds1_scoreform_payload() -> None:
    payload = QrPayload(
        schema="PDS1",
        module="scoreform",
        class_id="english9_p2",
        assignment_id="rj_act1_quiz",
        student_id="1001",
        page=1,
        metadata={"doc": "answer_sheet"},
    )

    assert payload.metadata == {"doc": "answer_sheet"}


def test_valid_legacy_omr1_payload() -> None:
    payload = QrPayload(
        schema="OMR1",
        module="scoreform",
        class_id="english9_p2",
        assignment_id="rj_act1_quiz",
        student_id="1001",
        page=1,
    )

    assert payload.schema == "OMR1"
    assert payload.module == "scoreform"
    assert payload.metadata == {}


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("schema", {"schema": "PDS 1"}),
        ("module", {"module": "quillan/module"}),
        ("class_id", {"class_id": "../english12_p4"}),
        ("assignment_id", {"assignment_id": "personal|narrative"}),
        ("student_id", {"student_id": "sid=1001"}),
    ],
)
def test_invalid_identifier_fields_raise_error(
    field_name: str,
    kwargs: dict[str, str],
) -> None:
    payload_kwargs = {
        "schema": "PDS1",
        "module": "quillan",
        "class_id": "english12_p4",
        "assignment_id": "personal_narrative",
        "student_id": "1001",
        "page": 1,
    }
    payload_kwargs.update(kwargs)

    with pytest.raises(QrPayloadValidationError, match=field_name):
        QrPayload(**payload_kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("page", [0, -1])
def test_page_must_be_positive(page: int) -> None:
    with pytest.raises(QrPayloadValidationError, match="page"):
        QrPayload(
            schema="PDS1",
            module="quillan",
            class_id="english12_p4",
            assignment_id="personal_narrative",
            student_id="1001",
            page=page,
        )


@pytest.mark.parametrize("page", ["1", 1.5, None])
def test_page_must_be_integer(page: object) -> None:
    with pytest.raises(QrPayloadValidationError, match="page must be an integer"):
        QrPayload(
            schema="PDS1",
            module="quillan",
            class_id="english12_p4",
            assignment_id="personal_narrative",
            student_id="1001",
            page=page,  # type: ignore[arg-type]
        )


def test_metadata_must_be_mapping() -> None:
    with pytest.raises(QrPayloadValidationError, match="metadata must be a mapping"):
        QrPayload(
            schema="PDS1",
            module="quillan",
            class_id="english12_p4",
            assignment_id="personal_narrative",
            student_id="1001",
            page=1,
            metadata=["doc", "response"],  # type: ignore[arg-type]
        )


def test_metadata_keys_must_be_strings() -> None:
    with pytest.raises(QrPayloadValidationError, match="metadata keys must be strings"):
        QrPayload(
            schema="PDS1",
            module="quillan",
            class_id="english12_p4",
            assignment_id="personal_narrative",
            student_id="1001",
            page=1,
            metadata={1: "response"},  # type: ignore[dict-item]
        )


def test_metadata_values_must_be_strings() -> None:
    with pytest.raises(QrPayloadValidationError, match="metadata values must be strings"):
        QrPayload(
            schema="PDS1",
            module="quillan",
            class_id="english12_p4",
            assignment_id="personal_narrative",
            student_id="1001",
            page=1,
            metadata={"doc": 1},  # type: ignore[dict-item]
        )


@pytest.mark.parametrize(
    "reserved_key",
    [
        "schema",
        "module",
        "class",
        "class_id",
        "aid",
        "assignment_id",
        "sid",
        "student_id",
        "page",
    ],
)
def test_reserved_metadata_keys_raise_error(reserved_key: str) -> None:
    with pytest.raises(QrPayloadValidationError, match="reserved"):
        QrPayload(
            schema="PDS1",
            module="quillan",
            class_id="english12_p4",
            assignment_id="personal_narrative",
            student_id="1001",
            page=1,
            metadata={reserved_key: "value"},
        )


def test_invalid_metadata_key_raises_error() -> None:
    with pytest.raises(QrPayloadValidationError, match="metadata key"):
        QrPayload(
            schema="PDS1",
            module="quillan",
            class_id="english12_p4",
            assignment_id="personal_narrative",
            student_id="1001",
            page=1,
            metadata={"doc type": "response"},
        )


def test_invalid_metadata_value_raises_error() -> None:
    with pytest.raises(QrPayloadValidationError, match="metadata value"):
        QrPayload(
            schema="PDS1",
            module="quillan",
            class_id="english12_p4",
            assignment_id="personal_narrative",
            student_id="1001",
            page=1,
            metadata={"doc": "written response"},
        )