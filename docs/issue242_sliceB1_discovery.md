# Core #242 — Slice B1 authoritative read-only discovery

**Status:** Feature-branch implementation candidate; exact-SHA focused Windows
qualification remains pending. No interactive production menu is exposed,
no existing Core menu choices are changed, and `classroom.menu.v1` remains
unadvertised. Issue #242's updated description is the governing specification.

## Deliverable

`pds_core.classroom_discovery` composes, without writing:

- `inspect_workspace_root` to distinguish **missing workspace**, an existing
  empty workspace and an invalid workspace root. The existing resolution source
  (`explicit`, environment, saved config or default) is retained.
- `load_school_year_state` to report the **active** year, or `None` when
  absent/closed. Invalid year state is not silently treated as no active year.
- Existing canonical class routes and `load_class_metadata_for_class`, so
  legacy classes without metadata remain visible but invalid metadata raises
  a stable bounded refusal. Class IDs are unchanged; display labels derive
  from the ID and are **not** a separate class-name authority.
- `load_class_roster` and `student_display_name` for a **single selected
  class**, showing each student by a safe display name plus its exact
  leading-zero-preserving student ID. Duplicate names remain distinguishable.

Public read-only functions:

```python
inspect_classroom_overview(root: str | Path | None = None) -> ClassroomOverview
inspect_classroom_roster(root: str | Path | None, class_id: str) -> ClassroomRosterView
```

The returned frozen summary objects carry observations only. They are **not**
authorization, current-state tokens, or a substitute for `#241` roster
preview/commit. Loading an overview does **not** read or export every roster;
a selected roster is loaded separately and fully validated.

## Fail-closed read boundaries

The reader refuses redirected class/year/roster paths (symlinks and Windows
junctions), invalid class identifiers, malformed school-year and metadata
records, invalid selected rosters, and oversized class/roster listings.
Stable `ClassroomDiscoveryError.reason` values provide a teacher-safe
message without raw paths, file contents or private exception strings.

An **absent roster** is a valid not-yet-enrolled class condition; an
invalid or unreadable roster is not. Only valid canonical roster rows are
presented. This read-only service never creates a workspace, class, lock,
roster, preference or any producer-owned artifact. Local filesystem
observations do not guarantee cross-device sync consistency.

## Acceptance

Synthetic tests in `tests/test_issue242_classroom_discovery.py` cover
workspace missing versus empty, active year, class metadata, legacy
metadata absence, two students with identical names but distinct IDs,
no-roster display, corrupted state, unsafe path redirection, invalid
class selection, and roster display-size refusal. Existing #242 A1
navigation and Notes/Core menu tests must stay green.

**Next B2:** Connect these authoritative read-only views to the staged
classroom menu controller with injected I/O and B/M/Q navigation, while
keeping the public menu fail-closed until full C–F qualification.
Do not add any write action or advertise `classroom.menu.v1` in B2.

**Next release:** #244 only, after Core #242's final PR/CI review.
