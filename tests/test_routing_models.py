from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from pds_core.routing_models import (
    PDS2_SCHEMA,
    ROUTE_REGISTRATION_SCHEMA_VERSION,
    ROUTE_REGISTRATION_STATUSES,
    ModuleRecordRef,
    ModuleWorkRef,
    RouteLocator,
    RouteRegistration,
    RouteResolution,
    RoutingModelError,
    is_route_registration_status,
    module_record_ref_from_dict,
    module_record_ref_to_dict,
    module_work_ref_from_dict,
    module_work_ref_to_dict,
    route_locator_from_dict,
    route_locator_to_dict,
    route_registration_from_dict,
    route_registration_to_dict,
    validate_module_record_ref,
    validate_module_work_ref,
    validate_route_locator,
    validate_route_registration,
)


def _work() -> ModuleWorkRef:
    return ModuleWorkRef("concord", "english10_p3", "socratic_seminar_1")


def _locator(route_id: str = "rt_0123456789abcdef0123456789abcdef") -> RouteLocator:
    return RouteLocator(PDS2_SCHEMA, _work(), route_id)


def _target(
    module_id: str = "concord", contract_version: str | None = "1"
) -> ModuleRecordRef:
    return ModuleRecordRef(
        module_id,
        "artifact_page",
        "artifact_page_0123456789abcdef",
        contract_version,
    )


def _registration(
    *,
    locator: RouteLocator | None = None,
    target: ModuleRecordRef | None = None,
    status: str = "active",
    module_details: Any = None,
) -> RouteRegistration:
    return RouteRegistration(
        schema_version=ROUTE_REGISTRATION_SCHEMA_VERSION,
        locator=locator or _locator(),
        target=target or _target(),
        created_at="2026-07-14T09:00:00-04:00",
        status=status,
        human_fallback=(
            "PDS2 | concord | english10_p3 | socratic_seminar_1 | "
            "rt_0123456789abcdef0123456789abcdef"
        ),
        module_details={} if module_details is None else module_details,
    )


def _registration_dict() -> dict[str, object]:
    return route_registration_to_dict(_registration())


def test_module_work_ref_is_frozen_slotted_hashable_value() -> None:
    value = _work()
    same = ModuleWorkRef("concord", "english10_p3", "socratic_seminar_1")

    assert value == same
    assert hash(value) == hash(same)
    assert {value: "found"}[same] == "found"
    with pytest.raises(FrozenInstanceError):
        value.work_id = "other"  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        value.dynamic = "no"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("module_id", "ScoreForm"),
        ("module_id", "pds.concord"),
        ("module_id", "../concord"),
        ("class_id", ""),
        ("class_id", " english10"),
        ("class_id", "english/10"),
        ("work_id", "work|one"),
        ("work_id", "work one"),
    ],
)
def test_module_work_ref_rejects_invalid_identifiers(
    field_name: str, value: str
) -> None:
    values = {
        "module_id": "concord",
        "class_id": "english10_p3",
        "work_id": "seminar-1",
    }
    values[field_name] = value

    with pytest.raises(RoutingModelError, match=field_name):
        ModuleWorkRef(**values)


def test_module_work_ref_exact_mapping_contract_and_round_trip() -> None:
    expected = {
        "module_id": "concord",
        "class_id": "english10_p3",
        "work_id": "socratic_seminar_1",
    }

    assert module_work_ref_to_dict(_work()) == expected
    assert module_work_ref_from_dict(expected) == _work()
    assert validate_module_work_ref(expected) == _work()
    assert validate_module_work_ref(_work()) is not None

    for invalid in (
        {"module_id": "concord", "class_id": "english10_p3"},
        {**expected, "student_id": "student_1"},
        {1: "concord", "class_id": "english10_p3", "work_id": "work"},
        "not a mapping",
    ):
        with pytest.raises(RoutingModelError):
            module_work_ref_from_dict(invalid)


def test_route_locator_value_and_convenience_contract() -> None:
    locator = _locator()
    same = _locator()

    assert locator == same
    assert hash(locator) == hash(same)
    assert locator.schema == "PDS2"
    assert locator.module_id == "concord"
    assert locator.class_id == "english10_p3"
    assert locator.work_id == "socratic_seminar_1"
    assert not hasattr(locator, "student_id")
    assert not hasattr(locator, "page")


def test_route_locator_validates_schema_work_and_general_safe_route_id() -> None:
    assert RouteLocator(PDS2_SCHEMA, _work(), "future_route-id")

    with pytest.raises(RoutingModelError, match="schema"):
        RouteLocator("PDS1", _work(), "route_1")  # type: ignore[arg-type]
    with pytest.raises(RoutingModelError, match="work"):
        RouteLocator(PDS2_SCHEMA, "not-work", "route_1")  # type: ignore[arg-type]
    with pytest.raises(RoutingModelError, match="route_id"):
        RouteLocator(PDS2_SCHEMA, _work(), "route/1")


