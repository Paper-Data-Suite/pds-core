# Shared Roster and Workspace Contract

## Purpose

This document defines the shared Paper Data Suite contract for rosters, class
workspaces, and workspace-root behavior.

The central architecture decision is:

```text
Shared roster and workspace management belongs in pds-core.
```

The Core roster, class-folder, and workspace APIs described below are
implemented. Downstream adoption remains module work and should proceed through
focused migrations rather than a broad cross-repository refactor.

## Architecture Decision

Paper Data Suite modules should consume shared roster and workspace behavior
from `pds-core`:

```text
pds-scoreform -> pds-core
pds-quillan   -> pds-core
pds-concord   -> pds-core
```

Downstream modules must not depend on each other through shared roster use.

A separate shared dependency is not currently recommended because:

* `pds-core` already owns suite-level workspace and route conventions;
* `pds-core` already owns identifier validation;
* rosters, classes, student identity, and workspace setup are suite-level
  concepts;
* another package would add packaging and versioning complexity without a
  strong architectural boundary.

ScoreForm has the most mature current roster behavior, but that behavior should
not be moved into core unchanged. The shared contract should be module-neutral,
structured, and suitable for both ScoreForm and Quillan.

## Core Principles

The shared layer should own:

* roster creation/writing;
* roster validation;
* class setup;
* workspace settings;
* canonical student identity and display helpers.

Assignment behavior remains module-specific.

Shared core code must be UI-neutral. It should return data or raise structured
exceptions rather than print messages, prompt users, parse command-line
arguments, or render menus. Module CLI and menu behavior should be thin
wrappers around the shared APIs.

Teacher judgment remains primary. This layer must not introduce AI grading,
automated feedback, or automated writing judgment.

## Canonical Roster CSV

The baseline canonical roster schema is:

```csv
class_id,student_id,last_name,first_name,period
english9_p2,1001,Doe,Jane,2
english9_p2,1002,Smith,Marcus,2
english9_p2,1003,Brown,Alyssa,2
```

The required columns, in canonical order, are:

```text
class_id,student_id,last_name,first_name,period
```

Readers and validators must:

* read CSV files as UTF-8 and accept a UTF-8 byte order mark;
* treat every value as a string and preserve leading zeros in identifiers;
* trim surrounding whitespace from headers and values;
* reject missing required columns;
* reject blank required values;
* reject blank or duplicate headers after trimming;
* reject malformed rows containing more fields than the header;
* require at least one student row;
* validate `class_id` and `student_id` with the existing `pds-core`
  identifier rules;
* require one exact `class_id` throughout the roster;
* reject duplicate `student_id` values;
* preserve optional columns in their original order;
* permit blank optional values;
* avoid silently renaming, normalizing, or inferring identifiers.

Optional columns are roster metadata, not an automatic extension of every
module's output schema. Modules must explicitly choose whether an optional
field belongs in a result export.

## Roster Model and APIs

The implemented module is:

```python
pds_core.rosters
```

Public pieces include:

```python
ROSTER_REQUIRED_COLUMNS
StudentRecord
Roster
RosterIssue
RosterError
RosterReadError
RosterValidationError

load_roster(path) -> Roster
validate_roster_rows(...)
create_roster(class_id, students, ...) -> Roster
write_roster(path, roster, *, overwrite=False) -> None
add_student_record(roster, student) -> Roster
replace_student_record(roster, student) -> Roster
upsert_student_record(roster, student) -> Roster
remove_student_record(roster, student_id) -> Roster
student_display_name(student) -> str
student_sort_name(student) -> str
student_lookup(roster) -> Mapping[str, StudentRecord]
```

`StudentRecord` retains the canonical fields and ordered optional fields.
`Roster` retains the class ID, student records, source columns, and an optional
source path. The models preserve string values rather than coercing
identifier-like values to numbers.

Writing should be atomic where practical. Writers must not overwrite an
existing roster unless the caller explicitly sets `overwrite=True`.

In-memory roster mutation helpers return new validated `Roster` instances.
They preserve the roster source path and column order, require edited students
to match the roster `class_id`, and do not introduce optional columns
implicitly. These helpers do not read or write files, create directories,
alter assignments, delete generated materials, or rewrite historical results.
Removing a student means removing that student from the active roster object
only. ScoreForm and Quillan still own their own UI, menu, and workflow
wrappers.

