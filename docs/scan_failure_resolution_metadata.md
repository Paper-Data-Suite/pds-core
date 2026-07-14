# Scan Failure and Resolution Metadata Version 2

## Contract

The version 2 schemas describe a generic route from retained source bytes to a
source page, raw payload, validated PDS2 locator, optional typed module target,
and module-owned processing. Shared metadata does not infer a student,
assignment, Author, Subject, Group, evidence destination, or scoring meaning.

Failures are immutable occurrence records. Resolutions are separate immutable
events appended under distinct IDs. A resolution never edits or replaces its
failure, and several resolutions may reference one failure.

Version 1 metadata is rejected. Core provides no compatibility model,
fallback reader, field alias, or automatic conversion.

## Failure schema

Every failure object has exactly these 17 required keys; nullable values are
written as JSON `null`:

```json
{
  "schema_version": "2",
  "failure_id": "failure_001",
  "scope": "page",
  "stage": "route_resolution",
  "created_at": "2026-07-14T14:00:00Z",
  "failure_category": "route_unknown",
  "failure_message": "No route registration exists.",
  "source_filename": "scanner export.pdf",
  "source_scan_id": "scan_001",
  "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "retained_source_path": "scans/source/2026-07-14/scan.pdf",
  "review_copy_path": null,
  "source_page_number": 2,
  "detected_payload": "PDS2|m=concord|c=science7_p3|w=lab|r=route_001",
  "route_locator": {
    "schema": "PDS2",
    "module_id": "concord",
    "class_id": "science7_p3",
    "work_id": "lab",
    "route_id": "route_001"
  },
  "target": null,
  "module_details": {}
}
```

Accepted scopes are `scan` and `page`. Page scope requires a positive,
non-Boolean source page number; scan scope requires null. Stages are open safe
lowercase identifiers. Recommended stages are `intake`, `retention`,
`decoding`, `payload`, `module_resolution`, `route_resolution`,
`module_validation`, `module_handling`, `evidence`, and `review`.

Failure messages are non-empty, trimmed, single-line strings without Unicode
control or line/paragraph separator characters. `detected_payload` is the raw
decoded string and is preserved exactly without trimming, normalization,
canonicalization, or reparsing during model validation.

The generic categories are exactly:

```text
source_missing                 source_unreadable
source_type_unsupported        source_retention_failed
payload_missing                payload_unreadable
payload_invalid                payload_schema_unsupported
payload_too_large              identifier_invalid
module_unsupported             module_profile_incompatible
class_unknown                  work_unknown
route_unknown                  route_inactive
route_ambiguous                route_mismatch
route_registration_invalid     target_unknown
target_incompatible            page_conflict
processing_error               evidence_write_failed
```

`assignment_unknown` and `student_unknown` are not shared categories. A
module may retain those concepts only as module-owned diagnostics.

## Authoritative and diagnostic identity

`route_locator` is either null or an actual validated `RouteLocator`. If a raw
payload cannot produce all required PDS2 fields, Core stores no locator. Any
parser error, partial observation, candidate, or guess belongs only under
`module_details`.

`target` is either null or an actual validated `ModuleRecordRef`. A target
requires a locator and both module IDs must match. Core validates the generic
reference shape but does not assert that the referenced record exists or
interpret its kind.

`module_details` contains only JSON-native dictionaries, lists, strings,
finite numbers, booleans, and null. Keys are strings. Circular references,
unsupported objects, NaN, and infinities are rejected. Constructor input,
property results, and serialized output are deeply isolated from the stored
value.

## Retained-source provenance

`source_filename` is always required. `source_scan_id`, `source_sha256`, and
`retained_source_path` are either all null or all non-null. When present, the
ID passes Core identifier validation, the hash has exactly 64 hexadecimal
characters, and the retained path is safe and workspace-relative.
`review_copy_path` is independently optional and workspace-relative. Metadata
validation does not require any referenced file to exist and never changes
retained bytes.

## Dispatch error mapping

`routing_failure_metadata_from_dispatch_failure` converts an actual
`RouteDispatchFailure` without filesystem access. It copies the request's
locator, retained provenance, source page number, optional raw payload,
optional target, review path, and details. Its error mapping is:

| Error | Category | Stage |
| --- | --- | --- |
| `UnsupportedModuleError` | `module_unsupported` | `module_resolution` |
| `ModuleContractCompatibilityError` | `module_profile_incompatible` | `module_resolution` |
| `RouteRegistrationNotFoundError` | `route_unknown` | `route_resolution` |
| `RouteRegistrationIntegrityError` | `route_mismatch` | `route_resolution` |
| `RouteRegistrationReadError` | `route_registration_invalid` | `route_resolution` |
| `RouteStatusNotDispatchableError` | `route_inactive` | `route_resolution` |
| `ModuleRegistrationValidationError` | `target_incompatible` | `module_validation` |
| `ModuleRouteHandlingError` | `processing_error` | `module_handling` |
| `RouteDispatchRequestError` | `processing_error` | `module_handling` |
| `RoutingModelError` | `identifier_invalid` | `route_resolution` |

