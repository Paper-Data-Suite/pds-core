# Active Scan Intake, Retention, and Routing Review Contract

## Status and Scope

This document defines the shared Paper Data Suite contract for active scan
intake, retained source scans, routed evidence, routing review, failure and
resolution metadata, and provenance.

The shared route, retained-filename, retained-source copy/provenance helper,
failure and resolution metadata validation, and safe metadata writing helpers
are implemented in `pds-core`. Scan routing, QR extraction, PDF splitting,
and module workflow adoption remain module work.

Shared module-profile discovery and page-by-page dispatch are also implemented.
Pages from one retained source may target different modules and are dispatched
independently, so an expected page failure does not stop later pages. Dispatch
does not itself write the failure or resolution metadata documented below;
generalized mapping of dispatch outcomes into those persisted schemas remains
separate follow-up work.

## Terminology

`scans_inbox/` is the existing teacher-facing scan intake/drop location. It
remains supported for compatibility.

An **active retained source scan** is the copy of a readable selected input
that Paper Data Suite preserves before module-specific parsing, scoring,
routing, or evidence generation. It represents one intake event and retains
its own identity even when its content matches a previously retained scan.

The **source scan store** is the canonical location for active retained source
scans: `scans/source/YYYY-MM-DD/`. The date bucket is the PDS intake date in
UTC.

**Routed scan evidence** is a copied or derived artifact associated with a
known class, assignment, or student. Assignment-level `scans/` and student
submission folders may contain routed evidence, but they are not the
canonical retained source location.

**Routing review** is the process and workspace area used to inspect failures,
ambiguities, conflicts, and unrouted scans or pages. Canonical routing failure
records live under `scans/review/`.

**Failure metadata** is one structured JSON record for one failure occurrence.
It records what failed, where it failed, validated identity information when
available, and provenance back to the retained source.

**Inactive historical preservation** covers closed or historical classes,
assignments, marking periods, school years, and related lifecycle policy.
Those workflows belong to `pds-sunset`, not active scan routing.

> Do not use "archive" for active source scans or current-year routing
> artifacts. Archiving is reserved for inactive historical preservation
> handled by `pds-sunset`.

## Shared Workspace Paths

The preferred shared active scan layout is:

```text
<PDS workspace root>/
  scans_inbox/
  scans/
    source/
      YYYY-MM-DD/
    review/
      resolutions/
  classes/
    <class_id>/
      assignments/
        <assignment_id>/
          scans/
          submissions/
            <student_id>/
```

The locations have these roles:

* `scans_inbox/` is the teacher-facing intake/drop location and is preserved
  for compatibility.
* `scans/source/YYYY-MM-DD/` is the active retained source scan store,
  date-bucketed by PDS intake UTC date.
* `scans/review/` contains canonical routing review records and may contain
  optional problem artifacts.
* `scans/review/resolutions/` contains immutable resolution records linked to
  failure records.
* `classes/<class_id>/assignments/<assignment_id>/scans/` contains routed scan
  evidence. It is not canonical source retention.
* `classes/<class_id>/assignments/<assignment_id>/submissions/<student_id>/`
  is the module-specific location for routed student evidence or a routed
  submission.

## Retained Source Scan Naming

The recommended collision-resistant filename pattern is:

```text
<UTC timestamp>__<sanitized-original-stem>__<short-sha256>.<ext>
```

For example:

```text
20260619T184512123456Z__scanner_export__a1b2c3d4e5f6.pdf
```

The naming rules are:

* The timestamp uses UTC and includes subsecond precision.
* The date bucket uses the PDS intake UTC date.
* The original filename stem is sanitized for safe use as one filename
  component.
* The original extension is preserved when it is safe.
* Metadata stores the full SHA-256 digest.
* The retained filename uses a short SHA-256 prefix.
* The module name is not part of the retained filename because routing may be
  unknown or the source may contain mixed modules.
* Repeated intake events must not silently overwrite each other.
* Matching hashes indicate possible duplicate content. They do not
  automatically authorize discarding an intake event.

The shared filename helper uses these exact rules:

