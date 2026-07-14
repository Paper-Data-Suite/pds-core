"""Tests for the strict PDS2 page-locator payload contract."""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from pds_core.pds2 import (
    PDS2_FIELD_ORDER,
    PDS2_MAX_PAYLOAD_BYTES,
    PDS2_RECOMMENDED_PAYLOAD_BYTES,
    PDS2_REQUIRED_FIELDS,
    Pds2PayloadError,
    parse_pds2_payload,
    serialize_pds2_payload,
)
from pds_core.routing_models import (
    PDS2_SCHEMA,
    ROUTE_REGISTRATION_SCHEMA_VERSION,
    ModuleRecordRef,
    ModuleWorkRef,
    RouteLocator,
    RouteRegistration,
    RouteResolution,
    RoutingModelError,
)

CANONICAL_PAYLOAD = (
    "PDS2|m=concord|c=english10_p3|w=socratic_seminar_1|"
    "r=rt_0123456789abcdef0123456789abcdef"
)
FIELD_SEGMENTS = (
    "m=concord",
    "c=english10_p3",
    "w=socratic_seminar_1",
    "r=rt_0123456789abcdef0123456789abcdef",
)


def _locator() -> RouteLocator:
    return RouteLocator(
        schema=PDS2_SCHEMA,
        work=ModuleWorkRef(
            module_id="concord",
            class_id="english10_p3",
            work_id="socratic_seminar_1",
        ),
        route_id="rt_0123456789abcdef0123456789abcdef",
    )


def _payload_for_size(payload_size: int) -> str:
    fixed_payload = "PDS2|m=m|c=c|w=w|r="
    return fixed_payload + "r" * (payload_size - len(fixed_payload))


def _locator_for_payload_size(payload_size: int) -> RouteLocator:
    payload = _payload_for_size(payload_size)
    return RouteLocator(
        schema=PDS2_SCHEMA,
        work=ModuleWorkRef(module_id="m", class_id="c", work_id="w"),
        route_id=payload.removeprefix("PDS2|m=m|c=c|w=w|r="),
    )


def _unsafe_locator(
    *, schema: object = PDS2_SCHEMA, work: object | None = None, route_id: object = "route_1"
) -> RouteLocator:
    value = object.__new__(RouteLocator)
    object.__setattr__(value, "schema", schema)
    object.__setattr__(
        value,
        "work",
        work
        if work is not None
        else ModuleWorkRef(module_id="concord", class_id="class_1", work_id="work_1"),
    )
    object.__setattr__(value, "route_id", route_id)
    return value


def test_pds2_public_constants_are_exact() -> None:
    assert PDS2_FIELD_ORDER == ("m", "c", "w", "r")
    assert PDS2_REQUIRED_FIELDS == frozenset({"m", "c", "w", "r"})
    assert PDS2_MAX_PAYLOAD_BYTES == 256
    assert PDS2_RECOMMENDED_PAYLOAD_BYTES == 160


def test_parse_pds2_payload_returns_route_locator() -> None:
    locator = parse_pds2_payload(CANONICAL_PAYLOAD)

    assert locator == _locator()
    assert locator.schema == PDS2_SCHEMA
    assert locator.module_id == "concord"
    assert locator.class_id == "english10_p3"
    assert locator.work_id == "socratic_seminar_1"
    assert locator.route_id == "rt_0123456789abcdef0123456789abcdef"


@pytest.mark.parametrize("segments", tuple(itertools.permutations(FIELD_SEGMENTS)))
def test_parse_pds2_payload_accepts_every_field_order(
    segments: tuple[str, ...],
) -> None:
    assert parse_pds2_payload("PDS2|" + "|".join(segments)) == _locator()


def test_serialize_pds2_payload_uses_canonical_order() -> None:
    assert serialize_pds2_payload(_locator()) == CANONICAL_PAYLOAD


def test_pds2_round_trip_is_canonical() -> None:
    noncanonical = "PDS2|r=route_1|w=work_1|m=concord|c=class_1"

    assert serialize_pds2_payload(parse_pds2_payload(noncanonical)) == (
        "PDS2|m=concord|c=class_1|w=work_1|r=route_1"
    )