These APIs work in tests and module-owned command or menu wrappers.

## Student Identity and Display

`student_id` is the canonical identity within a `Roster` and for roster
lookups. A module may reference it in module-owned records where that domain
requires student identity. It is not part of PDS2 payloads, shared Core route
identity, or mandatory scan routing metadata.

Names are for teacher display only. Shared helpers should provide consistent
forms such as:

```python
student_display_name(student)  # "Jane Doe"
student_sort_name(student)     # "Doe, Jane"
```

If a roster includes the optional `preferred_name` field, it may replace
`first_name` for display only. It must not replace `student_id` in the roster or
become a hidden identifier.

## Structured Diagnostics

Shared roster validation should produce structured diagnostics suitable for
tests and UI wrappers. A diagnostic should include, where applicable:

* a stable error code;
* the CSV row number;
* the column name;
* a readable message;
* the offending value, when safe and useful.

`RosterIssue` may represent individual diagnostics, while read and validation
exceptions may carry one or more issues. Exact class relationships can be
settled during implementation, but wrappers must not need to parse printed
text to understand a failure.

The shared layer must not print user-facing messages. ScoreForm and Quillan
wrappers may translate structured exceptions into terminal or menu output.

## Workspace Root

The existing workspace-root resolution priority is:

```text
1. Explicit runtime argument
2. PDS_WORKSPACE_ROOT environment variable
3. Saved user configuration
4. Default root
```

The default root is:

```text
~/Paper Data Suite
```

Shared workspace behavior includes:

* resolving the selected root;
* ensuring that the root exists and is writable;
* saving a user-selected root;
* clearing the saved root;
* reporting the configuration path;
* reporting the selected root and the source that selected it.

Changing or resetting workspace configuration must not automatically migrate,
move, copy, or delete user files.

The implemented public functions in `pds_core.workspace` include:

```python
WorkspaceStatus

inspect_workspace_root(explicit_root=None) -> WorkspaceStatus
ensure_workspace_root(path, create=True) -> Path
save_workspace_root(path) -> Path
clear_saved_workspace_root() -> bool
```

`WorkspaceStatus` exposes the resolved root, stable resolution source,
configuration path, default root, and basic non-mutating filesystem status.
This lets module wrappers report workspace state without duplicating resolution
logic or changing saved configuration.

## Workspace and Class Layout

The shared layout is:

```text
<PDS workspace root>/
  classes/
    <class_id>/
      roster.csv
      class.json
      modules/
        <module_id>/
          work/
            <work_id>/
              routes/
                <route_id>.json
              <module-owned descendants>
```

Existing route helpers are pure path constructors. Calling a route helper does
not create a directory or imply that every part of the returned route already
exists.

PDS Core owns canonical class, module, work, and route-registration paths.
Modules own the meaning of `work_id` and their descendants beneath a work
root. Core does not define a universal assignment root or student-submission
directory. A module may use assignments or students in its own domain model
without making either concept part of shared routing identity.

Directory creation belongs in explicit setup helpers. Class setup should:

* validate `class_id`;
* create the class directory;
* return useful path information.

Class setup must not:

* create module work or route-registration directories;
* create module-owned descendants;
* synthesize a roster;
* overwrite an existing roster.

Roster creation is a separate, explicit operation.

## Class Folder APIs

A current shared module is:

```python
pds_core.classes
```

Public pieces include:

```python
ClassFolder

class_folder(root, class_id) -> ClassFolder
ensure_class_folder(root, class_id) -> ClassFolder
load_class_roster(root, class_id) -> Roster
write_class_roster(root, roster, *, overwrite=False) -> Path
list_class_folders(
    root,
    *,
    require_roster=False,
    load_rosters=False,
    require_metadata=False,
    load_metadata=False,
) -> tuple[ClassFolder, ...]
```

`ClassFolder` provides the validated class ID and useful canonical paths,
including the class directory, roster path, and class metadata path. When
requested through `list_class_folders(..., load_rosters=True)` or
`list_class_folders(..., load_metadata=True)`, it may also carry loaded roster
or metadata data.

