"""PDS1 QR payload parsing and building."""

from __future__ import annotations

from typing import Final

from pds_core.qr_payload import QrPayload, QrPayloadValidationError

PDS1_SCHEMA: Final[str] = "PDS1"
PDS1_REQUIRED_FIELDS: Final[set[str]] = {"module", "class", "aid", "sid", "page"}


class Pds1PayloadError(ValueError):
    """Raised when a PDS1 payload string is missing or invalid."""


def build_pds1_payload(payload: QrPayload) -> str:
    """Build a canonical PDS1 payload string from normalized QR payload data."""
    if payload.schema != PDS1_SCHEMA:
        raise Pds1PayloadError(
            f"Cannot build PDS1 payload from schema '{payload.schema}'."
        )

    parts = [
        PDS1_SCHEMA,
        f"module={payload.module}",
        f"class={payload.class_id}",
        f"aid={payload.assignment_id}",
        f"sid={payload.student_id}",
        f"page={payload.page}",
    ]

    for key in sorted(payload.metadata):
        parts.append(f"{key}={payload.metadata[key]}")

    return "|".join(parts)


def parse_pds1_payload(payload_text: str) -> QrPayload:
    """Parse a PDS1 payload string into normalized QR payload data."""
    if not isinstance(payload_text, str):
        raise Pds1PayloadError("PDS1 payload must be a string.")

    if payload_text == "":
        raise Pds1PayloadError("PDS1 payload must not be empty.")

    segments = payload_text.split("|")

    if segments[0] != PDS1_SCHEMA:
        raise Pds1PayloadError("PDS1 payload must start with 'PDS1'.")

    if len(segments) == 1:
        raise Pds1PayloadError("PDS1 payload must include key=value fields.")

    fields: dict[str, str] = {}

    for segment in segments[1:]:
        if segment == "":
            raise Pds1PayloadError("PDS1 payload contains an empty segment.")

        if "=" not in segment:
            raise Pds1PayloadError(
                f"PDS1 payload segment '{segment}' must use key=value format."
            )

        key, value = segment.split("=", maxsplit=1)

        if key == "":
            raise Pds1PayloadError("PDS1 payload contains an empty key.")

        if value == "":
            raise Pds1PayloadError(f"PDS1 payload field '{key}' must not be empty.")

        if key in fields:
            raise Pds1PayloadError(f"PDS1 payload contains duplicate field '{key}'.")

        fields[key] = value

    missing_fields = sorted(PDS1_REQUIRED_FIELDS - fields.keys())
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise Pds1PayloadError(f"PDS1 payload is missing required field(s): {missing}.")

    try:
        page = int(fields["page"])
    except ValueError as error:
        raise Pds1PayloadError("PDS1 payload field 'page' must be an integer.") from error

    metadata = {
        key: value
        for key, value in fields.items()
        if key not in PDS1_REQUIRED_FIELDS
    }

    try:
        return QrPayload(
            schema=PDS1_SCHEMA,
            module=fields["module"],
            class_id=fields["class"],
            assignment_id=fields["aid"],
            student_id=fields["sid"],
            page=page,
            metadata=metadata,
        )
    except QrPayloadValidationError as error:
        raise Pds1PayloadError(str(error)) from error