@pytest.mark.parametrize(
    "value",
    [
        b"PDS2",
        bytearray(b"PDS2"),
        memoryview(b"PDS2"),
        1,
        {},
        [],
        None,
        object(),
    ],
)
def test_parse_pds2_payload_rejects_non_string_input(value: object) -> None:
    with pytest.raises(Pds2PayloadError, match="string"):
        parse_pds2_payload(value)  # type: ignore[arg-type]


def test_parse_pds2_payload_rejects_empty_input() -> None:
    with pytest.raises(Pds2PayloadError, match="empty"):
        parse_pds2_payload("")


@pytest.mark.parametrize(
    "payload",
    [
        "PDS1|m=concord|c=class_1|w=work_1|r=route_1",
        "OMR1|m=concord|c=class_1|w=work_1|r=route_1",
        "PDS3|m=concord|c=class_1|w=work_1|r=route_1",
        "pds2|m=concord|c=class_1|w=work_1|r=route_1",
        "Pds2|m=concord|c=class_1|w=work_1|r=route_1",
        " PDS2|m=concord|c=class_1|w=work_1|r=route_1",
        "PDS2 ",
    ],
)
def test_parse_pds2_payload_rejects_unsupported_schema(payload: str) -> None:
    with pytest.raises(Pds2PayloadError, match="[Uu]nsupported.*schema"):
        parse_pds2_payload(payload)


@pytest.mark.parametrize(
    "payload",
    [
        "PDS２|m=concord|c=class_1|w=work_1|r=route_1",
        "PDS2|ｍ=concord|c=class_1|w=work_1|r=route_1",
        "PDS2|m=café|c=class_1|w=work_1|r=route_1",
        "PDS2|m=concord|c=cláss_1|w=work_1|r=route_1",
        "PDS2|m=concord|c=class_1|w=wörk_1|r=route_1",
        "PDS2|m=concord|c=class_1|w=work_1|r=route😀",
        "—PDS2|m=concord|c=class_1|w=work_1|r=route_1—",
        "PDS2｜m=concord｜c=class_1｜w=work_1｜r=route_1",
        "PDS2|m＝concord|c=class_1|w=work_1|r=route_1",
    ],
)
def test_parse_pds2_payload_rejects_non_ascii_content(payload: str) -> None:
    with pytest.raises(Pds2PayloadError, match="ASCII") as caught:
        parse_pds2_payload(payload)

    assert isinstance(caught.value.__cause__, UnicodeEncodeError)


@pytest.mark.parametrize(
    ("payload_size", "is_valid"),
    [(159, True), (160, True), (161, True), (255, True), (256, True), (257, False)],
)
def test_parse_pds2_payload_enforces_exact_size_boundaries(
    payload_size: int, is_valid: bool
) -> None:
    locator = _locator_for_payload_size(payload_size)
    payload = _payload_for_size(payload_size)
    assert len(payload.encode("ascii")) == payload_size

    if is_valid:
        assert parse_pds2_payload(payload) == locator
    else:
        with pytest.raises(Pds2PayloadError, match="256.*bytes"):
            parse_pds2_payload(payload)


def test_parse_checks_size_before_detailed_segment_validation() -> None:
    malformed_over_limit = "PDS2|" + "not-a-field" * 23
    assert len(malformed_over_limit.encode("ascii")) > PDS2_MAX_PAYLOAD_BYTES

    with pytest.raises(Pds2PayloadError, match="maximum size"):
        parse_pds2_payload(malformed_over_limit)


@pytest.mark.parametrize(
    "payload",
    [
        "PDS2|",
        "PDS2||m=concord|c=class_1|w=work_1|r=route_1",
        "PDS2|m=concord|c=class_1|w=work_1|r=route_1|",
    ],
)
def test_parse_pds2_payload_rejects_empty_segments(payload: str) -> None:
    with pytest.raises(Pds2PayloadError, match="empty segment"):
        parse_pds2_payload(payload)


