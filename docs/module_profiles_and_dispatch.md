# Module Profiles and Page Dispatch

PDS Core implements a public runtime boundary between a validated PDS2 route
and the module that owns it. Core discovers or accepts a `ModuleProfile`,
resolves the persisted `RouteRegistration`, checks exact compatibility, and
dispatches one retained-source page. It does not import sibling modules,
derive imports from QR data, or interpret module-owned targets.

## Runtime contract and profile

`CORE_ROUTING_CONTRACT_VERSION` is currently `"1"`. This version identifies
the public Core routing integration contract; it is independent of the Core
package version, the `PDS2` QR schema, route-registration schema `"1"`, and a
module target's contract version. Compatibility is exact membership, not
package-version comparison.

`ModuleProfile` is a frozen, slotted runtime object containing:

- a safe lowercase stable `module_id` and diagnostic `display_name`;
- non-empty supported Core, QR, and registration-schema sets;
- a non-empty subset of shared dispatchable route statuses;
- a required route handler;
- and an optional module registration validator.

Profiles are not persisted. Core defensively copies compatibility collections
to `frozenset` values. The validator can reject module-specific structural
requirements such as a target `record_kind`, target `contract_version`, or
required `module_details`, but it must not mutate the frozen registration and
must return `None`. Target existence and lifecycle checks belong to the route
handler. Handler results are returned unchanged and may be `None`.

## Explicit registration and installed discovery

Applications own a `ModuleRegistry`; there is no mutable process-global
registry. Registration is exact by `module_id`, deterministic inspection is
sorted, and every duplicate or explicit/installed conflict is an error. An
unknown module raises `UnsupportedModuleError` before registration filesystem
access.

Startup can include providers declared by installed distributions:

```python
from pds_core.module_profiles import build_module_registry

registry = build_module_registry(
    discover_installed=True,
)
```

Controlled applications and tests can compose profiles explicitly:

```python
registry = build_module_registry(
    explicit_profiles=(profile,),
    discover_installed=False,
)
```

Installed discovery enumerates only the standard entry-point group:

```text
paper_data_suite.modules
```

A downstream distribution declares the entry-point name as its stable module
ID and exposes a zero-argument provider:

```toml
[project.entry-points."paper_data_suite.modules"]
concord = "concord.pds_module:get_module_profile"
```

The provider must return one validated `ModuleProfile` whose `module_id`
exactly equals the entry-point name. Discovery order is deterministic. Load,
provider, type, validation, identity, and duplicate failures raise
`ModuleDiscoveryError`; a broken installed integration is never silently
omitted. A QR `module_id` is used only for exact registry lookup and is never
transformed into a Python import path or workspace search.

## Dispatch order and boundaries

`dispatch_route(...)` performs these steps in order:

1. Revalidate the `RouteDispatchRequest`.
2. Require its exact module profile.
3. Check Core routing-contract and QR-schema support.
4. Structurally resolve the persisted registration.
5. Check exact module identity, registration-schema support, and route status.
6. Invoke the optional registration validator.
7. Invoke the module route handler.
8. Return `RouteDispatchSuccess` with the unchanged handler result.

Pre-load checks ensure unknown or incompatible modules cannot trigger
registration reads. The request requires an actual `RouteLocator`, an actual
`RetainedSourceScan`, and a one-based integer source page number. It does not
accept raw payload text or an external source path.

```python
from pds_core.module_dispatch import RouteDispatchRequest, dispatch_route

request = RouteDispatchRequest(
    locator=locator,
    retained_source=retained_source,
    source_page_number=2,
)

success = dispatch_route(
    workspace_root,
    registry,
    request,
)
```

Core preserves typed distinctions among unsupported modules, contract
incompatibility, persistence or locator-integrity failures, non-dispatchable
statuses, validator failures, and handler failures. Validator and handler
exceptions are wrapped with their original exception as the cause;
`KeyboardInterrupt`, `SystemExit`, and other `BaseException` values are not
caught.

Structural resolution is not processing authorization. A non-active
registration can load and resolve, but its handler runs only if the selected
profile explicitly includes that status in `dispatchable_route_statuses`.
The normal initial policy is `frozenset({"active"})`.

Core dispatch does not load or create module targets, interpret record kinds,
write evidence or Review records, alter registration status, reread retained
source bytes, or write scan failure/resolution metadata.

## Mixed-module batches

`dispatch_routes(...)` eagerly processes an iterable sequentially, selects a
profile for each page, preserves request order, and returns one outcome per
request:

```python
from pds_core.module_dispatch import dispatch_routes

outcomes = dispatch_routes(
    workspace_root,
    registry,
    requests,
)
```

Each outcome is `RouteDispatchSuccess` or `RouteDispatchFailure`. Expected
request, module, compatibility, persistence, and routing-model failures are
isolated to that page, so later pages continue. One retained source may
therefore produce heterogeneous successes and failures across ScoreForm-like,
Quillan-like, Concord-like, or other installed integrations. Outcomes are
runtime values, not persisted metadata; generalized failure and resolution
mapping remains separate work.
