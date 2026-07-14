"""Tests for module compatibility and page-by-page route dispatch."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, cast

import pytest

import pds_core.module_dispatch as module_dispatch
from pds_core.module_dispatch import (
    ModuleContractCompatibilityError,
    ModuleRegistrationValidationError,
    ModuleRouteHandlingError,
    RouteDispatchFailure,
    RouteDispatchRequest,
    RouteDispatchRequestError,
    RouteDispatchSuccess,
    RouteStatusNotDispatchableError,
    dispatch_route,
    dispatch_routes,
)
from pds_core.module_profiles import (
    ModuleProfile,
    ModuleRegistrationValidator,
    ModuleRegistry,
    UnsupportedModuleError,
)
from pds_core.route_registrations import (
    RouteRegistrationIntegrityError,
    RouteRegistrationNotFoundError,
    RouteRegistrationReadError,
    write_route_registration,
)
from pds_core.routes import route_registration_path
from pds_core.routing_models import (
    PDS2_SCHEMA,
    ModuleRecordRef,
    ModuleWorkRef,
    RouteLocator,
    RouteRegistration,
    RouteResolution,
    route_registration_to_dict,
)
from pds_core.scan_retention import RetainedSourceScan


def make_locator(
    module_id: str = "concord",
    route_id: str = "route_1",
) -> RouteLocator:
    return RouteLocator(
        PDS2_SCHEMA,
        ModuleWorkRef(module_id, "english10_p3", f"{module_id}_work"),
        route_id,
    )


def make_registration(
    locator: RouteLocator,
    *,
    status: str = "active",
    record_kind: str = "artifact_page",
    contract_version: str = "1",
) -> RouteRegistration:
    return RouteRegistration(
        "1",
        locator,
        ModuleRecordRef(
            locator.module_id,
            record_kind,
            f"{locator.module_id}_record_1",
            contract_version,
        ),
        "2026-07-14T09:00:00-04:00",
        status,
        f"PDS2 | {locator.module_id} | {locator.route_id}",
        {},
    )


def make_retained(root: Path) -> RetainedSourceScan:
    return RetainedSourceScan(
        "scan_1",
        "source.pdf",
        "a" * 64,
        root / "scans" / "source" / "2026-07-14" / "source.pdf",
        "scans/source/2026-07-14/source.pdf",
        datetime(2026, 7, 14, 13, tzinfo=timezone.utc),
        date(2026, 7, 14),
    )


def make_profile(
    module_id: str = "concord",
    *,
    handler: Callable[..., object] = lambda *_args: None,
    validator: Callable[..., object] | None = None,
    core_versions: frozenset[str] = frozenset({"1"}),
    qr_schemas: frozenset[str] = frozenset({"PDS2"}),
    registration_versions: frozenset[str] = frozenset({"1"}),
    statuses: frozenset[str] = frozenset({"active"}),
) -> ModuleProfile:
    return ModuleProfile(
        module_id,
        module_id.title(),
        core_versions,
        qr_schemas,
        registration_versions,
        statuses,
        handler,
        cast(ModuleRegistrationValidator | None, validator),
    )


def make_request(root: Path, locator: RouteLocator | None = None, page: int = 1) -> RouteDispatchRequest:
    return RouteDispatchRequest(locator or make_locator(), make_retained(root), page)


def test_request_is_frozen_slotted_and_does_no_io(tmp_path: Path) -> None:
    request = make_request(tmp_path, page=2)
    assert request.source_page_number == 2
    assert not hasattr(request, "__dict__")
    assert not tmp_path.joinpath("scans").exists()
    with pytest.raises(FrozenInstanceError):
        request.source_page_number = 3  # type: ignore[misc]


@pytest.mark.parametrize("page", [0, -1, True, 1.5, "1"])
def test_request_rejects_invalid_page_number(tmp_path: Path, page: object) -> None:
    with pytest.raises(RouteDispatchRequestError, match="source_page_number"):
        RouteDispatchRequest(make_locator(), make_retained(tmp_path), page)  # type: ignore[arg-type]


def test_request_requires_actual_locator_and_retained_source(tmp_path: Path) -> None:
    with pytest.raises(RouteDispatchRequestError, match="locator"):
        RouteDispatchRequest({}, make_retained(tmp_path), 1)  # type: ignore[arg-type]
    with pytest.raises(RouteDispatchRequestError, match="retained_source"):
        RouteDispatchRequest(make_locator(), tmp_path / "source.pdf", 1)  # type: ignore[arg-type]


def test_dispatch_success_preserves_exact_inputs_and_result(tmp_path: Path) -> None:
    locator = make_locator()
    registration = make_registration(locator)
    write_route_registration(tmp_path, registration)
    retained = make_retained(tmp_path)
    request = RouteDispatchRequest(locator, retained, 3)
    result = object()
    calls: list[tuple[RouteResolution, RetainedSourceScan, int]] = []

    def handler(
        resolution: RouteResolution,
        source: RetainedSourceScan,
        page: int,
    ) -> object:
        calls.append((resolution, source, page))
        return result

    profile = make_profile(handler=handler)
    success = dispatch_route(tmp_path, ModuleRegistry((profile,)), request)

    assert isinstance(success, RouteDispatchSuccess)
    assert success.request is request
    assert success.profile is profile
    assert success.module_result is result
    assert calls == [(success.resolution, retained, 3)]
    assert success.resolution.registration == registration


def test_none_is_a_valid_handler_result(tmp_path: Path) -> None:
    locator = make_locator()
    write_route_registration(tmp_path, make_registration(locator))
    success = dispatch_route(
        tmp_path, ModuleRegistry((make_profile(),)), make_request(tmp_path, locator)
    )
    assert success.module_result is None


def test_unsupported_module_and_preload_incompatibility_precede_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = make_request(tmp_path)
    called = False

    def resolve(*_args: object) -> RouteResolution:
        nonlocal called
        called = True
        raise AssertionError("must not resolve")

    monkeypatch.setattr(module_dispatch, "resolve_route_registration", resolve)
    with pytest.raises(UnsupportedModuleError):
        dispatch_route(tmp_path, ModuleRegistry(), request)
    with pytest.raises(ModuleContractCompatibilityError, match="Core"):
        dispatch_route(
            tmp_path,
            ModuleRegistry((make_profile(core_versions=frozenset({"2"})),)),
            request,
        )
    with pytest.raises(ModuleContractCompatibilityError, match="QR schema"):
        dispatch_route(
            tmp_path,
            ModuleRegistry((make_profile(qr_schemas=frozenset({"PDS3"})),)),
            request,
        )
    assert not called


def test_missing_registration_preserves_typed_error(tmp_path: Path) -> None:
    with pytest.raises(RouteRegistrationNotFoundError):
        dispatch_route(
            tmp_path,
            ModuleRegistry((make_profile(),)),
            make_request(tmp_path),
        )


def test_malformed_registration_read_error_propagates_before_module_calls(
    tmp_path: Path,
) -> None:
    locator = make_locator()
    path = route_registration_path(tmp_path, locator)
    path.parent.mkdir(parents=True)
    path.write_text("{not valid json", encoding="utf-8")
    calls: list[str] = []
    profile = make_profile(
        validator=lambda *_args: calls.append("validator"),
        handler=lambda *_args: calls.append("handler"),
    )

    with pytest.raises(RouteRegistrationReadError):
        dispatch_route(
            tmp_path,
            ModuleRegistry((profile,)),
            make_request(tmp_path, locator),
        )

    assert calls == []


def test_registration_locator_integrity_error_propagates_before_module_calls(
    tmp_path: Path,
) -> None:
    requested = make_locator()
    stored = make_locator(route_id="different_route")
    path = route_registration_path(tmp_path, requested)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(route_registration_to_dict(make_registration(stored))),
        encoding="utf-8",
    )
    calls: list[str] = []
    profile = make_profile(
        validator=lambda *_args: calls.append("validator"),
        handler=lambda *_args: calls.append("handler"),
    )
    nonexistent_target = tmp_path / "module-target-record.json"

    with pytest.raises(RouteRegistrationIntegrityError):
        dispatch_route(
            tmp_path,
            ModuleRegistry((profile,)),
            make_request(tmp_path, requested),
        )

    assert calls == []
    assert not nonexistent_target.exists()


def test_registration_schema_compatibility_precedes_module_invocation(
    tmp_path: Path,
) -> None:
    locator = make_locator()
    write_route_registration(tmp_path, make_registration(locator))
    called = False

    def handler(*_args: object) -> object:
        nonlocal called
        called = True
        return None

    with pytest.raises(ModuleContractCompatibilityError, match="registration"):
        dispatch_route(
            tmp_path,
            ModuleRegistry(
                (make_profile(handler=handler, registration_versions=frozenset({"2"})),)
            ),
            make_request(tmp_path, locator),
        )
    assert not called


@pytest.mark.parametrize(
    "status", ["inactive", "retired", "superseded", "cancelled", "invalidated"]
)
def test_non_dispatchable_status_rejects_before_validator_and_handler(
    tmp_path: Path,
    status: str,
) -> None:
    locator = make_locator()
    write_route_registration(tmp_path, make_registration(locator, status=status))
    calls: list[str] = []
    profile = make_profile(
        handler=lambda *_args: calls.append("handler"),
        validator=lambda *_args: calls.append("validator"),
    )
    with pytest.raises(RouteStatusNotDispatchableError, match=status):
        dispatch_route(tmp_path, ModuleRegistry((profile,)), make_request(tmp_path, locator))
    assert calls == []


def test_profile_can_deliberately_dispatch_another_status(tmp_path: Path) -> None:
    locator = make_locator()
    write_route_registration(tmp_path, make_registration(locator, status="inactive"))
    success = dispatch_route(
        tmp_path,
        ModuleRegistry((make_profile(statuses=frozenset({"inactive"})),)),
        make_request(tmp_path, locator),
    )
    assert success.resolution.registration.status == "inactive"


def test_validator_runs_before_handler_and_must_return_none(tmp_path: Path) -> None:
    locator = make_locator()
    registration = make_registration(locator)
    write_route_registration(tmp_path, registration)
    calls: list[str] = []

    def validator(value: RouteRegistration) -> None:
        assert value == registration
        calls.append("validator")

    def handler(*_args: object) -> object:
        calls.append("handler")
        return "ok"

    success = dispatch_route(
        tmp_path,
        ModuleRegistry((make_profile(handler=handler, validator=validator),)),
        make_request(tmp_path, locator),
    )
    assert success.module_result == "ok"
    assert calls == ["validator", "handler"]

    with pytest.raises(ModuleRegistrationValidationError, match="return None"):
        dispatch_route(
            tmp_path,
            ModuleRegistry((make_profile(validator=lambda *_args: "bad"),)),
            make_request(tmp_path, locator),
        )


def test_validator_exception_is_wrapped_with_cause_and_handler_not_called(
    tmp_path: Path,
) -> None:
    locator = make_locator()
    write_route_registration(tmp_path, make_registration(locator))
    called = False

    def validator(_registration: RouteRegistration) -> None:
        raise ValueError("unsupported target")

    def handler(*_args: object) -> object:
        nonlocal called
        called = True
        return None

    with pytest.raises(ModuleRegistrationValidationError) as raised:
        dispatch_route(
            tmp_path,
            ModuleRegistry((make_profile(handler=handler, validator=validator),)),
            make_request(tmp_path, locator),
        )
    assert isinstance(raised.value.__cause__, ValueError)
    assert not called


@pytest.mark.parametrize(
    ("record_kind", "contract_version", "expected_message"),
    [
        ("response_page", "1", "unsupported record kind"),
        ("artifact_page", "2", "unsupported target contract"),
    ],
)
def test_profile_validator_owns_target_kind_and_contract_validation(
    tmp_path: Path,
    record_kind: str,
    contract_version: str,
    expected_message: str,
) -> None:
    locator = make_locator()
    write_route_registration(
        tmp_path,
        make_registration(
            locator,
            record_kind=record_kind,
            contract_version=contract_version,
        ),
    )
    handler_called = False

    def validator(registration: RouteRegistration) -> None:
        if registration.target.record_kind != "artifact_page":
            raise ValueError("unsupported record kind")
        if registration.target.contract_version != "1":
            raise ValueError("unsupported target contract")

    def handler(*_args: object) -> object:
        nonlocal handler_called
        handler_called = True
        return None

    with pytest.raises(ModuleRegistrationValidationError) as raised:
        dispatch_route(
            tmp_path,
            ModuleRegistry((make_profile(handler=handler, validator=validator),)),
            make_request(tmp_path, locator),
        )

    assert isinstance(raised.value.__cause__, ValueError)
    assert str(raised.value.__cause__) == expected_message
    assert not handler_called


def test_handler_exception_is_wrapped_with_cause(tmp_path: Path) -> None:
    locator = make_locator()
    write_route_registration(tmp_path, make_registration(locator))

    def handler(*_args: object) -> object:
        raise LookupError("target missing")

    with pytest.raises(ModuleRouteHandlingError) as raised:
        dispatch_route(
            tmp_path,
            ModuleRegistry((make_profile(handler=handler),)),
            make_request(tmp_path, locator),
        )
    assert isinstance(raised.value.__cause__, LookupError)


@pytest.mark.parametrize("raised", [KeyboardInterrupt(), SystemExit()])
def test_base_exceptions_are_not_wrapped(tmp_path: Path, raised: BaseException) -> None:
    locator = make_locator()
    write_route_registration(tmp_path, make_registration(locator))

    def handler(*_args: object) -> object:
        raise raised

    with pytest.raises(type(raised)):
        dispatch_route(
            tmp_path,
            ModuleRegistry((make_profile(handler=handler),)),
            make_request(tmp_path, locator),
        )


def test_mixed_module_batch_preserves_order_results_and_continues(
    tmp_path: Path,
) -> None:
    retained = make_retained(tmp_path)
    modules = ("scoreform", "quillan", "concord")
    profiles: list[ModuleProfile] = []
    requests: list[RouteDispatchRequest] = []
    call_order: list[tuple[str, int]] = []
    results: dict[str, object] = {
        "scoreform": {"score": 3},
        "quillan": ["tag"],
        "concord": "accepted",
    }
    for page, module_id in enumerate(modules, start=1):
        locator = make_locator(module_id, f"route_{page}")
        write_route_registration(tmp_path, make_registration(locator))

        def handler(
            _resolution: RouteResolution,
            source: RetainedSourceScan,
            source_page: int,
            *,
            owner: str = module_id,
        ) -> object:
            assert source is retained
            call_order.append((owner, source_page))
            return results[owner]

        profiles.append(make_profile(module_id, handler=handler))
        requests.append(RouteDispatchRequest(locator, retained, page))

    unsupported = RouteDispatchRequest(make_locator("unknown", "route_4"), retained, 4)
    missing = RouteDispatchRequest(make_locator("concord", "route_5"), retained, 5)
    batch = (requests[0], unsupported, requests[1], missing, requests[2], requests[2])
    outcomes = dispatch_routes(tmp_path, ModuleRegistry(profiles), batch)

    assert len(outcomes) == len(batch)
    assert [outcome.request for outcome in outcomes] == list(batch)
    assert isinstance(outcomes[0], RouteDispatchSuccess)
    assert isinstance(outcomes[1], RouteDispatchFailure)
    assert isinstance(outcomes[1].error, UnsupportedModuleError)
    assert isinstance(outcomes[2], RouteDispatchSuccess)
    assert isinstance(outcomes[3], RouteDispatchFailure)
    assert isinstance(outcomes[3].error, RouteRegistrationNotFoundError)
    assert isinstance(outcomes[4], RouteDispatchSuccess)
    assert isinstance(outcomes[5], RouteDispatchSuccess)
    assert outcomes[0].module_result is results["scoreform"]
    assert outcomes[2].module_result is results["quillan"]
    assert outcomes[4].module_result is results["concord"]
    assert call_order == [
        ("scoreform", 1),
        ("quillan", 2),
        ("concord", 3),
        ("concord", 3),
    ]


def test_mixed_batch_isolates_middle_contract_incompatibility(
    tmp_path: Path,
) -> None:
    retained = make_retained(tmp_path)
    calls: list[tuple[str, int]] = []
    results: dict[str, object] = {
        "concord": {"accepted": True},
        "scoreform": [3, 4],
    }

    def concord_handler(
        _resolution: RouteResolution,
        source: RetainedSourceScan,
        page: int,
    ) -> object:
        assert source is retained
        calls.append(("concord", page))
        return results["concord"]

    def quillan_handler(*_args: object) -> object:
        calls.append(("quillan", 2))
        return "must not run"

    def scoreform_handler(
        _resolution: RouteResolution,
        source: RetainedSourceScan,
        page: int,
    ) -> object:
        assert source is retained
        calls.append(("scoreform", page))
        return results["scoreform"]

    locators = (
        make_locator("concord", "route_1"),
        make_locator("quillan", "route_2"),
        make_locator("scoreform", "route_3"),
    )
    for locator in locators:
        write_route_registration(tmp_path, make_registration(locator))
    requests = tuple(
        RouteDispatchRequest(locator, retained, page)
        for page, locator in enumerate(locators, start=1)
    )
    registry = ModuleRegistry(
        (
            make_profile("concord", handler=concord_handler),
            make_profile(
                "quillan",
                handler=quillan_handler,
                core_versions=frozenset({"2"}),
            ),
            make_profile("scoreform", handler=scoreform_handler),
        )
    )

    outcomes = dispatch_routes(tmp_path, registry, requests)

    assert len(outcomes) == 3
    assert [outcome.request for outcome in outcomes] == list(requests)
    assert isinstance(outcomes[0], RouteDispatchSuccess)
    assert isinstance(outcomes[1], RouteDispatchFailure)
    assert isinstance(outcomes[1].error, ModuleContractCompatibilityError)
    assert isinstance(outcomes[2], RouteDispatchSuccess)
    assert outcomes[0].module_result is results["concord"]
    assert outcomes[2].module_result is results["scoreform"]
    assert calls == [("concord", 1), ("scoreform", 3)]


def test_batch_isolates_wrapped_handler_failure(tmp_path: Path) -> None:
    retained = make_retained(tmp_path)
    first = make_locator("concord", "route_1")
    second = make_locator("concord", "route_2")
    write_route_registration(tmp_path, make_registration(first))
    write_route_registration(tmp_path, make_registration(second))
    calls = 0

    def handler(*_args: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("page failure")
        return "later success"

    outcomes = dispatch_routes(
        tmp_path,
        ModuleRegistry((make_profile(handler=handler),)),
        (
            RouteDispatchRequest(first, retained, 1),
            RouteDispatchRequest(second, retained, 2),
        ),
    )
    assert isinstance(outcomes[0], RouteDispatchFailure)
    assert isinstance(outcomes[0].error, ModuleRouteHandlingError)
    assert isinstance(outcomes[1], RouteDispatchSuccess)
    assert outcomes[1].module_result == "later success"
