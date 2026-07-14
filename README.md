# PDS Core

PDS Core contains shared contracts and infrastructure for Paper Data Suite
modules.

Shared responsibilities include:

- identifier validation;
- strict PDS2 page-locator payload parsing and canonical serialization;
- generic PDS2 routing identity and registration models;
- deterministic module-qualified route/path construction;
- explicit and installed module-profile registration with page dispatch;
- version 2 generic scan-failure metadata and append-only resolution events;
- generic opening of existing local files and directories in the system viewer;
- active scan intake, source retention, and routing review contracts;
- workspace-root conventions.

PDS Core is intended to be used by:

- `pds-scoreform`
- `pds-quillan`
- `pds-concord`

## PDS2 Routing Identity API

PDS Core implements strict PDS2 payload parsing and serialization in
`pds_core.pds2`. Parsing accepts the required `m`, `c`, `w`, and `r` fields in
any order and returns a validated `RouteLocator`; serialization emits the
canonical compact form:

```text
PDS2|m=<module_id>|c=<class_id>|w=<work_id>|r=<route_id>
```

The payload is ASCII-only, contains exactly those four fields, and has a hard
limit of 256 bytes. PDS1 and OMR1 are not supported.

PDS Core also implements the generic PDS2 routing identity and registration
API in `pds_core.routing_models`, including `ModuleWorkRef`, `RouteLocator`,
`ModuleRecordRef`, `RouteRegistration`, and the runtime-only
`RouteResolution`. Exact mapping conversion, shared registration statuses, and
JSON-safe module details validation are included.
`pds_core.route_ids.generate_route_id()` provides non-semantic,
collision-resistant route IDs using standard-library secure randomness.
Module-qualified work roots use
`classes/<class_id>/modules/<module_id>/work/<work_id>/`. Route registrations
are created and loaded through `pds_core.route_registrations` at deterministic
paths beneath each work root. Creation is exclusive and never overwrites an
existing route; loading requires the persisted locator to match the requested
locator exactly.

See [`docs/pds2_payload_contract.md`](docs/pds2_payload_contract.md) for the
payload grammar, limits, public API, and error contract. See
[`docs/routing_identity_models.md`](docs/routing_identity_models.md) for
identity composition, serialized shapes, validation rules, and ownership
boundaries. See
[`docs/module_qualified_workspace.md`](docs/module_qualified_workspace.md) for
the implemented workspace paths, safe module-owned descendants, persisted
registration behavior, and runtime resolution contract.

PDS Core also implements runtime module profiles and per-page dispatch in
`pds_core.module_profiles` and `pds_core.module_dispatch`. Applications may
register profiles explicitly or discover zero-argument providers from the
`paper_data_suite.modules` Python entry-point group. Core contains no
hard-coded ScoreForm, Quillan, or Concord imports, never derives an import path
from a QR module value, and rejects unknown module IDs explicitly before route
registration lookup. Mixed-module batches preserve page order and isolate
expected failures. See
[`docs/module_profiles_and_dispatch.md`](docs/module_profiles_and_dispatch.md)
for the public profile, registry, discovery, compatibility, and dispatch
contract.

PDS Core implements routing failure and resolution schema version `"2"` in
`pds_core.scan_failure_metadata` and `pds_core.scan_resolution_metadata`.
Failure files are immutable and created exclusively at
`scans/review/<failure_id>.json`; resolutions append separately at
`scans/review/resolutions/<resolution_id>.json`, and several resolutions may
reference one failure. Shared metadata contains no universal student or
assignment fields. It stores raw payload separately from an optional validated
`RouteLocator`, and accepts an optional validated `ModuleRecordRef` target.
See
[`docs/scan_failure_resolution_metadata.md`](docs/scan_failure_resolution_metadata.md)
for exact schemas, dispatch mapping, linkage checks, and module ownership.

### Shared Menu Navigation

PDS modules should use `pds_core.menu_navigation` for teacher-facing controlled
prompts that support `B. Back`, `M. Main Menu`, and `Q. Quit`. Modules should
catch `ReturnToMainMenu` at their main-menu boundary and `QuitPDS` at their
top-level interactive entry point. The module handles parsing, labels, hints,
and unwind signals; it does not handle screen clearing, app headers, or
workflow logic.

Module-specific scoring, tagging, PDF layout, and reporting logic should remain in the module repositories.

Module wrappers can use `pds_core.local_open.open_local_path(...)` to ask the
operating system to open an existing local file or directory in its default
application. The helper rejects URLs and does not create or modify paths.

## Current Status

Version 0.5.0 is a supported pre-1.0 Core release. It implements the PDS2
routing contract and shared infrastructure described below. Pre-1.0 releases
may make intentional breaking changes, and only the latest supported minor line
receives fixes unless otherwise documented.