@pytest.mark.parametrize(
    "segment", ["m", "m=concord=extra", "m:concord", "m==concord"]
)
def test_parse_pds2_payload_rejects_malformed_segments(segment: str) -> None:
    payload = f"PDS2|{segment}|c=class_1|w=work_1|r=route_1"

    with pytest.raises(Pds2PayloadError, match="exactly one"):
        parse_pds2_payload(payload)


def test_parse_pds2_payload_rejects_empty_key() -> None:
    with pytest.raises(Pds2PayloadError, match="empty key"):
        parse_pds2_payload("PDS2|=concord|c=class_1|w=work_1|r=route_1")


@pytest.mark.parametrize("field", PDS2_FIELD_ORDER)
def test_parse_pds2_payload_rejects_empty_values(field: str) -> None:
    values = {"m": "concord", "c": "class_1", "w": "work_1", "r": "route_1"}
    values[field] = ""
    payload = "PDS2|" + "|".join(f"{key}={values[key]}" for key in PDS2_FIELD_ORDER)

    with pytest.raises(Pds2PayloadError, match="empty value"):
        parse_pds2_payload(payload)


@pytest.mark.parametrize("field", PDS2_FIELD_ORDER)
def test_parse_pds2_payload_rejects_duplicate_fields(field: str) -> None:
    payload = CANONICAL_PAYLOAD + f"|{field}=duplicate"

    with pytest.raises(Pds2PayloadError, match=f"duplicate field '{field}'"):
        parse_pds2_payload(payload)


def test_parse_pds2_payload_rejects_duplicate_field_with_identical_value() -> None:
    payload = "PDS2|m=concord|c=class_1|w=work_1|r=route_1|m=concord"

    with pytest.raises(Pds2PayloadError, match="duplicate field 'm'"):
        parse_pds2_payload(payload)


@pytest.mark.parametrize(
    "field",
    [
        "module=concord",
        "class=class_1",
        "work=work_1",
        "route=route_1",
        "module_id=concord",
        "assignment_id=assignment_1",
        "student_id=student_1",
        "page=1",
        "metadata=value",
        "M=concord",
    ],
)
def test_parse_pds2_payload_rejects_unknown_and_legacy_fields(field: str) -> None:
    with pytest.raises(Pds2PayloadError, match="unknown field"):
        parse_pds2_payload(CANONICAL_PAYLOAD + f"|{field}")


@pytest.mark.parametrize("missing", PDS2_FIELD_ORDER)
def test_parse_pds2_payload_rejects_missing_fields(missing: str) -> None:
    segments = [segment for segment in FIELD_SEGMENTS if not segment.startswith(f"{missing}=")]

    with pytest.raises(Pds2PayloadError, match=f"missing required field.*{missing}"):
        parse_pds2_payload("PDS2|" + "|".join(segments))


@pytest.mark.parametrize(
    ("payload", "ordered_missing"),
    [("PDS2|m=concord", "c, w, r"), ("PDS2", "m, c, w, r")],
)
def test_parse_pds2_payload_reports_multiple_missing_fields_in_canonical_order(
    payload: str, ordered_missing: str
) -> None:
    with pytest.raises(Pds2PayloadError, match="missing required field") as caught:
        parse_pds2_payload(payload)

    assert ordered_missing in str(caught.value)


@pytest.mark.parametrize(
    "payload",
    [
        " PDS2|m=concord|c=class_1|w=work_1|r=route_1",
        "PDS2|m=concord|c=class_1|w=work_1|r=route_1 ",
        "PDS2|m =concord|c=class_1|w=work_1|r=route_1",
        "PDS2|m=concord |c=class_1|w=work_1|r=route_1",
        "PDS2|m=Concord|c=class_1|w=work_1|r=route_1",
        "PDS2|m=concord|c=class%5F1|w=work_1|r=route_1",
        "PDS2|m=concord|c=class 1|w=work_1|r=route_1",
        "PDS2|m:concord|c=class_1|w=work_1|r=route_1",
        "PDS2;m=concord;c=class_1;w=work_1;r=route_1",
        "PDS2｜m=concord｜c=class_1｜w=work_1｜r=route_1",
        'PDS2|m="concord"|c=class_1|w=work_1|r=route_1',
    ],
)
def test_parse_pds2_payload_does_not_normalize_input(payload: str) -> None:
    with pytest.raises(Pds2PayloadError):
        parse_pds2_payload(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("m", "Concord", "module_id.*lowercase"),
        ("m", "con cord", "module_id.*letters"),
        ("c", "class.1", "class_id.*letters"),
        ("w", "../work", "work_id.*letters"),
        ("r", "route%201", "route_id.*letters"),
        ("r", " route_1", "route_id.*whitespace"),
    ],
)
def test_parse_pds2_payload_wraps_invalid_identifiers(
    field: str, value: str, message: str
) -> None:
    values = {"m": "concord", "c": "class_1", "w": "work_1", "r": "route_1"}
    values[field] = value
    payload = "PDS2|" + "|".join(f"{key}={values[key]}" for key in PDS2_FIELD_ORDER)

    with pytest.raises(Pds2PayloadError, match=message) as caught:
        parse_pds2_payload(payload)

    assert isinstance(caught.value.__cause__, RoutingModelError)