* `intake_timestamp` must be timezone-aware and is converted to UTC.
* The timestamp is formatted as `YYYYMMDDTHHMMSSffffffZ`.
* The full caller-supplied SHA-256 value must contain exactly 64 hexadecimal
  characters; the filename uses its first 12 characters lowercased.
* Path-like original filenames are rejected.
* Runs outside ASCII letters, numbers, `_`, and `-` in the original stem are
  replaced with `_`, leading and trailing `_` are removed, and an empty result
  becomes `scan`.
* Supported extensions are `.pdf`, `.png`, `.jpg`, `.jpeg`, `.tif`, and
  `.tiff`; they are lowercased. Extensionless and unsupported filenames are
  rejected.
* The helper builds a name only. It does not check collisions or copy files.

## Copy, Retention, and Provenance Semantics

All Paper Data Suite modules handling active scans must:

1. Leave the teacher's original external file untouched.
2. Copy every readable selected source scan into the active source scan store
   before module-specific parsing, scoring, routing, or evidence generation.
3. Process the retained source scan, or maintain explicit provenance back to
   it when a workflow cannot process that copy directly.
4. Copy or derive routed evidence into assignment or student locations.
5. Not silently overwrite retained sources, review records, or routed
   evidence.
6. Preserve provenance from routed evidence back to the retained source scan.
7. Treat module-specific result attempts separately from source scan identity.

Source scan identity describes the retained intake event. A retry, scoring
attempt, routing attempt, or report export does not create a new source scan
identity unless a new source intake event occurred.

## Routing Failure Metadata

Store one JSON record per failure occurrence. The shared base shape is:

```json
{
  "schema_version": "1",
  "failure_id": "failure_...",
  "scope": "page",
  "stage": "routing",
  "created_at": "2026-06-19T18:45:12.123456Z",
  "failure_category": "assignment_unknown",
  "failure_message": "No matching workspace assignment was found.",
  "module": "quillan",
  "source_scan_id": "scan_...",
  "source_filename": "scanner export.pdf",
  "source_sha256": "...",
  "retained_source_path": "scans/source/2026-06-19/...",
  "review_copy_path": null,
  "source_page_number": 2,
  "detected_payload": "PDS1|...",
  "payload_page_number": 1,
  "class_id": "english12_p4",
  "assignment_id": "personal_narrative",
  "student_id": "1001",
  "module_details": {}
}
```

These fields are required and must be non-null:

```text
schema_version
failure_id
scope
stage
created_at
failure_category
failure_message
source_filename
module_details
```

These fields are required but may be null:

```text
module
source_scan_id
source_sha256
retained_source_path
review_copy_path
source_page_number
detected_payload
payload_page_number
class_id
assignment_id
student_id
```

Additional rules:

* Paths must be relative to the PDS workspace root.
* Identity fields must come from validated data, not guesses.
* Use `scope="scan"` for whole-file or batch-level failures.
* Use `scope="page"` for page-specific failures.
* One source scan may produce multiple failure records when multiple pages
  fail.
* Modules may add module-specific structured fields under `module_details`.
* Canonical failure records live in `scans/review/`.
* Do not duplicate failure JSON beside a retained source scan unless a later
  implementation ticket explicitly adopts a source-manifest design.

The shared helper layer stores canonical records as
`scans/review/<failure_id>.json`. Failure IDs and stages use the shared safe
identifier format. Writers use stable, indented UTF-8 JSON with a final
newline and exclusive file creation. Failure ID generation remains the
caller's responsibility.

### Shared failure categories

Shared validation recognizes these module-neutral categories:

```text
source_missing
source_unreadable
source_type_unsupported
source_retention_failed
payload_missing
payload_unreadable
payload_invalid
payload_schema_unsupported
module_unsupported
identifier_invalid
class_unknown
assignment_unknown
student_unknown
route_mismatch
route_ambiguous
page_conflict
processing_error
evidence_write_failed
```

Module-specific categories remain module-owned. For example:

* ScoreForm scoring failures are ScoreForm-specific.
* ScoreForm result export failures are ScoreForm-specific.
* Quillan submission completeness failures are Quillan-specific.
* OCR-related failures are module-specific unless a later shared OCR contract
  is defined.

## Scan Resolution Metadata

Resolution records live under
`scans/review/resolutions/<resolution_id>.json`. Failure records remain
immutable: a teacher or module decision is recorded in a separate immutable
resolution record linked by `failure_id` and optional
`failure_metadata_path`. A failure may have multiple resolution records as an
audit trail. The absence of a resolution record means the failure is
unresolved; Core does not select a latest resolution.

Shared statuses are `resolved` and `deferred`. Shared actions are
`manual_entry`, `manual_marks`, `rescan_needed`, `cannot_route`,
`mixed_assignment`, `evidence_filed`, `dismissed_duplicate`, and `other`.
Modules put structured module-specific information in `module_details` and
own all teacher-facing review UX, manual entry, result writing, and
module-specific outcomes and evidence.

Resolution metadata describes decisions in active workflows; it is not
historical archiving. Writing a resolution record does not delete scan
evidence or move a retained source. Assignment-local evidence remains routed
or resolution evidence, not canonical source retention.

## Relationship to Existing Scan Route Helpers

`pds_core.scan_routes` currently provides:

```python
scans_inbox_dir(...)
scans_archive_dir(...)
scans_archive_date_dir(...)
```

The `scans_archive_*` helpers are legacy and incorrectly named for active
source scan retention. Their behavior is unchanged by this contract, and they
must not be interpreted as the preferred active scan layout.

The preferred active source-scan and routing-review helper layer now provides:

```python
scans_root_dir(...)
scans_source_dir(...)
scans_source_date_dir(...)
routing_review_dir(...)
build_retained_source_filename(...)
retained_source_scan_path(...)
RetainedSourceScan
SourceRetentionError
retain_source_scan(...)
routing_failure_metadata_path(...)
validate_routing_failure_metadata(...)
write_routing_failure_metadata(...)
scan_resolution_metadata_dir(...)
scan_resolution_metadata_path(...)
ScanResolutionMetadata
ScanResolutionMetadataError
ScanResolutionMetadataWriteError
validate_scan_resolution_metadata(...)
scan_resolution_metadata_to_dict(...)
scan_resolution_metadata_from_dict(...)
write_scan_resolution_metadata(...)
```

The legacy helpers remain available with unchanged paths and exceptions. Core
implements the reusable retained-source copy and provenance operation, but it
does not route scans, decode QR codes, or split PDFs. ScoreForm and Quillan
adoption remain separate module work.

## Ownership Boundaries

### `pds-core`

`pds-core` owns the shared contract for:

* active source scan store paths;
* routing review paths;
* retained source naming;
* base failure metadata;
* shared failure categories;
* base resolution metadata and shared resolution statuses and actions;
* resolution record paths and exclusive writing;
* copy-first, no-overwrite, and provenance semantics;
* shared active-scan helpers and validators.

### Paper Data Suite modules

Modules own:

* QR extraction;
* scan splitting;
* payload interpretation beyond the shared `PDS1` model;
* scoring;
* routed evidence generation;
* routed submission assembly;
* teacher review UX;
* manual entry and result-writing decisions;
* module-specific resolution evidence;
* module-specific failure details;
* module-specific result and report formats.

### `pds-sunset`

`pds-sunset` owns:

* inactive historical preservation;
* end-of-year and closed-cycle archival workflows;
* inactive-data lifecycle rules.

## Backward Compatibility

This contract preserves the following behavior:

* `scans_inbox/` remains supported as the teacher-facing intake location.
* Existing `scans_archive_*` helper behavior is unchanged.
* Existing ScoreForm behavior is unchanged.
* Existing Quillan behavior is unchanged.
* Assignment-level `scans/` remains a valid routed-evidence location.

Active source/review path helpers, retained filename/path helpers, retained
source copying and provenance, failure and resolution metadata validation, and
exclusive metadata writing are implemented. No routing behavior, QR
extraction, PDF splitting, module migration, or legacy-helper deprecation is
implemented.