## Installation

PDS Core v0.5.0 requires Python 3.11 or newer. See the
[v0.5.0 release notes](docs/releases/v0.5.0.md) for compatibility details,
breaking changes, and migration guidance.

Install the verified wheel attached to the GitHub Release:

```powershell
python -m pip install .\pds_core-0.5.0-py3-none-any.whl
python -m pip check
```

Downstream packages should declare:

```text
pds-core>=0.5,<0.6
```

For local sibling-repository development:

```powershell
python -m pip install -e "../pds-core"
```

Version 0.5.0 is distributed through the GitHub Release. This release does not
publish to PyPI.

Active implementation guidance begins with
[`docs/pds2_module_integration.md`](docs/pds2_module_integration.md). The
[`migration_plan.md`](migration_plan.md) file is retained only as a superseded
historical PDS1/OMR1 plan and is not current guidance.

See [`docs/pds2_payload_contract.md`](docs/pds2_payload_contract.md) for the
active QR payload text contract. The earlier
[`docs/qr_payload_and_routing_contract.md`](docs/qr_payload_and_routing_contract.md)
is retained only as a superseded historical design record.

See [`docs/roster_workspace_contract.md`](docs/roster_workspace_contract.md) for the shared roster and workspace contract.

See [`docs/active_scan_contract.md`](docs/active_scan_contract.md) for the
defined active scan intake, retained source, routing review, failure metadata,
and provenance contract. Source retention, PDS2 routing and dispatch, immutable
version 2 failure records, strict loaders, and append-only linked resolutions
are implemented. Image decoding, PDF splitting, module-owned evidence, and
downstream Review adoption remain module work; legacy `scans_archive_*`
behavior is preserved.

See [`docs/standards_contract.md`](docs/standards_contract.md) for the shared
standards contract. PDS Core owns durable standard definitions, reusable
standards profiles, workspace standards storage, browsing/filtering helpers,
and module-neutral standards usage events; modules should store shared
`standard_id` references and keep module-specific feedback or alignment
behavior in module-owned data. The same contract preserves the historical
v0.4.0 planning audit whose implemented management surface ships in v0.5.0.

See [`docs/module_standards_integration.md`](docs/module_standards_integration.md)
for the practical integration expectations for `pds-quillan`, `pds-scoreform`,
and future modules that consume shared `pds-core` standards management.

See [`docs/standards_management_workflow.md`](docs/standards_management_workflow.md)
for the smoke-tested CLI, menu, import/export, and module selection workflow.

See [`docs/cli_menu_parity.md`](docs/cli_menu_parity.md) for the durable
teacher-menu/non-interactive CLI parity policy, complete capability matrix,
current partial-parity findings, and linked implementation follow-up.

See [`docs/workspace_management.md`](docs/workspace_management.md) for
teacher-facing workspace status, setup, validation, reset, and clean simulation
workspace workflows.

See [`docs/starter_standards.md`](docs/starter_standards.md) for bundled
starter standards packs, including the installable 2023 NJSLS-ELA high school
starter library and English 10 / English 12 reusable profiles.

See [`docs/decisions/README.md`](docs/decisions/README.md) for accepted
architecture decisions. ADR 0001 establishes PDS2 page-locator routing,
persisted route registrations, module-qualified work identity, and the removal
of PDS1 and OMR1 support; it is implemented by v0.5.0.

## Standards CLI

Teachers can type the module shortcut to open the current pds-core menu:

```powershell
core
```

The `core` shortcut opens a plain-text Paper Data Suite Core menu. Standards
Management and Workspace Settings are available from that menu. The existing
`pds-core` command remains the full CLI namespace for direct commands and
scripts, and `pds-core standards menu` remains available as the direct
standards route.

PDS Core exposes `pds-core standards` commands for inspecting, validating,
importing, exporting, and mutating the active workspace standards library:

```powershell
pds-core --workspace "C:\Path\To\Paper Data Suite" standards list
pds-core standards menu
pds-core standards show njsls-ela:RL.CR.11-12.1
pds-core standards search evidence --all
pds-core standards subjects
pds-core standards sources
pds-core standards domains
pds-core standards categories
pds-core standards profiles
pds-core standards profile create --profile-id english_12_njsls --title "English 12 NJSLS" --standard njsls-ela:RL.CR.11-12.1
pds-core standards profile replace english_12_njsls --title "English 12 NJSLS" --standard njsls-ela:RL.CR.11-12.1
pds-core standards profile add-standard english_12_njsls njsls-ela:RI.CR.11-12.1
pds-core standards profile remove-standard english_12_njsls njsls-ela:RI.CR.11-12.1
pds-core standards profile validate english_12_njsls
pds-core standards profile show english_12_njsls
pds-core standards validate
pds-core standards validate-file ".\standards-library.json"
pds-core standards starter list
pds-core standards starter preview njsls_ela_2023
pds-core standards starter validate
pds-core standards starter install njsls_ela_2023
pds-core standards export ".\standards-library.json"
pds-core standards import ".\standards-library.json" --replace
pds-core standards add --standard-id local-reading:close_reading --code CR.1 --source "Local Reading" --short-name "Close Reading" --description "Use evidence from a text."
pds-core standards replace local-reading:close_reading --code CR.1 --source "Local Reading" --short-name "Close Reading" --description "Use stronger textual evidence."
pds-core standards upsert local-reading:close_reading --code CR.1 --source "Local Reading" --short-name "Close Reading" --description "Use evidence from a text."
pds-core standards retire local-reading:close_reading
pds-core standards reactivate local-reading:close_reading
pds-core standards profile export english_12_njsls ".\english-12-profile.json"
pds-core standards profile import ".\english-12-profile.json" --add
```

The CLI loads `<workspace>/standards/library.json` using the normal workspace
resolution rules, or the non-mutating `--workspace` override for one command.
If the library file is missing, read-only commands treat it as an empty library
and do not create `standards/`, usage folders, workspace metadata, or module
folders.
Mutation commands write only the canonical
`<workspace>/standards/library.json`; they may create the `standards/`
directory and library file, but do not create usage ledgers or module-specific
folders.

Starter standards install optional shared definitions and reusable profiles
into the same canonical library. The bundled `njsls_ela_2023` pack contains
64 parent standards and 71 first-class lettered subskills. Its English 10 and
English 12 profiles include both kinds of record so modules can select either
by durable `standard_id`; no hierarchy schema or parent/child rollup is
implied. Subskill `short_name` values pair the parent skill with a concise,
teacher-readable description-derived label. Install merges missing records,
skips identical records, refuses conflicts by default, and requires
`--overwrite` to replace conflicting starter records. Starter install does not
record usage events.

Use `standard_id` and `profile_id` for durable Paper Data Suite references.
Teacher-facing `code`, profile titles, and sources are display fields and may
not be unique.

For an end-to-end synthetic workflow with add, profile, validation,
import/export, menu, and module API examples, see
[`docs/standards_management_workflow.md`](docs/standards_management_workflow.md).

## Module Standards Selection API

Downstream modules can use `pds_core.standards_selection` to browse and
validate standards without knowing the workspace storage path or standards JSON
shape. The helpers load missing workspace libraries as empty, read-only
libraries and do not create files or folders.

For module ownership boundaries, durable ID rules, Quillan and ScoreForm
examples, missing/deprecated standards behavior, and future-module guidance,
see [`docs/module_standards_integration.md`](docs/module_standards_integration.md).
For a compact executable-style workflow, see
[`docs/standards_management_workflow.md`](docs/standards_management_workflow.md).

Modules should store only durable `standard_id` and `profile_id` values.
Returned labels, standard `code` values, profile titles, and sources are for
teacher display only and should not be stored as durable references. Standard
selection labels use `code | short_name | source` (plus `[inactive]` when
applicable); the durable ID remains available separately as `item.standard_id`.

```python
from pds_core.standards_selection import (
    list_profiles_for_selection,
    list_standards_for_profile_selection,
    load_standards_for_selection,
    resolve_profile_standard_selection,
)

library = load_standards_for_selection(workspace_root)
profiles = list_profiles_for_selection(library, course="English 12")
standards = list_standards_for_profile_selection(library, "english_12_njsls")
selected = resolve_profile_standard_selection(
    library,
    profile_id="english_12_njsls",
    selected_standard_ids=["njsls-ela:RL.CR.11-12.1"],
)
```

The selection API is module-neutral and does not import ScoreForm or Quillan.
It validates profile-member selections with the shared standards backend and
raises `StandardsValidationError` for missing IDs, duplicates, unknown
standards, or standards outside the selected profile.

`pds-core standards menu` opens a plain-text teacher-facing management menu for
the shared workspace standards library. It distinguishes durable
`standard_id`/`profile_id` values from display fields, confirms before writing,
and does not support destructive standard or profile deletion.

Profiles group standards for reuse by storing ordered durable `standard_id`
references. `profile create` adds a new durable `profile_id`; `profile replace`
is full-record replacement and clears omitted optional metadata and membership.
`profile add-standard` appends one standard reference, and `profile
remove-standard` removes one membership reference only. It does not delete the
standard definition. `profile validate`, `profile show`, `profile import`, and
`profile export` remain available. Destructive profile deletion is not
supported in v0.5.0.

