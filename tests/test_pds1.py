"""Tests for PDS1 QR payload parsing and building."""

from __future__ import annotations

import pytest

from pds_core.pds1 import Pds1PayloadError, build_pds1_payload, parse_pds1_payload
from pds_core.qr_payload import QrPayload


def test_build_minimal_pds1_payload() -> None:
    payload = QrPayload(
        schema="PDS1",
        module="quillan",
        class_id="english12_p4",
        assignment_id="personal_narrative",
        student_id="1001",
        page=1,
    )

    result = build_pds1_payload(payload)

    assert (
        result
        == "PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=1"
    )


def test_build_pds1_payload_with_metadata() -> None:
    payload = QrPayload(
        schema="PDS1",
        module="quillan",
        class_id="english12_p4",
        assignment_id="personal_narrative",
        student_id="1001",
        page=2,
        metadata={
            "template": "lined_response_v1",
            "doc": "response",
            "pages": "3",
        },
    )

    result = build_pds1_payload(payload)

    assert (
        result
        == "PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=2|doc=response|pages=3|template=lined_response_v1"
    )


def test_build_rejects_non_pds1_schema() -> None:
    payload = QrPayload(
        schema="OMR1",
        module="scoreform",
        class_id="english9_p2",
        assignment_id="rj_act1_quiz",
        student_id="1001",
        page=1,
    )

    with pytest.raises(Pds1PayloadError, match="Cannot build PDS1 payload"):
        build_pds1_payload(payload)


def test_parse_minimal_pds1_payload() -> None:
    payload = parse_pds1_payload(
        "PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=1"
    )

    assert payload == QrPayload(
        schema="PDS1",
        module="quillan",
        class_id="english12_p4",
        assignment_id="personal_narrative",
        student_id="1001",
        page=1,
    )


def test_parse_pds1_payload_with_metadata() -> None:
    payload = parse_pds1_payload(
        "PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=2|doc=response|pages=3|template=lined_response_v1"
    )

    assert payload == QrPayload(
        schema="PDS1",
        module="quillan",
        class_id="english12_p4",
        assignment_id="personal_narrative",
        student_id="1001",
        page=2,
        metadata={
            "doc": "response",
            "pages": "3",
            "template": "lined_response_v1",
        },
    )


def test_parse_build_round_trip() -> None:
    original = QrPayload(
        schema="PDS1",
        module="scoreform",
        class_id="english9_p2",
        assignment_id="rj_act1_quiz",
        student_id="1001",
        page=1,
        metadata={"doc": "answer_sheet"},
    )

    built = build_pds1_payload(original)
    parsed = parse_pds1_payload(built)

    assert parsed == original


@pytest.mark.parametrize(
    "payload_text",
    [
        "OMR1|class=english9_p2|aid=rj_act1_quiz|sid=1001",
        "PDS2|module=quillan|class=english12_p4|aid=test|sid=1001|page=1",
        "",
    ],
)
def test_parse_rejects_invalid_prefix_or_empty_payload(payload_text: str) -> None:
    with pytest.raises(Pds1PayloadError):
        parse_pds1_payload(payload_text)


def test_parse_rejects_non_string_input() -> None:
    with pytest.raises(Pds1PayloadError, match="must be a string"):
        parse_pds1_payload(123)  # type: ignore[arg-type]


def test_parse_rejects_payload_with_no_fields() -> None:
    with pytest.raises(Pds1PayloadError, match="must include key=value fields"):
        parse_pds1_payload("PDS1")


@pytest.mark.parametrize(
    "payload_text",
    [
        "PDS1|module=quillan|",
        "PDS1|module=quillan||class=english12_p4",
    ],
)
def test_parse_rejects_empty_segments(payload_text: str) -> None:
    with pytest.raises(Pds1PayloadError, match="empty segment"):
        parse_pds1_payload(payload_text)


def test_parse_rejects_malformed_segment() -> None:
    with pytest.raises(Pds1PayloadError, match="key=value"):
        parse_pds1_payload("PDS1|module=quillan|class")


def test_parse_rejects_empty_key() -> None:
    with pytest.raises(Pds1PayloadError, match="empty key"):
        parse_pds1_payload("PDS1|=quillan|class=english12_p4|aid=test|sid=1001|page=1")


def test_parse_rejects_empty_value() -> None:
    with pytest.raises(Pds1PayloadError, match="must not be empty"):
        parse_pds1_payload("PDS1|module=|class=english12_p4|aid=test|sid=1001|page=1")


def test_parse_rejects_duplicate_fields() -> None:
    with pytest.raises(Pds1PayloadError, match="duplicate field 'module'"):
        parse_pds1_payload(
            "PDS1|module=quillan|module=scoreform|class=english12_p4|aid=test|sid=1001|page=1"
        )


def test_parse_rejects_missing_required_field() -> None:
    with pytest.raises(Pds1PayloadError, match="missing required field"):
        parse_pds1_payload("PDS1|module=quillan|class=english12_p4|sid=1001|page=1")


@pytest.mark.parametrize(
    "payload_text",
    [
        "PDS1|module=quillan|class=English 12|aid=personal_narrative|sid=1001|page=1",
        "PDS1|module=quillan|class=english12_p4|aid=personal|narrative|sid=1001|page=1",
        "PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=sid=1001|page=1",
    ],
)
def test_parse_rejects_invalid_identifier_values(payload_text: str) -> None:
    with pytest.raises(Pds1PayloadError):
        parse_pds1_payload(payload_text)


@pytest.mark.parametrize(
    "payload_text",
    [
        "PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=zero",
        "PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=0",
        "PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=-1",
    ],
)
def test_parse_rejects_invalid_page_values(payload_text: str) -> None:
    with pytest.raises(Pds1PayloadError, match="page"):
        parse_pds1_payload(payload_text)


def test_parse_rejects_reserved_metadata_key() -> None:
    with pytest.raises(Pds1PayloadError, match="reserved"):
        parse_pds1_payload(
            "PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=1|class_id=other"
        )