Class folder listing handles invalid entries deterministically. Invalid folder
names are skipped rather than reinterpreted. When roster loading is requested,
invalid or mismatched rosters are also skipped.

## CLI and Menu Wrappers

Core owns the implemented `pds-core` command namespace and the `core`
teacher-facing menu for shared standards and workspace management. Modules own
their branding and module-specific workflows and may expose thin wrappers over
shared behavior. Core's direct workspace operations are:

```text
pds-core workspace show
pds-core workspace set <path>
pds-core workspace validate
pds-core workspace reset
pds-core workspace paths
```

Wrapper behavior should be consistent:

* `workspace show` reports the resolved root, source, config path, and default;
* `workspace set` creates or validates and saves the root without migrating
  files;
* `workspace reset` clears only saved configuration;
* `workspace paths` is read-only;
* shared commands format structured exceptions for users; and
* module wrappers retain ownership of module-specific roster and class UX.

## Module Boundaries

### ScoreForm

ScoreForm retains ownership of:

* answer keys;
* the ScoreForm assignment schema;
* OMR templates;
* printable answer-sheet generation;
* mark detection;
* OMR scoring;
* QR-aware scan scoring;
* the result CSV schema;
* attempt handling;
* ScoreForm PDF filenames;
* scan diagnostics;
* debug artifacts;
* assignment-specific folder and output behavior.

### Quillan

Quillan retains ownership of:

* writing assignment configuration;
* printable writing-response layout;
* writing-response PDF generation;
* submission evidence records;
* requirements records;
* teacher tags;
* teacher notes;
* teacher-entered or teacher-confirmed scores;
* feedback records;
* writing reports;
* future scan routing and submission assembly.

Neither module should duplicate canonical roster parsing, validation, student
identity, class setup, or workspace settings.

## ScoreForm Migration

ScoreForm migration requires a compatibility layer because current callers may
expect:

* dictionaries rather than shared model objects;
* printed messages;
* `None` for invalid roster input;
* existing CLI or menu wording;
* current result-enrichment behavior.

The migration should introduce a compatibility adapter over shared roster APIs,
then move callers incrementally. A broad direct replacement in one pull request
is not recommended. ScoreForm assignment and scoring behavior should remain
unchanged while roster ownership moves to core.

## Quillan Integration

Quillan is an easier early consumer because its roster behavior is less
established.

Important integration points are:

* printable response generation currently accepts ad hoc student mappings;
* future printable generation should consume shared roster and student records;
* display names should come from `student_display_name`;
* Quillan should verify roster and class consistency before generating
  class-routed PDFs;
* Quillan should eventually expose the same workspace wrapper behavior as
  ScoreForm.

## Downstream Follow-Ups

### Module-owned outputs

Quillan `reports/`, ScoreForm results, and comparable module outputs are
module-owned descendants beneath a module-qualified work root. Core does not
define a universal shared `results/`, assignment, or submission layout. Each
downstream migration must document its own target paths.

### Python version compatibility

Core v0.5.0 requires Python `>=3.11`. A downstream module must raise its own
requirement to Python 3.11 or newer before depending on this release.

## Migration Sequence

The shared roster models, validation, atomic writing, class helpers, workspace
status, and workspace configuration helpers are implemented in Core. ScoreForm,
Quillan, and Concord adoption remains in their downstream issues. Compatibility
adapters, if required, remain module-owned and should be removed only after
consumers and documentation have migrated.

## Non-Goals

This contract does not include:

* a ScoreForm refactor;
* Quillan CLI or menu implementation;
* scan routing;
* OCR;
* SIS integration;
* Google Classroom import;
* automatic roster syncing;
* cloud roster storage;
* AI grading;
* AI feedback generation;
* automated writing judgment;
* a ScoreForm scoring redesign;
* a Quillan writing-model redesign.

## Summary

`pds-core` is the shared owner of roster parsing, roster validation, student
identity helpers, class setup, workspace settings, and shared class-level path
conventions. ScoreForm, Quillan, and Concord remain responsible for their own
module-qualified work, output, and teacher-workflow behavior.

This boundary keeps shared data contracts consistent without coupling the
modules to each other or moving UI and educational judgment into the core
package.
