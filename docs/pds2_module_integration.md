# PDS2 Module Integration Guide

This guide is the active integration contract for Paper Data Suite modules
using `pds-core` v0.5.0. Accepted architecture decisions and the focused
contracts linked below remain authoritative for their respective schemas.

## Requirements and compatibility

A downstream module integrating this release must:

- require Python 3.11 or newer;
- depend on `pds-core>=0.5,<0.6` while Core remains pre-1.0;
- use Core routing contract version `"1"`;
- emit and parse only the `PDS2` QR payload schema;
- persist route-registration schema version `"1"`;
- write new routing-failure and resolution records using schema version `"2"`;
- keep module-specific records and descendants owned by the module; and
- register its profile explicitly or through the
  `paper_data_suite.modules` entry-point group.

The QR, registration, failure, and resolution versions are independent. A
Core package upgrade does not implicitly change any serialized schema version.

For a downstream `pyproject.toml`, the dependency boundary is:

```toml
dependencies = ["pds-core>=0.5,<0.6"]
```

Core has no runtime dependencies and does not depend on ScoreForm, Quillan, or
Concord.

## Identity and ownership

PDS2 identifies one expected physical page route:

```text
PDS2|m=<module_id>|c=<class_id>|w=<work_id>|r=<route_id>
```

The four values form a `RouteLocator`. They do not identify a student,
assignment, logical page, Author, Subject, Group, scorer, final evidence file,
or module record. Module-specific meaning remains behind the persisted
`RouteRegistration.target`, which is a generic `ModuleRecordRef`.

Core owns:

- the PDS2 grammar and `RouteLocator` validation;
- generic work, locator, target-reference, registration, and resolution models;
- module-qualified work and registration paths;
- exclusive registration persistence and strict loading;
- module-profile discovery, registry rules, compatibility checks, and dispatch;
- retained-source provenance; and
- generic failure and resolution metadata.

The module owns:

- `work_id`, `record_kind`, and `record_id` semantics;
- the target record and its schema;
- module-specific registration validation;
- files beneath its work root other than Core's `routes/` registrations;
- QR image rendering and payload extraction from images;
- page interpretation, evidence, scoring, and Review UX; and
- any student, assignment, Author, Subject, or other domain identity.

## Create and persist a route

Use the public modules directly; v0.5.0 does not add broad re-exports from
`pds_core.__init__`.

```python
from datetime import datetime, timezone

from pds_core.pds2 import serialize_pds2_payload
from pds_core.route_ids import generate_route_id
from pds_core.route_registrations import write_route_registration
from pds_core.routing_models import (
    PDS2_SCHEMA,
    ROUTE_REGISTRATION_SCHEMA_VERSION,
    ModuleRecordRef,
    ModuleWorkRef,
    RouteLocator,
    RouteRegistration,
)

work = ModuleWorkRef(
    module_id="quillan",
    class_id="english12_p4",
    work_id="personal_narrative",
)
locator = RouteLocator(
    schema=PDS2_SCHEMA,
    work=work,
    route_id=generate_route_id(),
)
target = ModuleRecordRef(
    module_id="quillan",
    record_kind="response_page",
    record_id="response_page_001",
    contract_version="1",
)
registration = RouteRegistration(
    schema_version=ROUTE_REGISTRATION_SCHEMA_VERSION,
    locator=locator,
    target=target,
    created_at=datetime.now(timezone.utc).isoformat(),
    status="active",
    human_fallback="English 12 P4 personal narrative response page",
    module_details={"template_version": "1"},
)

registration_path = write_route_registration(workspace_root, registration)
payload_text = serialize_pds2_payload(locator)
```

`generate_route_id()` is non-semantic. Registration creation is exclusive and
never replaces an existing route. Treat `RouteRegistration` as immutable; a
later lifecycle state uses a new route and explicit module workflow rather than
editing persisted Core registration JSON in place.

The canonical paths are:

```text
classes/<class_id>/modules/<module_id>/work/<work_id>/
classes/<class_id>/modules/<module_id>/work/<work_id>/routes/<route_id>.json
```

Use `safe_module_work_descendant(...)` for module-owned relative paths. Do not
reintroduce universal assignment or student-submission directories in Core.

## Parse, resolve, and dispatch

```python
from pds_core.module_dispatch import RouteDispatchRequest, dispatch_route
from pds_core.pds2 import parse_pds2_payload

locator = parse_pds2_payload(decoded_payload_text)
request = RouteDispatchRequest(
    locator=locator,
    retained_source=retained_source,
    source_page_number=source_page_number,
)
result = dispatch_route(workspace_root, registry, request)
```

