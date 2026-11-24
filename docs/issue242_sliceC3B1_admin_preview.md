# Core #242 — C3B1 school-year and class creation review

**Status:** Read-only candidate on `242-workspace-classroom-management-menu`;
focused Windows qualification pending. Scope was recorded in the GitHub issue
**before implementation**. No CLI writer, new menu action, capability, merge
or release is authorized by this slice.

## Reused Core authority

- `school_years.py` owns the canonical `settings/school_year.json`
  record and `open_school_year`, `close_school_year` writers.
- `class_metadata.py` owns class metadata validation, creation and atomic
  writing. `classes.py` owns canonical class folders and rosters.
- `classroom_discovery.py` validates the selected workspace, active year,
  classes and class metadata before a proposed administrative action.

These established writers do **not** yet share a reviewed-state token,
confirmation lock, or equivalent noninteractive school-year/class CLI
contract. C3B1 **does not invoke them to write**.

## C3B1 read-only plans

`pds_core.classroom_admin_preview` provides:

```python
plan_school_year_change(root, SchoolYearChange("open", "2026-2027"))
plan_school_year_change(root, SchoolYearChange("close"))
plan_class_creation(
    root, ClassCreationChange("english10_p2", "2026-2027")
)
```

The school-year plan includes canonical workspace root, before/current
record status (`missing`, `open`, `closed`), proposed active year,
same-year no-op, exact-bounded current state fingerprint and a distinct
candidate digest. The class-creation plan describes a **new empty class**,
its stable class ID, required matching active school year, the prospective
class directory, prospective metadata and an explicit **no roster creation**
flag. Neither planner creates files, directories, markers or locks.

The current-state token binds the exact 64 KiB-bounded school-year bytes and
canonical state path. The candidate digest additionally binds the reviewed
operation/year or class/year. These are **observations**, not permission or
cross-process compare-and-swap guarantees. Any later commit must recheck
the whole relevant scope, including the class folder and metadata absence,
under a locally appropriate coordination boundary.

## Explicit refusal / history preservation

- Missing workspaces, malformed, oversized or redirected canonical
  school-year records and state changes while planning fail closed.
- Opening the same active year is a reviewed no-op. Opening a different
  year while one is active is refused without using `overwrite=True`.
- Closing requires an active year; a missing or already-closed year is
  refused.
- Existing `open_school_year` can replace a closed record when a new
  year is opened. Because that would overwrite the only existing
  closed-year record, **C3B1 refuses this transition** with
  `year_history_policy_required`. No silent archiving or migration rule
  is invented.
- New classes require an active school year matching the proposed
  class metadata year. Any preexisting class folder or redirected class
  metadata/roster path is refused, not overwritten. Roster changes and
  student management remain outside this slice.

## Acceptance vectors

`tests/test_issue242_admin_preview.py` covers synthetic-only first open,
same-year no-op, active-year close, double-close refusal, different-year
conflict, preserved closed-year history, invalid year shapes, class
creation without writes, distinct candidate tokens, missing/mismatched
active year, existing class preservation, malformed/oversized school-year
state, missing workspace, redirected state, and injected stale mid-read
detection. No real teacher preferences or classroom data are used.

C3B1 qualifies with scoped Ruff format/lint, strict mypy, targeted pytest
for the new module plus existing Core school-year/class/discovery tests,
and exact-SHA clean-tree Windows verification.

## Next gated steps

**C3B2:** decide a durable preservation/rollover policy for closed-year
history before permitting a new active year, then implement guarded
year open/close service, exact CLI parity, cancellation, stale-state and
uncertain-write testing.

**C3B3:** implement guarded new-class metadata and folder transaction
with explicit partial-create recovery and matching noninteractive CLI.

**C3B4:** integrate the qualified operations into the **test-gated**
teacher controller with one reviewed confirmation, exact
`SCHOOL_YEAR`/`CLASS` durability scope and immediate caller
revalidation. Public `classroom.menu.v1` remains unavailable until full
#242 and consolidated #244 acceptance.
