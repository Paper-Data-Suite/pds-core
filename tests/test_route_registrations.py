"""Tests for persisted route registrations."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from pds_core.route_registrations import (
    RouteRegistrationIntegrityError,
    RouteRegistrationNotFoundError,
    RouteRegistrationReadError,
    RouteRegistrationWriteError,
    load_route_registration,
    resolve_route_registration,
    write_route_registration,
)
from pds_core.routes import route_registration_path
from pds_core.routing_models import (
    PDS2_SCHEMA,
    ROUTE_REGISTRATION_STATUSES,
    ModuleRecordRef,
    ModuleWorkRef,
    RouteLocator,
    RouteRegistration,
    RoutingModelError,
    route_registration_to_dict,
)


def make_locator(
    *,
    module_id: str = "concord",
    class_id: str = "english10_p3",
    work_id: str = "socratic_seminar_1",
    route_id: str = "rt_0123456789abcdef0123456789abcdef",
) -> RouteLocator:
    return RouteLocator(
        PDS2_SCHEMA,
        ModuleWorkRef(module_id, class_id, work_id),
        route_id,
    )


def make_registration(
    *,
    locator: RouteLocator | None = None,
    status: str = "active",
) -> RouteRegistration:
    locator = locator or make_locator()
    return RouteRegistration(
        schema_version="1",
        locator=locator,
        target=ModuleRecordRef(
            locator.module_id,
            "artifact_page",
            "artifact_page_0123456789abcdef",
            "1",
        ),
        created_at="2026-07-14T09:00:00-04:00",
        status=status,
        human_fallback=(
            "PDS2 | Concord seminar route | "
            "R\u00e9sum\u00e9 for student discussion"
        ),
        module_details={"page": {"logical": 1}, "labels": ["opening", "\u03b1"]},
    )


def write_raw_registration(
    root: Path,
    requested: RouteLocator,
    data: object,
) -> Path:
    path = route_registration_path(root, requested)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_writer_creates_stable_registration_and_loader_round_trips(
    tmp_path: Path,
) -> None:
    registration = make_registration()
    path = write_route_registration(tmp_path, registration)
    expected = json.dumps(
        route_registration_to_dict(registration),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"

    assert path == route_registration_path(tmp_path, registration.locator)
    assert path.read_bytes() == expected.encode("utf-8")
    assert set(json.loads(path.read_text(encoding="utf-8"))) == {
        "schema_version",
        "locator",
        "target",
        "created_at",
        "status",
        "human_fallback",
        "module_details",
    }
    assert load_route_registration(tmp_path, registration.locator) == registration
    assert not (tmp_path / ".pds").exists()
    assert not (tmp_path / "scans").exists()
    assert not (tmp_path / "classes" / "english10_p3" / "class.json").exists()


def test_writer_refuses_identical_second_write(tmp_path: Path) -> None:
    registration = make_registration()
    path = write_route_registration(tmp_path, registration)
    original = path.read_bytes()

    with pytest.raises(RouteRegistrationWriteError, match="already exists"):
        write_route_registration(tmp_path, registration)

    assert path.read_bytes() == original


def test_writer_preserves_preexisting_arbitrary_contents(tmp_path: Path) -> None:
    registration = make_registration()
    path = route_registration_path(tmp_path, registration.locator)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"do not replace\x00this")

    with pytest.raises(RouteRegistrationWriteError):
        write_route_registration(tmp_path, registration)

    assert path.read_bytes() == b"do not replace\x00this"


def test_writer_refuses_different_registration_at_same_locator(
    tmp_path: Path,
) -> None:
    first = make_registration()
    second = RouteRegistration(
        schema_version=first.schema_version,
        locator=first.locator,
        target=ModuleRecordRef("concord", "artifact_page", "different_page", "1"),
        created_at=first.created_at,
        status=first.status,
        human_fallback=first.human_fallback,
        module_details={},
    )
    path = write_route_registration(tmp_path, first)
    original = path.read_bytes()

    with pytest.raises(RouteRegistrationWriteError):
        write_route_registration(tmp_path, second)

    assert path.read_bytes() == original


def test_writer_cleans_up_file_after_handled_completion_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registration = make_registration()
    path = route_registration_path(tmp_path, registration.locator)

    def fail_fsync(file_descriptor: int) -> None:
        raise OSError(f"cannot sync {file_descriptor}")

    monkeypatch.setattr(os, "fsync", fail_fsync)
    with pytest.raises(RouteRegistrationWriteError) as raised:
        write_route_registration(tmp_path, registration)

    assert isinstance(raised.value.__cause__, OSError)
    assert not path.exists()


def test_writer_wraps_blocked_parent_path(tmp_path: Path) -> None:
    (tmp_path / "classes").write_text("blocked", encoding="utf-8")
    with pytest.raises(RouteRegistrationWriteError) as raised:
        write_route_registration(tmp_path, make_registration())
    assert isinstance(raised.value.__cause__, OSError)


def test_writer_uses_concurrency_safe_exclusive_creation(tmp_path: Path) -> None:
    registration = make_registration()

    def attempt() -> Path | RouteRegistrationWriteError:
        try:
            return write_route_registration(tmp_path, registration)
        except RouteRegistrationWriteError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: attempt(), range(2)))

    assert sum(isinstance(value, Path) for value in outcomes) == 1
    assert sum(isinstance(value, RouteRegistrationWriteError) for value in outcomes) == 1
    assert load_route_registration(tmp_path, registration.locator) == registration


@pytest.mark.parametrize("value", [{}, "registration", object()])
def test_writer_requires_actual_registration(tmp_path: Path, value: object) -> None:
    with pytest.raises(RoutingModelError, match="RouteRegistration"):
        write_route_registration(tmp_path, value)  # type: ignore[arg-type]
    assert not (tmp_path / "classes").exists()


def test_loader_reports_missing_canonical_file(tmp_path: Path) -> None:
    with pytest.raises(RouteRegistrationNotFoundError) as raised:
        load_route_registration(tmp_path, make_locator())
    assert isinstance(raised.value.__cause__, FileNotFoundError)


@pytest.mark.parametrize(
    "location",
    [
        Path("elsewhere/route.json"),
        Path("classes/english10_p3/assignments/socratic_seminar_1/routes/route.json"),
        Path("classes/other/modules/concord/work/socratic_seminar_1/routes/route.json"),
    ],
)
def test_loader_never_searches_other_locations(tmp_path: Path, location: Path) -> None:
    path = tmp_path / location
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(route_registration_to_dict(make_registration())),
        encoding="utf-8",
    )
    with pytest.raises(RouteRegistrationNotFoundError):
        load_route_registration(tmp_path, make_locator())


@pytest.mark.parametrize("value", [{}, "PDS2|m=concord", object()])
def test_loader_requires_actual_locator(tmp_path: Path, value: object) -> None:
    with pytest.raises(RoutingModelError, match="RouteLocator"):
        load_route_registration(tmp_path, value)  # type: ignore[arg-type]


@pytest.mark.parametrize("raw", [b"\xff", b"{not json", b"null", b"[]"])
def test_loader_wraps_invalid_encoding_json_and_top_level(
    tmp_path: Path,
    raw: bytes,
) -> None:
    locator = make_locator()
    path = route_registration_path(tmp_path, locator)
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    with pytest.raises(RouteRegistrationReadError) as raised:
        load_route_registration(tmp_path, locator)
    assert raised.value.__cause__ is not None


@pytest.mark.parametrize(
    "raw",
    [
        '{"schema_version":"1","schema_version":"1"}',
        '{"locator":{"schema":"PDS2","schema":"PDS2"}}',
        '{"target":{"module_id":"concord","module_id":"concord"}}',
        '{"module_details":{"page":{"id":1,"id":2}}}',
    ],
)
def test_loader_rejects_duplicate_keys_at_every_level(
    tmp_path: Path,
    raw: str,
) -> None:
    locator = make_locator()
    path = route_registration_path(tmp_path, locator)
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(RouteRegistrationReadError, match="duplicate"):
        load_route_registration(tmp_path, locator)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_loader_rejects_nonstandard_json_constants(
    tmp_path: Path,
    constant: str,
) -> None:
    locator = make_locator()
    data = route_registration_to_dict(make_registration())
    raw = json.dumps(data).replace('"logical": 1', f'"logical": {constant}')
    path = route_registration_path(tmp_path, locator)
    path.parent.mkdir(parents=True)
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(RouteRegistrationReadError):
        load_route_registration(tmp_path, locator)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "2"),
        ("status", "unknown"),
        ("created_at", "2026-07-14T09:00:00"),
        ("human_fallback", " bad "),
        ("module_details", []),
    ],
)
def test_loader_wraps_stored_model_failures(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    locator = make_locator()
    data = route_registration_to_dict(make_registration())
    data[field] = value
    write_raw_registration(tmp_path, locator, data)
    with pytest.raises(RouteRegistrationReadError) as raised:
        load_route_registration(tmp_path, locator)
    assert isinstance(raised.value.__cause__, RoutingModelError)


@pytest.mark.parametrize(
    "persisted_locator",
    [
        make_locator(module_id="quillan"),
        make_locator(class_id="english10_p4"),
        make_locator(work_id="other_work"),
        make_locator(route_id="rt_ffffffffffffffffffffffffffffffff"),
    ],
)
def test_loader_rejects_each_exact_locator_mismatch(
    tmp_path: Path,
    persisted_locator: RouteLocator,
) -> None:
    requested = make_locator()
    write_raw_registration(
        tmp_path,
        requested,
        route_registration_to_dict(make_registration(locator=persisted_locator)),
    )
    with pytest.raises(RouteRegistrationIntegrityError):
        load_route_registration(tmp_path, requested)


@pytest.mark.parametrize("status", sorted(ROUTE_REGISTRATION_STATUSES))
def test_all_shared_statuses_load_and_resolve(
    tmp_path: Path,
    status: str,
) -> None:
    registration = make_registration(status=status)
    write_route_registration(tmp_path, registration)
    resolution = resolve_route_registration(tmp_path, registration.locator)

    assert resolution.locator == registration.locator
    assert resolution.registration == registration
    assert resolution.class_root == tmp_path / "classes" / "english10_p3"
    assert resolution.module_root == resolution.class_root / "modules" / "concord"
    assert resolution.work_root == (
        resolution.module_root / "work" / "socratic_seminar_1"
    )
    assert not (
        resolution.work_root / "artifacts" / "artifact_page_0123456789abcdef"
    ).exists()