@pytest.mark.parametrize(
    "attribute",
    [
        "student_id",
        "assignment_id",
        "page",
        "metadata",
        "template",
        "submission_dir",
        "Author",
        "Subject",
        "Score",
    ],
)
def test_parsed_locator_excludes_legacy_semantics(attribute: str) -> None:
    assert not hasattr(parse_pds2_payload(CANONICAL_PAYLOAD), attribute)


@pytest.mark.parametrize(
    ("payload_size", "is_valid"),
    [(159, True), (160, True), (161, True), (255, True), (256, True), (257, False)],
)
def test_serialize_pds2_payload_enforces_exact_size_boundaries(
    payload_size: int, is_valid: bool
) -> None:
    locator = _locator_for_payload_size(payload_size)

    if is_valid:
        payload = serialize_pds2_payload(locator)
        assert len(payload.encode("ascii")) == payload_size
    else:
        with pytest.raises(Pds2PayloadError, match="256.*bytes"):
            serialize_pds2_payload(locator)


def test_serialize_pds2_payload_rejects_mapping_and_string() -> None:
    for value in ({}, CANONICAL_PAYLOAD):  # type: object
        with pytest.raises(Pds2PayloadError, match="RouteLocator"):
            serialize_pds2_payload(value)  # type: ignore[arg-type]


def test_serialize_pds2_payload_rejects_module_work_ref() -> None:
    work = ModuleWorkRef(module_id="concord", class_id="class_1", work_id="work_1")
    with pytest.raises(Pds2PayloadError, match="RouteLocator"):
        serialize_pds2_payload(work)  # type: ignore[arg-type]


def test_serialize_pds2_payload_rejects_registration_and_resolution(tmp_path: Path) -> None:
    locator = _locator()
    registration = RouteRegistration(
        schema_version=ROUTE_REGISTRATION_SCHEMA_VERSION,
        locator=locator,
        target=ModuleRecordRef(
            module_id="concord", record_kind="artifact_page", record_id="record_1"
        ),
        created_at="2026-07-14T09:00:00-04:00",
        status="active",
        human_fallback="PDS2 route",
    )
    resolution = RouteResolution(
        locator=locator,
        registration=registration,
        class_root=tmp_path / "class",
        module_root=tmp_path / "module",
        work_root=tmp_path / "work",
    )

    for value in (registration, resolution):
        with pytest.raises(Pds2PayloadError, match="RouteLocator"):
            serialize_pds2_payload(value)  # type: ignore[arg-type]


def test_serialize_pds2_payload_rejects_arbitrary_object() -> None:
    with pytest.raises(Pds2PayloadError, match="RouteLocator"):
        serialize_pds2_payload(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "locator",
    [
        _unsafe_locator(schema="PDS1"),
        _unsafe_locator(work={"module_id": "concord"}),
        _unsafe_locator(route_id="invalid route"),
    ],
)
def test_serialize_pds2_payload_wraps_model_validation_failures(
    locator: RouteLocator,
) -> None:
    with pytest.raises(Pds2PayloadError) as caught:
        serialize_pds2_payload(locator)

    assert isinstance(caught.value.__cause__, RoutingModelError)
