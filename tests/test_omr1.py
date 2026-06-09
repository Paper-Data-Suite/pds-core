"""Tests for legacy OMR1 QR payload parsing."""

from __future__ import annotations

import pytest

from pds_core.omr1 import Omr1PayloadError, parse_omr1_payload
from pds_core.qr_payload import QrPayload


def test_parse_valid_omr1_payload() -> None:
    payload = parse_omr1_payload("OMR1|class=english9_p2|aid=rj_act1_quiz|sid=1001")

    assert payload == QrPayload(
        schema="OMR1",
        module="scoreform",
        class_id="english9_p2",
        assignment_id="rj_act1_quiz",
        student_id="1001",
        page=1,
    )


def test_parse_valid_omr1_payload_with_student_identifier() -> None:
    payload = parse_omr1_payload("OMR1|class=apcsp_p1|aid=unit_3_quiz|sid=stu_0001")

    assert payload == QrPayload(
        schema="OMR1",
        module="scoreform",
        class_id="apcsp_p1",
        assignment_id="unit_3_quiz",
        student_id="stu_0001",
        page=1,
    )


def test_parse_omr1_field_order_does_not_matter() -> None:
    payload = parse_omr1_payload("OMR1|sid=1001|aid=rj_act1_quiz|class=english9_p2")

    assert payload == QrPayload(
        schema="OMR1",
        module="scoreform",
        class_id="english9_p2",
        assignment_id="rj_act1_quiz",
        student_id="1001",
        page=1,
    )


@pytest.mark.parametrize(
    "payload_text",
    [
        "PDS1|module=scoreform|class=english9_p2|aid=rj_act1_quiz|sid=1001|page=1",
        "OMR2|class=english9_p2|aid=rj_act1_quiz|sid=1001",
        "",
    ],
)
def test_parse_rejects_invalid_prefix_or_empty_payload(payload_text: str) -> None:
    with pytest.raises(Omr1PayloadError):
        parse_omr1_payload(payload_text)


def test_parse_rejects_non_string_input() -> None:
    with pytest.raises(Omr1PayloadError, match="must be a string"):
        parse_omr1_payload(123)  # type: ignore[arg-type]


def test_parse_rejects_payload_with_no_fields() -> None:
    with pytest.raises(Omr1PayloadError, match="must include key=value fields"):
        parse_omr1_payload("OMR1")


@pytest.mark.parametrize(
    "payload_text",
    [
        "OMR1|class=english9_p2|",
        "OMR1|class=english9_p2||aid=rj_act1_quiz|sid=1001",
    ],
)
def test_parse_rejects_empty_segments(payload_text: str) -> None:
    with pytest.raises(Omr1PayloadError, match="empty segment"):
        parse_omr1_payload(payload_text)


def test_parse_rejects_malformed_segment() -> None:
    with pytest.raises(Omr1PayloadError, match="key=value"):
        parse_omr1_payload("OMR1|class=english9_p2|aid")


def test_parse_rejects_empty_key() -> None:
    with pytest.raises(Omr1PayloadError, match="empty key"):
        parse_omr1_payload("OMR1|=english9_p2|aid=rj_act1_quiz|sid=1001")


def test_parse_rejects_empty_value() -> None:
    with pytest.raises(Omr1PayloadError, match="must not be empty"):
        parse_omr1_payload("OMR1|class=|aid=rj_act1_quiz|sid=1001")


def test_parse_rejects_duplicate_fields() -> None:
    with pytest.raises(Omr1PayloadError, match="duplicate field 'class'"):
        parse_omr1_payload(
            "OMR1|class=english9_p2|class=english10_p1|aid=rj_act1_quiz|sid=1001"
        )


def test_parse_rejects_missing_required_field() -> None:
    with pytest.raises(Omr1PayloadError, match="missing required field"):
        parse_omr1_payload("OMR1|class=english9_p2|sid=1001")


def test_parse_rejects_unknown_field() -> None:
    with pytest.raises(Omr1PayloadError, match="unknown field"):
        parse_omr1_payload("OMR1|class=english9_p2|aid=rj_act1_quiz|sid=1001|page=1")


@pytest.mark.parametrize(
    "payload_text",
    [
        "OMR1|class=English 9|aid=rj_act1_quiz|sid=1001",
        "OMR1|class=english9_p2|aid=rj|act1|sid=1001",
        "OMR1|class=english9_p2|aid=rj_act1_quiz|sid=sid=1001",
        "OMR1|class=../english9_p2|aid=rj_act1_quiz|sid=1001",
    ],
)
def test_parse_rejects_invalid_identifier_values(payload_text: str) -> None:
    with pytest.raises(Omr1PayloadError):
        parse_omr1_payload(payload_text)