def test_route_locator_uses_exact_flat_mapping_shape() -> None:
    expected = {
        "schema": "PDS2",
        "module_id": "concord",
        "class_id": "english10_p3",
        "work_id": "socratic_seminar_1",
        "route_id": "rt_0123456789abcdef0123456789abcdef",
    }

    assert route_locator_to_dict(_locator()) == expected
    assert route_locator_from_dict(expected) == _locator()
    assert validate_route_locator(expected) == _locator()
    assert "work" not in route_locator_to_dict(_locator())

    for invalid in (
        {key: value for key, value in expected.items() if key != "route_id"},
        {**expected, "page": 1},
        {**expected, "schema": "PDS1"},
        {"work": module_work_ref_to_dict(_work()), "route_id": "route_1"},
    ):
        with pytest.raises(RoutingModelError):
            route_locator_from_dict(invalid)


@pytest.mark.parametrize(
    "record_kind", ["answer_sheet_page", "response_page", "artifact_page"]
)
def test_module_record_ref_supports_module_owned_record_kinds(
    record_kind: str,
) -> None:
    value = ModuleRecordRef("concord", record_kind, "record_1", "v1")
    assert value.record_kind == record_kind


def test_module_record_ref_validation_equality_hashing_and_mapping() -> None:
    value = _target(contract_version=None)
    expected = {
        "module_id": "concord",
        "record_kind": "artifact_page",
        "record_id": "artifact_page_0123456789abcdef",
        "contract_version": None,
    }

    assert value == _target(contract_version=None)
    assert hash(value) == hash(_target(contract_version=None))
    assert module_record_ref_to_dict(value) == expected
    assert module_record_ref_from_dict(expected) == value
    assert validate_module_record_ref(expected) == value

    invalid_values = (
        ("Concord", "artifact_page", "record_1", "1"),
        ("concord", "ArtifactPage", "record_1", "1"),
        ("concord", "artifact_page", "record/1", "1"),
        ("concord", "artifact_page", "record_1", "0.5.0"),
        ("concord", "artifact_page", "record_1", ""),
    )
    for arguments in invalid_values:
        with pytest.raises(RoutingModelError):
            ModuleRecordRef(*arguments)


def test_module_record_ref_mapping_requires_all_and_only_documented_keys() -> None:
    expected = module_record_ref_to_dict(_target())

    with pytest.raises(RoutingModelError, match="missing"):
        module_record_ref_from_dict(
            {key: value for key, value in expected.items() if key != "contract_version"}
        )
    with pytest.raises(RoutingModelError, match="unknown"):
        module_record_ref_from_dict({**expected, "module": "concord"})


@pytest.mark.parametrize("status", sorted(ROUTE_REGISTRATION_STATUSES))
def test_route_registration_accepts_every_shared_status(status: str) -> None:
    registration = _registration(status=status)
    assert registration.status == status
    assert is_route_registration_status(status)


def test_route_registration_rejects_schema_status_and_target_mismatch() -> None:
    base = _registration()

    with pytest.raises(RoutingModelError, match="schema_version"):
        RouteRegistration(
            "2",
            base.locator,
            base.target,
            base.created_at,
            base.status,
            base.human_fallback,
        )
    with pytest.raises(RoutingModelError, match="status"):
        _registration(status="unknown")
    with pytest.raises(RoutingModelError, match="target.module_id"):
        _registration(target=_target(module_id="scoreform"))
    assert not is_route_registration_status(1)
    assert not is_route_registration_status("ACTIVE")


@pytest.mark.parametrize(
    "created_at",
    ["2026-07-14T09:00:00", "not-a-date", "", 123],
)
def test_route_registration_requires_aware_iso_timestamp(created_at: object) -> None:
    base = _registration()
    with pytest.raises(RoutingModelError, match="created_at"):
        RouteRegistration(
            base.schema_version,
            base.locator,
            base.target,
            created_at,  # type: ignore[arg-type]
            base.status,
            base.human_fallback,
        )


def test_route_registration_accepts_z_and_numeric_offset_timestamps() -> None:
    base = _registration()
    for created_at in ("2026-07-14T13:00:00Z", "2026-07-14T09:00:00-04:00"):
        value = RouteRegistration(
            base.schema_version,
            base.locator,
            base.target,
            created_at,
            base.status,
            base.human_fallback,
        )
        assert value.created_at == created_at


@pytest.mark.parametrize(
    "human_fallback",
    [
        "",
        " leading",
        "trailing ",
        "two\nlines",
        "nul\x00value",
        "first\u2028second",
        "first\u2029second",
    ],
)
def test_route_registration_rejects_invalid_human_fallback(
    human_fallback: str,
) -> None:
    base = _registration()
    with pytest.raises(RoutingModelError, match="human_fallback"):
        RouteRegistration(
            base.schema_version,
            base.locator,
            base.target,
            base.created_at,
            base.status,
            human_fallback,
        )


