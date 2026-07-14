"""Strict parsing and canonical serialization for PDS2 page locators."""

from __future__ import annotations

from typing import Final

from pds_core.routing_models import (
    PDS2_SCHEMA,
    ModuleWorkRef,
    RouteLocator,
    RoutingModelError,
    validate_route_locator,
)

PDS2_FIELD_ORDER: Final[tuple[str, ...]] = ("m", "c", "w", "r")
PDS2_REQUIRED_FIELDS: Final[frozenset[str]] = frozenset(PDS2_FIELD_ORDER)
PDS2_MAX_PAYLOAD_BYTES: Final[int] = 256
PDS2_RECOMMENDED_PAYLOAD_BYTES: Final[int] = 160


class Pds2PayloadError(ValueError):
    """Raised when a PDS2 payload cannot be parsed or serialized."""


def parse_pds2_payload(payload_text: str) -> RouteLocator:
    """Parse a strict PDS2 payload into a validated route locator."""
    if not isinstance(payload_text, str):
        raise Pds2PayloadError("PDS2 payload must be a string.")
    if payload_text == "":
        raise Pds2PayloadError("PDS2 payload must not be empty.")

    payload_bytes = _encode_ascii(payload_text)
    _require_size_limit(payload_bytes)

    segments = payload_text.split("|")
    if segments[0] != PDS2_SCHEMA:
        raise Pds2PayloadError(
            f"Unsupported payload schema {segments[0]!r}; expected {PDS2_SCHEMA!r}."
        )

    fields: dict[str, str] = {}
    for segment in segments[1:]:
        if segment == "":
            raise Pds2PayloadError("PDS2 payload contains an empty segment.")
        if segment.count("=") != 1:
            raise Pds2PayloadError(
                f"PDS2 payload segment {segment!r} must contain exactly one '='."
            )

        key, value = segment.split("=", 1)
        if key == "":
            raise Pds2PayloadError("PDS2 payload contains an empty key.")
        if value == "":
            raise Pds2PayloadError(
                f"PDS2 payload field {key!r} must not have an empty value."
            )
        if key not in PDS2_REQUIRED_FIELDS:
            raise Pds2PayloadError(
                f"PDS2 payload contains unknown field {key!r}."
            )
        if key in fields:
            raise Pds2PayloadError(
                f"PDS2 payload contains duplicate field {key!r}."
            )
        fields[key] = value

    missing = [key for key in PDS2_FIELD_ORDER if key not in fields]
    if missing:
        raise Pds2PayloadError(
            "PDS2 payload is missing required field(s): " + ", ".join(missing) + "."
        )

    try:
        return RouteLocator(
            schema=PDS2_SCHEMA,
            work=ModuleWorkRef(
                module_id=fields["m"],
                class_id=fields["c"],
                work_id=fields["w"],
            ),
            route_id=fields["r"],
        )
    except RoutingModelError as error:
        raise Pds2PayloadError(str(error)) from error


def serialize_pds2_payload(locator: RouteLocator) -> str:
    """Serialize a validated route locator in canonical PDS2 field order."""
    if not isinstance(locator, RouteLocator):
        raise Pds2PayloadError("PDS2 serialization requires a RouteLocator.")

    try:
        validated = validate_route_locator(locator)
    except RoutingModelError as error:
        raise Pds2PayloadError(str(error)) from error
    except (AttributeError, ValueError) as error:
        raise Pds2PayloadError("RouteLocator is not valid.") from error

    payload_text = (
        f"{PDS2_SCHEMA}|m={validated.module_id}|c={validated.class_id}"
        f"|w={validated.work_id}|r={validated.route_id}"
    )
    payload_bytes = _encode_ascii(payload_text)
    _require_size_limit(payload_bytes)
    return payload_text


def _encode_ascii(payload_text: str) -> bytes:
    try:
        return payload_text.encode("ascii")
    except UnicodeEncodeError as error:
        raise Pds2PayloadError("PDS2 payload must contain only ASCII content.") from error


def _require_size_limit(payload_bytes: bytes) -> None:
    payload_size = len(payload_bytes)
    if payload_size > PDS2_MAX_PAYLOAD_BYTES:
        raise Pds2PayloadError(
            "PDS2 payload exceeds the maximum size of "
            f"{PDS2_MAX_PAYLOAD_BYTES} ASCII bytes ({payload_size} bytes)."
        )
