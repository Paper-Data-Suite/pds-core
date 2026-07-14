# Module-Qualified Workspace and Route Registrations

PDS Core implements the module-qualified workspace contract established by
[ADR 0001](decisions/0001-adopt-pds2-page-locator-routing.md). A work identity
is complete only when it contains:

```text
module_id + class_id + work_id
```

A route identity adds `route_id`. A bare `work_id` or `route_id` is not a
suite-wide identity, and different modules may reuse the same work identifier
in the same class without colliding.

## Canonical layout

The shared layout is:

```text
<workspace>/
  classes/
    <class_id>/
      class.json
      roster.csv
      modules/
        <module_id>/
          work/
            <work_id>/
              routes/
                <route_id>.json
```

Examples for the initial modules are:

```text
classes/english9_p2/modules/scoreform/work/rj_act1_quiz/
classes/english12_p4/modules/quillan/work/personal_narrative/
classes/english10_p3/modules/concord/work/socratic_seminar_1/
```

A Concord registration has this deterministic location:

```text
classes/
  english10_p3/
    modules/
      concord/
        work/
          socratic_seminar_1/
            routes/
              rt_0123456789abcdef0123456789abcdef.json
```

Core never recursively searches the workspace to find a registration and does
not fall back to the former `classes/<class_id>/assignments/<assignment_id>/`
layout.

## Path API

`pds_core.routes` provides deterministic constructors that accept a string or
`Path` root and perform no filesystem access:

- `classes_dir(root)`
- `class_dir(root, class_id)`
- `class_roster_path(root, class_id)`
- `class_metadata_path(root, class_id)`
- `class_modules_dir(root, class_id)`
- `class_module_dir(root, class_id, module_id)`
- `module_work_collection_dir(root, class_id, module_id)`
- `module_work_dir(root, work)`
- `module_routes_dir(root, work)`
- `route_registration_path(root, locator)`
- `safe_module_work_descendant(root, work, relative_path)`

`module_work_dir` and `module_routes_dir` require an actual validated
`ModuleWorkRef`. `route_registration_path` requires an actual validated
`RouteLocator`; mappings, payload strings, registrations, tuples, and separate
identity arguments are not convenience inputs. All identity-bearing path
components use Core's safe ASCII identifier contract, and `module_id` must be
lowercase.

The helpers do not resolve a workspace preference, expand `~` or environment
variables, normalize case, resolve symlinks, inspect metadata, require a module
installation, create directories, or require paths to exist.

## Safe module-owned descendants

Core owns the canonical work root. The module owns all other meaning and
organization beneath it. Modules use `safe_module_work_descendant` to construct
their own paths without permitting lexical escape from that root.

Accepted examples include:

```text
activity.json
pages/page_1.json
artifacts/artifact_1/pages/page_1.json
attachments/source notes.pdf
.hidden/module-state.json
```

Rejected examples include empty paths, `.` or `..` components, doubled or
trailing separators, NUL characters, leading or trailing whitespace, POSIX
absolute paths, Windows absolute or rooted paths, drive-qualified paths, UNC
paths, and traversal written with either slash style:

```text
../outside.json
pages/../../outside.json
pages/./page_1.json
/absolute/path.json
\absolute\path.json
C:\absolute\path.json
C:relative-drive-path.json
\\server\share\path.json
pages//page_1.json
pages/
```

Unsafe paths raise `ModuleWorkPathError`; they are never sanitized. This is a
lexical guarantee and does not follow symlinks. A workflow opening an existing,
untrusted symlink must apply any stronger filesystem containment it needs.

## Persisted route registrations

`pds_core.route_registrations` persists the exact seven-key mapping produced by
`route_registration_to_dict(registration)`. JSON is UTF-8, sorted, indented by
two spaces, standards-compliant (no non-finite numbers), and ends in exactly
one newline. It uses registration `schema_version` `"1"`; that version is
independent of PDS2 payload syntax and the package version.

`write_route_registration(root, registration)` validates before filesystem
mutation, creates only the canonical parent hierarchy, and creates the file
exclusively. It flushes and synchronizes the completed stream before returning.
An existing path is always a collision—even when its contents are identical—and
raises `RouteRegistrationWriteError` without modifying the existing file.
There is no overwrite, update, repoint, upsert, delete, or repair API.

`load_route_registration(root, locator)` opens exactly the path calculated by
`route_registration_path`. It rejects invalid UTF-8, malformed or non-object
JSON, non-standard numeric constants, duplicate keys at any object depth,
unknown or missing schema keys, and invalid model fields. It then requires the
stored locator to equal the requested locator in schema, module, class, work,
and route identity. A file at the expected path is not trusted merely because
it exists.

The persistence errors are:

- `RouteRegistrationPersistenceError`: base persistence error.
- `RouteRegistrationWriteError`: exclusive creation or completion failed.
- `RouteRegistrationReadError`: stored data or filesystem reading failed.
- `RouteRegistrationNotFoundError`: the canonical path is absent.
- `RouteRegistrationIntegrityError`: stored locator and requested locator differ.

Structurally valid `active`, `inactive`, `retired`, `superseded`, `cancelled`,
and `invalidated` registrations all remain loadable. Core validates the generic
`ModuleRecordRef`, but does not require its target file to exist or interpret
its record kind.

## Runtime resolution

`resolve_route_registration(root, locator)` loads the exact registration and
returns a `RouteResolution` containing the requested locator, loaded
registration, canonical class root, module root, and work root. Resolution does
not parse payload text, discover or dispatch to a module, load a target record,
create evidence, or authorize processing or scoring. In particular, successful
resolution of a non-active registration is structural information, not
processing authorization.

```python
from pds_core.pds2 import parse_pds2_payload
from pds_core.route_registrations import (
    load_route_registration,
    resolve_route_registration,
    write_route_registration,
)
from pds_core.routes import (
    module_work_dir,
    route_registration_path,
    safe_module_work_descendant,
)

locator = parse_pds2_payload(
    "PDS2|m=concord|c=english10_p3|w=socratic_seminar_1|"
    "r=rt_0123456789abcdef0123456789abcdef"
)

registration_path = route_registration_path(workspace_root, locator)
work_root = module_work_dir(workspace_root, locator.work)
artifact_path = safe_module_work_descendant(
    workspace_root,
    locator.work,
    "artifacts/artifact_1/pages/page_1.json",
)

# After constructing and validating a RouteRegistration:
persisted_path = write_route_registration(workspace_root, registration)
loaded = load_route_registration(workspace_root, locator)
resolution = resolve_route_registration(workspace_root, locator)
```

Modules must persist a registration successfully before rendering or issuing
the corresponding physical page.

## Removed universal paths

The former universal assignment and student-submission path helpers have been
removed. Assignment records, activities, artifacts, responses, answer sheets,
submissions, reviews, scores, and other descendants are module-owned concepts
beneath a module-qualified work root. Core does not select a module implicitly
or map old assignment paths into the new layout.