Subclass checks distinguish not-found and integrity errors before their
`RouteRegistrationReadError` base class. A successful dispatch is not
automatically a resolution of any earlier failure.

## Failure persistence

The canonical path is `scans/review/<failure_id>.json`. The writer validates
before mutation, creates only the canonical parent, writes sorted two-space
UTF-8 JSON ending in one newline with `allow_nan=False`, opens exclusively,
flushes, calls `fsync`, and removes a handled incomplete file when possible.
Existing IDs always collide.

The loader reads only the canonical path and rejects invalid UTF-8, malformed
JSON, duplicate keys at every depth, `NaN`, `Infinity`, `-Infinity`, non-object
roots, non-v2 or non-exact schemas, and stored/requested ID mismatches.

## Resolution schema

Every resolution object has exactly these 18 required keys:

```json
{
  "schema_version": "2",
  "resolution_id": "resolution_002",
  "failure_id": "failure_001",
  "failure_metadata_path": "scans/review/failure_001.json",
  "resolution_status": "resolved",
  "resolution_action": "route_corrected",
  "resolved_at": "2026-07-14T16:00:00Z",
  "resolution_message": "The final Concord route was selected.",
  "source_filename": "scanner export.pdf",
  "source_scan_id": "scan_001",
  "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "retained_source_path": "scans/source/2026-07-14/scan.pdf",
  "review_copy_path": null,
  "source_page_number": 2,
  "route_locator": {
    "schema": "PDS2",
    "module_id": "concord",
    "class_id": "science7_p3",
    "work_id": "lab",
    "route_id": "route_corrected"
  },
  "target": {
    "module_id": "concord",
    "record_kind": "evidence",
    "record_id": "evidence_001",
    "contract_version": "1"
  },
  "resolution_evidence_path": null,
  "module_details": {}
}
```

Statuses are exactly `resolved` and `deferred`. Actions are exactly:

```text
route_selected
route_corrected
evidence_filed
rescan_needed
cannot_route
dismissed_duplicate
deferred
other
```

The invariants are:

- deferred status and deferred action occur together, with null locator,
  target, and evidence path;
- `route_selected` and `route_corrected` require a locator and target;
- `evidence_filed` requires an evidence path;
- `rescan_needed`, `cannot_route`, and `dismissed_duplicate` require null
  locator, target, and evidence path;
- `route_selected`, `route_corrected`, and `other` may carry an evidence path;
- every path is safe and workspace-relative, but need not exist.

The resolution's route and target are the final decision and may differ from
the failure's route and target.

## Failure linkage and append-only persistence

`failure_metadata_path` must equal `scans/review/<failure_id>.json`.
`create_scan_resolution_metadata` takes an actual validated v2 failure, copies
all source provenance, derives that path, enforces action rules, and requires
`resolved_at >= failure.created_at`. It performs no filesystem access and does
not mutate the failure.

Before writing, Core loads the linked canonical failure and verifies its v2
schema, ID, canonical path, timestamp ordering, and exact equality for:

```text
source_filename
source_scan_id
source_sha256
retained_source_path
review_copy_path
source_page_number
```

Any absent, malformed, historical, or inconsistent failure prevents creation
of the resolution file. Resolution files use the same exclusive, stable,
flushed JSON behavior as failures and live at
`scans/review/resolutions/<resolution_id>.json`.

For example, all of these remain present:

```text
failure_001
  -> resolution_001: deferred
  -> resolution_002: route_corrected
  -> resolution_003: evidence_filed
```

The resolution loader strictly deserializes one canonical record and verifies
its stored ID. It need not load the linked failure; linkage is enforced when
the event is appended.

## Examples and ownership

An invalid payload has `detected_payload` set to its exact raw text,
`route_locator=null`, `target=null`, category `payload_invalid`, and parser
diagnostics such as `{"parser_error": "missing r", "observed": {"m":
"quillan"}}` under `module_details`.

An unsupported module uses `module_unsupported` at `module_resolution`. A
missing registration uses `route_unknown` at `route_resolution`. A module
registration validator failure uses `target_incompatible` at
`module_validation`. An evidence writer failure uses `evidence_write_failed`
at `evidence`; its evidence-specific context remains module-owned.

A corrected Concord route can use a Concord locator and evidence target with
no student identity anywhere in the shared record. Quillan may store student
observations under a module-owned shape such as
`{"quillan": {"student_candidates": ["student_001"]}}`. ScoreForm may store
mark diagnostics as `{"scoreform": {"unreadable_marks": [3, 7]}}`. Neither
shape becomes a universal Core field or authoritative route identity.

Core owns the schemas, generic vocabularies, routing-model validation,
provenance checks, strict readers, and immutable writers. Modules own semantic
record validation, participants, scoring, evidence creation, and Review UX.
