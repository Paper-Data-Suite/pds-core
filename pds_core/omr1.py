"""Legacy OMR1 QR payload parsing for ScoreForm compatibility."""

from __future__ import annotations

from typing import Final

from pds_core.qr_payload import QrPayload, QrPayloadValidationError

OMR1_SCHEMA: Final[str] = "OMR1"
OMR1_MODULE: Final[str] = "scoreform"
OMR1_REQUIRED_FIELDS: Final[set[str]] = {"class", "aid", "sid"}


class Omr1PayloadError(ValueError):
    """Raised when a legacy OMR1 payload string is missing or invalid."""


def parse_omr1_payload(payload_text: str) -> QrPayload:
    """Parse a legacy OMR1 payload string into normalized QR payload data."""
    if not isinstance(payload_text, str):
        raise Omr1PayloadError("OMR1 payload must be a string.")

    if payload_text == "":
        raise Omr1PayloadError("OMR1 payload must not be empty.")

    segments = payload_text.split("|")

    if segments[0] != OMR1_SCHEMA:
        raise Omr1PayloadError("OMR1 payload must start with 'OMR1'.")

    if len(segments) == 1:
        raise Omr1PayloadError("OMR1 payload must include key=value fields.")

    fields: dict[str, str] = {}

    for segment in segments[1:]:
        if segment == "":
            raise Omr1PayloadError("OMR1 payload contains an empty segment.")

        if "=" not in segment:
            raise Omr1PayloadError(
                f"OMR1 payload segment '{segment}' must use key=value format."
            )

        key, value = segment.split("=", maxsplit=1)

        if key == "":
            raise Omr1PayloadError("OMR1 payload contains an empty key.")

        if value == "":
            raise Omr1PayloadError(f"OMR1 payload field '{key}' must not be empty.")

        if key in fields:
            raise Omr1PayloadError(f"OMR1 payload contains duplicate field '{key}'.")

        fields[key] = value

    unknown_fields = sorted(set(fields) - OMR1_REQUIRED_FIELDS)
    if unknown_fields:
        unknown = ", ".join(unknown_fields)
        raise Omr1PayloadError(f"OMR1 payload contains unknown field(s): {unknown}.")

    missing_fields = sorted(OMR1_REQUIRED_FIELDS - fields.keys())
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise Omr1PayloadError(f"OMR1 payload is missing required field(s): {missing}.")

    try:
        return QrPayload(
            schema=OMR1_SCHEMA,
            module=OMR1_MODULE,
            class_id=fields["class"],
            assignment_id=fields["aid"],
            student_id=fields["sid"],
            page=1,
        )
    except QrPayloadValidationError as error:
        raise Omr1PayloadError(str(error)) from error