The parser accepts exactly four fields in any order and the serializer emits
canonical `m`, `c`, `w`, `r` order. Both enforce ASCII and a 256-byte maximum.
PDS1 and OMR1 are unsupported; there is no fallback parser.

`dispatch_route(...)` selects the exact registered module profile before route
lookup, checks Core and QR compatibility, strictly loads the exact registration,
checks registration-schema and status compatibility, runs the optional module
validator, and invokes the module handler. `dispatch_routes(...)` preserves
input order and isolates expected per-page failures.

## Provide a module profile

```python
from pds_core.module_profiles import (
    CORE_ROUTING_CONTRACT_VERSION,
    ModuleProfile,
)


def module_profile() -> ModuleProfile:
    return ModuleProfile(
        module_id="quillan",
        display_name="Quillan",
        supported_core_routing_contract_versions=frozenset(
            {CORE_ROUTING_CONTRACT_VERSION}
        ),
        supported_qr_schemas=frozenset({"PDS2"}),
        supported_route_registration_schema_versions=frozenset({"1"}),
        dispatchable_route_statuses=frozenset({"active"}),
        route_handler=handle_route,
        registration_validator=validate_registration,
    )
```

The provider must accept no arguments and return one `ModuleProfile`. Register
it for installed discovery with:

```toml
[project.entry-points."paper_data_suite.modules"]
quillan = "quillan.pds_integration:module_profile"
```

The entry-point name must exactly equal the returned profile's `module_id`.
Both values must be valid lowercase module identifiers. Discovery fails rather
than guessing or normalizing when they differ. Duplicate module IDs, malformed
providers, provider errors, and invalid profiles also fail discovery. Core
never derives an import path from QR data.

Applications may instead construct a registry explicitly:

```python
from pds_core.module_profiles import build_module_registry

registry = build_module_registry(
    explicit_profiles=(module_profile(),),
    discover_installed=False,
)
```

## Retention, failure, and resolution

Call `pds_core.scan_retention.retain_source_scan(...)` before module processing
to create an exclusive retained copy and SHA-256 provenance. Imports, help, and
path construction do not create workspace data; retention and explicit writers
are mutating operations.

Expected dispatch failures can be converted with
`routing_failure_metadata_from_dispatch_failure(...)` and persisted through
`write_routing_failure_metadata(...)`. Failure records are immutable and live
at `scans/review/<failure_id>.json`.

Create linked events with `create_scan_resolution_metadata(...)` and append
them through `write_scan_resolution_metadata(...)`. Core reloads and verifies
the canonical failure before writing a resolution at
`scans/review/resolutions/<resolution_id>.json`. Several resolution events may
refer to one failure; Core does not maintain a mutable latest-resolution file.

Failure and resolution records use schema `"2"`. Version 1 records are rejected
and are not converted automatically. Keep module diagnostics JSON-native under
`module_details`; incomplete observations are not authoritative locators or
targets.

## Migration checklist

1. Raise the downstream Python requirement to `>=3.11` if needed.
2. Add `pds-core>=0.5,<0.6` without adding the module to Core's dependencies.
3. Delete PDS1, OMR1, and `QrPayload` integration code and compatibility paths.
4. Replace assignment/student-based QR fields with PDS2 locators and persisted
   module-owned target references.
5. Move work under the module-qualified root and keep semantic descendants
   module-owned.
6. Implement a strict registration validator and route handler.
7. Register a profile explicitly and, for installed discovery, expose the
   `paper_data_suite.modules` entry point.
8. Adopt version 2 failure/resolution creation for new events; do not silently
   rewrite historical version 1 files.
9. Test mixed-module batches, unknown modules, missing/corrupt registrations,
   incompatible versions/statuses, module validation failures, and handler
   failures.
10. Confirm importing the module and displaying help create no workspace data.

## Downstream status

Core v0.5.0 establishes the contract required before downstream migration.
The migrations remain owned by:

- ScoreForm: `Paper-Data-Suite/pds-scoreform#137`;
- Quillan: `Paper-Data-Suite/pds-quillan#329`; and
- Concord: `Paper-Data-Suite/pds-concord#17`.

This release does not add downstream profiles, migrate their data, or implement
their module-owned targets.

## Authoritative references

- [ADR 0001](decisions/0001-adopt-pds2-page-locator-routing.md)
- [PDS2 payload contract](pds2_payload_contract.md)
- [Routing identity models](routing_identity_models.md)
- [Module-qualified workspace](module_qualified_workspace.md)
- [Module profiles and dispatch](module_profiles_and_dispatch.md)
- [Failure and resolution metadata](scan_failure_resolution_metadata.md)
- [Active scan contract](active_scan_contract.md)

The superseded [PDS1 QR/routing document](qr_payload_and_routing_contract.md)
and root [migration plan](../migration_plan.md) are historical context only.