Individual standard mutation commands require `code`, `source`, `short-name`,
and `description`. `add` also requires `--standard-id`; `replace` and `upsert`
take the durable ID as the positional `standard_id`. Optional metadata includes
`--subject`, `--course`, `--grade-band`, `--domain`, `--category-path`, `--tag`,
`--available-module`, `--active`, and `--inactive`. Category paths use `/`, for
example `--category-path "English Language Arts/Reading Literature/Close
Reading"`. Repeat `--tag` or `--available-module` for multiple values.

`replace` is full-record replacement, so omitted optional fields are cleared.
`upsert` adds or replaces as appropriate. `retire` is non-destructive: it marks
the standard inactive and leaves the record in the library, so historical data
and profile references remain valid. `reactivate` marks a retired standard
active again. There is no destructive standard deletion command in v0.5.0.

Import and export commands are deliberately conservative. Imports validate the
entire external JSON file before writing anything. Full-library import requires
`--replace`; replacing an existing workspace `standards/library.json` also
requires `--overwrite`. Profile import supports `--add`, which fails rather
than silently replacing an existing `profile_id`. Exports refuse to overwrite
target files unless `--overwrite` is supplied. Merge/upsert import remains
future work; module-facing selection APIs are available in
`pds_core.standards_selection`.

## Workspace Root

The PDS workspace root is the top-level folder where Paper Data Suite modules
store user data and generated working files. It is separate from the source,
installed package, virtual environment, and current working directory.

The default is:

```text
~/Paper Data Suite
```

Resolution uses this precedence:

1. An explicit runtime argument to `resolve_workspace_root(...)`.
2. The `PDS_WORKSPACE_ROOT` environment variable.
3. The saved user configuration.
4. The default above.

Saved configuration lives outside the workspace:

- Windows: `%APPDATA%\Paper Data Suite\config.json`
- macOS: `~/Library/Application Support/Paper Data Suite/config.json`
- Linux/Unix: `$XDG_CONFIG_HOME/paper-data-suite/config.json`, falling back to
  `~/.config/paper-data-suite/config.json`

For example, a workplace OneDrive folder can be saved as the normal workspace:

```python
from pds_core.workspace import ensure_workspace_root, save_workspace_root

root = ensure_workspace_root(
    r"C:\Users\teacher\OneDrive - District Name\Paper Data Suite"
)
save_workspace_root(root)
```

Consuming modules resolve the root and pass it to the module-qualified helpers:

```python
from pds_core.routes import module_work_dir
from pds_core.routing_models import ModuleWorkRef
from pds_core.workspace import resolve_workspace_root

workspace_root = resolve_workspace_root()
work = ModuleWorkRef("quillan", "english12_p4", "personal_narrative")
path = module_work_dir(workspace_root, work)
```

An explicit root applies only to that call and does not change saved
configuration. `ensure_workspace_root()` can create and validate a workspace,
including a small `.pds/workspace.json` marker and the shared baseline folders
`classes/`, `scans_inbox/`, `scans/source/`, and `scans/review/`. It does not
create module-specific data folders or files.

Use `clear_saved_workspace_root()` to forget the saved workspace preference and
fall back to the environment variable or default root. Clearing the setting
does not delete the workspace folder, `.pds/` metadata, or user data.

Teacher-facing workspace management is available from:

```text
core
-> Workspace Settings
```

The direct CLI commands are:

```powershell
pds-core workspace show
pds-core workspace set "C:\Path\To\Paper Data Suite"
pds-core workspace validate
pds-core workspace reset
pds-core workspace paths
```

`workspace show` and `workspace paths` are read-only. `workspace validate`
creates or verifies the workspace root and initializes this shared baseline
structure:

```text
<workspace>/
  .pds/
    workspace.json
  classes/
  scans_inbox/
  scans/
    source/
    review/
```

It does not create class rosters, module work roots, standards libraries, usage
ledgers, review records, feedback exports, reports, generated answer sheets,
scored results, or date-bucketed scan folders. `workspace reset` clears only
the saved preference and does not delete workspace data. See
[`docs/workspace_management.md`](docs/workspace_management.md) for the full
teacher workflow.

## Development Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Run the complete validation sequence with:

```powershell
.\run_tests.ps1
```

This runs pytest, Ruff, mypy, and `git diff --check`.

## Project Policies

- See [`CHANGELOG.md`](CHANGELOG.md) for development history.
- See [`SECURITY.md`](SECURITY.md) for security and student-data guidance.
- PDS Core is available under the [MIT License](LICENSE).