@pytest.mark.parametrize(
    "invalid_value",
    [
        {1: "non-string key"},
        {"value": {"set"}},
        {"value": b"bytes"},
        {"value": Path("somewhere")},
        {"value": datetime.now(timezone.utc)},
        {"value": object()},
        {"value": ("tuple",)},
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": float("-inf")},
    ],
)
def test_route_registration_rejects_non_json_module_details(
    invalid_value: object,
) -> None:
    with pytest.raises(RoutingModelError, match="module_details"):
        _registration(module_details=invalid_value)


def test_route_registration_rejects_circular_module_details() -> None:
    details: dict[str, object] = {}
    details["self"] = details
    with pytest.raises(RoutingModelError, match="circular"):
        _registration(module_details=details)


def test_route_registration_defensively_freezes_and_serializes_details() -> None:
    details = {
        "lookup": {"attempt": 2, "labels": ["first", "second"]},
        "confidence": 0.95,
        "ready": True,
        "optional": None,
    }
    registration = _registration(module_details=details)
    expected = {
        "lookup": {"attempt": 2, "labels": ["first", "second"]},
        "confidence": 0.95,
        "ready": True,
        "optional": None,
    }

    details["lookup"]["labels"].append("caller mutation")  # type: ignore[index]
    assert route_registration_to_dict(registration)["module_details"] == expected
    assert registration.module_details == expected
    json.dumps(registration.module_details, allow_nan=False)

    exposed = registration.module_details
    exposed_lookup = exposed["lookup"]
    assert isinstance(exposed_lookup, dict)
    exposed_labels = exposed_lookup["labels"]
    assert isinstance(exposed_labels, list)
    exposed_labels.append("exposed mutation")
    assert registration.module_details == expected
    assert route_registration_to_dict(registration)["module_details"] == expected

    serialized_details = route_registration_to_dict(registration)["module_details"]
    assert isinstance(serialized_details, dict)
    serialized_lookup = serialized_details["lookup"]
    assert isinstance(serialized_lookup, dict)
    serialized_labels = serialized_lookup["labels"]
    assert isinstance(serialized_labels, list)
    serialized_labels.append("output mutation")
    assert registration.module_details == expected
    assert route_registration_to_dict(registration)["module_details"] == expected


def test_route_registration_exact_mapping_shape_and_round_trip() -> None:
    expected = _registration_dict()
    assert set(expected) == {
        "schema_version",
        "locator",
        "target",
        "created_at",
        "status",
        "human_fallback",
        "module_details",
    }
    assert route_registration_from_dict(expected) == _registration()
    assert validate_route_registration(expected) == _registration()

    with pytest.raises(RoutingModelError, match="missing"):
        route_registration_from_dict(
            {key: value for key, value in expected.items() if key != "status"}
        )
    with pytest.raises(RoutingModelError, match="unknown"):
        route_registration_from_dict({**expected, "metadata": {}})
    nested_locator_value = expected["locator"]
    assert isinstance(nested_locator_value, dict)
    nested_locator = dict(nested_locator_value)
    nested_locator["student_id"] = "student_1"
    with pytest.raises(RoutingModelError, match="unknown"):
        route_registration_from_dict({**expected, "locator": nested_locator})


def test_route_resolution_validates_identity_and_paths_without_io(
    tmp_path: Path,
) -> None:
    registration = _registration()
    class_root = tmp_path / "missing-class"
    module_root = class_root / "modules" / "concord"
    work_root = module_root / "work" / "socratic_seminar_1"
    resolution = RouteResolution(
        registration.locator,
        registration,
        class_root,
        module_root,
        work_root,
    )

    assert resolution.registration == registration
    assert not class_root.exists()
    with pytest.raises(FrozenInstanceError):
        resolution.work_root = tmp_path  # type: ignore[misc]


def test_route_resolution_allows_non_active_registration(tmp_path: Path) -> None:
    registration = _registration(status="retired")
    resolution = RouteResolution(
        registration.locator,
        registration,
        tmp_path / "class",
        tmp_path / "module",
        tmp_path / "work",
    )
    assert resolution.registration.status == "retired"


def test_route_resolution_rejects_mismatch_and_non_path_values(tmp_path: Path) -> None:
    registration = _registration()
    with pytest.raises(RoutingModelError, match="exactly match"):
        RouteResolution(
            _locator("different_route"),
            registration,
            tmp_path,
            tmp_path,
            tmp_path,
        )
    with pytest.raises(RoutingModelError, match="class_root"):
        RouteResolution(
            registration.locator,
            registration,
            "not-a-path",  # type: ignore[arg-type]
            tmp_path,
            tmp_path,
        )


def test_new_models_exclude_legacy_and_module_semantic_fields() -> None:
    excluded = {
        "assignment_id",
        "student_id",
        "page",
        "metadata",
        "submission_dir",
        "author",
        "subject",
        "score_target",
    }
    for model in (
        ModuleWorkRef,
        RouteLocator,
        ModuleRecordRef,
        RouteRegistration,
        RouteResolution,
    ):
        assert excluded.isdisjoint(field.name for field in fields(model))
