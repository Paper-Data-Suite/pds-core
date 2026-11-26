# Core #242 — Callable Workspace & Classroom Management menu

**Slice A1 status:** Gated in-process entry point and synthetic navigation-only
acceptance on the issue branch. **Not yet a usable menu.**
**Base:** Core `main` at `3e4ea93dc9130c6b532cd33376ced9b8a5f2b068`
after approved #241 squash merge.
**No intermediate Core release:** release consolidation is #244.

## Scope and ownership

Core #242 composes **one reusable teacher-facing utility** that can be invoked
inside Core or from a qualified producer without launching a second process.
It covers workspace selection and settings, active school year, existing
classes and class metadata, canonical rosters, guarded full-roster import,
guarded single-student add/update/remove, and Standards Library management.

The utility must call existing Core services, not create an alternate
writer, roster identity database, school-year policy, or standards store.
Core never opens or mutates producer-owned grades, scans, reviews or work.

| Scope | Existing authority to reuse | Relevant direct CLI |
| --- | --- | --- |
| Workspace | `pds_core.workspace` | `pds-core workspace ...` |
| School years | `pds_core.school_years` | Identify CLI gaps before enabling writes |
| Classes / metadata | `pds_core.classes` and `class_metadata` | Add parity only for enabled writes |
| Complete roster import | `pds_core.roster_imports` | `roster import-preview/import-commit` |
| One student edit | `pds_core.roster_edits` (#241) | `roster student-preview/student-commit` |
| Standards | `pds_core.standards` and existing menu | `pds-core standards ...` |

## Public callable contract — unchanged from Core #236

```python
def run_workspace_classroom_menu(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    interactive: bool,
    error_output: TextIO | None = None,
) -> SharedTeacherMenuResult: ...
```

This is an in-process function; it does not call the Core executable,
install a global input hook, take over a producer's event loop, or treat
the caller's hints as authority. It preserves the caller's opaque
`return_token` without printing it.

`SharedTeacherMenuResult` separates navigation (`BACK`, `MAIN_MENU`,
`QUIT`, `CANCELLED`, `FAILED`, `UNAVAILABLE`) from durability
(`NO_CHANGE`, `COMMITTED`, `PARTIAL`, `INDETERMINATE`) and changed
Core domains (`WORKSPACE`, `SCHOOL_YEAR`, `CLASS`, `ROSTER`,
`STANDARDS`). `B` leaves the current submenu, then returns to the
caller at top level. `M` and `Q` must be passed to the owning caller,
not applied as a global subprocess exit.

**Unconditional caller obligation:** after *any* shared menu return,
even when `NO_CHANGE` is reported, the producer must revalidate its
workspace, active school year, selected class, roster/student, own work
revision and authorization before consequential continuation. A return
token and change-scope hint are **not** proof of freshness or permission.

## Slice A1 delivered now

`pds_core.teacher_menus.run_workspace_classroom_menu` is importable,
validates its injected I/O and request inputs, and **fails closed** with
`UNAVAILABLE` and `NO_CHANGE`, without prompting or reading workspace
state. `classroom.menu.v1` stays unadvertised.

A private **test-only** switch enters a synthetic navigation preview.
Its pages map workspace/year, classes/rosters and Standards, with B/M/Q
and EOF semantics. The test-only tree never invokes storage/services,
no-ops the menu data operations, and cannot claim a durable change.
These pages are **not** represented as functioning teacher workflows.

## Build slices, each with implementation and acceptance

**A — Frozen callable and navigation contract (this slice).**
Gated public entry, unqualified negative behavior, test-only nested menu
navigation, injected-input invariants, no import-time side effects.
Do not change existing Core menu choices or expose a new capability.

**B — Authoritative read-only discovery.**
Resolve the workspace and school-year context from Core; list validated
classes and display roster/student identities with ambiguity-safe ID
disambiguation. Distinguish missing data, malformed state, and unsafe
paths. Do not cache caller hints as permission/currentness. Preserve B/M/Q.

**C — Guarded workspace, year, class and Standards workflows.**
Reuse existing handlers and domain services. For every consequential
operation: authoritative preview and single meaningful confirmation,
freshness and strict cancellation boundaries, accurate change scopes and
bounded failures. Add missing direct noninteractive CLI parity before
exposing any new durable menu action. Refuse ambiguous semantics instead
of inventing destructive class/year behavior.

**D — Full-roster and individual-student workflows.**
Use the existing complete-roster import preview/commit and #241's
`StudentRosterChange`, `plan_student_roster_edit` and
`commit_student_roster_edit` with both opaque tokens retained inside the
controller. Show a readable name plus stable ID and scoped before/after.
Never ask a teacher to type state tokens. Stale candidate/current data
must return to fresh preview. No modification to historical module work.
After any uncertain write result, report `INDETERMINATE` and require
canonical inspection before retry.

**E — One callable controller with Core-menu entry and consumer handoff.**
Integrate the same controller with `core` and the appropriate `pds-core`
route without changing `core`'s existing 1–5 options, Notes `:notes`
interception, or producer-owned shortcuts. Report `PARTIAL` if a later
action fails after a prior confirmed save. No Suite launcher behavior.

**F — Full qualification, capability and PR.**
Focused service/CLI/menu tests, navigation and failure injections,
Ruff format/lint, strict mypy, one full Core regression, installed
candidate wheels on Windows and Ubuntu, ordinary GitHub CI and diff
review. Advertise `classroom.menu.v1` only after qualified. Obtain
explicit owner permission to merge. No release before #244.

## Test fixture and safety rules

All automated examples use synthetic workspace data; no real teacher
rosters, class IDs, names, scores, work files, or credentials may appear
in artifacts or logs. Previewing or cancelling never creates or mutates
workspace state; no implicit file migration or syncing. Keep workspace
provider conflict copies and invalid/corrupted artifacts intact.
No cloud-distributed lock guarantee is implied by local roster locks.

## Integration dependencies and completion

The merged #241 roster services and CLI remain the single authority.
This implementation is a prerequisite for #244 qualification and
later producer/Suite adoption, but it is **not itself an official release**.
The baseline capability set continues advertising
`classroom.roster_edits.v1`; the menu capability is withheld until Slice F.

Related: [#235](https://github.com/Paper-Data-Suite/pds-core/issues/235),
[#236](https://github.com/Paper-Data-Suite/pds-core/issues/236),
[#241](https://github.com/Paper-Data-Suite/pds-core/issues/241),
[#242](https://github.com/Paper-Data-Suite/pds-core/issues/242),
[#244](https://github.com/Paper-Data-Suite/pds-core/issues/244).
