# Active Scan Intake, Retention, and Routing Review Contract

## Status and scope

PDS Core implements the shared active-scan paths, retained-source operation,
PDS2 routing identity, module dispatch, generic routing-failure metadata, and
append-only resolution metadata. It does not decode images, split PDFs,
interpret module records, write evidence, or implement a module's Review UI.

The generalized relationship is:

```text
retained source scan
  -> source page
  -> detected payload
  -> validated RouteLocator, when available
  -> RouteRegistration
  -> ModuleRecordRef target, when available
  -> module-owned evidence or Review workflow
```

No shared step assumes a student, assignment, payload page number, submission
directory, Author, Subject, Group, or Score target.

## Shared active-scan layout

```text
<workspace>/
  scans_inbox/
  scans/
    source/
      YYYY-MM-DD/
        <retained source bytes>
    review/
      <failure_id>.json
      <optional review artifacts>
      resolutions/
        <resolution_id>.json
  classes/
    <class_id>/
      modules/
        <module_id>/
          work/
            <work_id>/
```

`scans_inbox/` remains the teacher-facing drop location.
`scans/source/YYYY-MM-DD/` contains canonical retained source bytes.
`scans/review/<failure_id>.json` contains immutable failure occurrences.
`scans/review/resolutions/<resolution_id>.json` contains immutable resolution
events. Module-owned evidence paths are determined by the selected module, not
by shared scan metadata.

The legacy `scans_archive_*` helpers retain their historical behavior but are
not the active retained-source contract. Historical preservation belongs to
`pds-sunset`.

## Retention and provenance

Every readable selected source is copied before module-specific parsing or
processing. The external original and retained bytes are never modified.
Retained filenames use:

```text
<UTC timestamp>__<sanitized-original-stem>__<short-sha256>.<ext>
```

The `RetainedSourceScan` result records the source filename, generated scan
ID, full SHA-256, workspace-relative retained path, intake timestamp, and
intake date. A repeated intake is a distinct event even when hashes match.
Writers never silently overwrite retained sources or metadata.

Failure and resolution provenance uses these fields:

```text
source_filename
source_scan_id
source_sha256
retained_source_path
review_copy_path
source_page_number
```

`source_filename` is always required because failure may occur before
retention. The retained-source identity triple (`source_scan_id`,
`source_sha256`, and `retained_source_path`) is either entirely present or
entirely null. A page failure has a positive source page number; a scan failure
has no source page number. Referenced files need not exist when metadata is
validated.

## PDS2 identity and dispatch

Raw decoded payload text is preserved separately from authoritative identity.
Only a complete, validated `RouteLocator` may be stored in `route_locator`.
Parser errors, candidate values, and incomplete observations belong in
`module_details`; Core never promotes guesses to identity.

When a target is known it is a complete validated `ModuleRecordRef`, its
module ID matches the locator, and its existence and meaning remain
module-owned. Core profiles select modules by exact module ID, resolve exact
route registrations, validate compatibility, and dispatch retained-source
pages independently.

## Failure and resolution records

Failure and resolution schemas are both version `"2"`. Version 1 data is
historical and rejected; there is no fallback reader or automatic conversion.

Failure records contain generic source, payload, route, target, and diagnostic
information. They are created exclusively, flushed with `fsync`, and never
edited or replaced. A second write using the same failure ID is a collision,
even if its bytes would be identical.

Resolutions are separate append-only events. Before appending a resolution,
Core loads its canonical linked failure and verifies its identity, version,
path, copied provenance, and timestamp ordering. Several distinct resolution
IDs may refer to one failure. Core does not create a mutable current-resolution
record, select a latest event, alter the failure, or delete earlier events.

The exact schemas, vocabularies, dispatch mapping, examples, persistence
behavior, and public APIs are specified in
[`scan_failure_resolution_metadata.md`](scan_failure_resolution_metadata.md).

## Ownership boundaries

PDS Core owns retained-source paths and copying, safe shared identifiers,
validated PDS2 routing structures, generic dispatch, strict metadata schemas,
immutable persistence, and module-neutral provenance.

Modules own payload extraction, semantic target validation, record loading,
students or other participant identities, Authors, Subjects, Groups, scoring,
evidence destinations, Review workflows, and all module-specific details.
Those details belong under `module_details` or in module-owned records.

## Public helper surface

The active helper surface includes:

```text
retain_source_scan
routing_failure_metadata_path
load_routing_failure_metadata
write_routing_failure_metadata
routing_failure_metadata_from_dispatch_failure
scan_resolution_metadata_dir
scan_resolution_metadata_path
create_scan_resolution_metadata
load_scan_resolution_metadata
write_scan_resolution_metadata
```

Path helpers are side-effect free. Loaders inspect only canonical paths and
strictly reject malformed JSON, invalid UTF-8, duplicate keys at any depth,
non-standard numeric constants, non-object roots, invalid schemas, and stored
ID mismatches.
