# Core #242 — Slice B2 staged read-only menu integration

**Status:** Candidate on the issue branch, pending exact-SHA Windows qualification.
The authoritative issue description was updated before B2 implementation.
No public administration menu is qualified or advertised in this slice.

## Implemented, reviewable teacher journey

`pds_core.classroom_menu_readonly` composes B1's canonical discovery service
with Core's accepted shared teacher-menu contract. For this stage it is
invocable only behind the private `_CLASSROOM_READONLY_PREVIEW_TEST_ONLY`
switch in `pds_core.teacher_menus`. Ordinary
`run_workspace_classroom_menu(..., interactive=True)` remains
`UNAVAILABLE / NO_CHANGE`, and `interactive=False` refuses before touching
the workspace or reading input. Existing Core and Notes routes are unchanged.

Under test injection, the teacher can:

1. See a Core-standard screen header and read-only overview of available
   management areas. Unimplemented Standards actions are clearly unavailable.
2. Inspect the actual selected workspace's resolution source, existence,
   writability and current open school year, without saving any preference.
3. Browse validated classes by readable derived label **and exact class ID**,
   including known school year and roster presence. Listings are paged in
   groups of 12; `>`/`<` change the displayed page without writing.
4. Select one class and inspect the canonical roster through B1's reader.
   Students with duplicate names show unique, leading-zero-preserved IDs
   alongside their names and periods; roster lists are also paged.
5. Select one student to view their read-only enrollment summary. There is
   no edit, save, remove, import, school-year change, or Standards write.
6. Use `B` to move backward through student → roster → classes → home,
   `M` to return a caller-owned main-menu disposition, or `Q` for a
   caller-owned quit disposition. EOF or interrupt cancels without a write.

## Failure, privacy and currentness boundaries

- Each screen re-reads the canonical overview. If the resolved workspace or
  active school year changes during the visit, the controller **refuses**
  with `FAILED / NO_CHANGE` and instructs the caller to revalidate.
- A previously selected class or student that disappears refuses instead of
  silently switching the selection to another index or student.
- Corrupt/unavailable/redirected canonical data yields a bounded
  `ClassroomDiscoveryError`, displayed through the caller-injected error
  output. No raw private exception or path is printed as an error.
- Output labels have terminal control characters sanitized and limited.
  Page indexes and numeric selection lengths are bounded, so an untrusted
  pasted number cannot become an unbounded integer conversion.
- Every result preserves the opaque return token **without printing it**.
  All B2 paths return `NO_CHANGE` and empty change scopes. Even after
  `NO_CHANGE`, the producer must revalidate its own workspace, school
  year, class, roster/student, work revision and authorization.
- The staged controller performs no filesystem write, shell command, Notes
  mutation, global I/O monkeypatching, or producer/Suite import.

## Qualification

Synthetic acceptance: `tests/test_issue242_classroom_menu_readonly.py`
checks public refusal, noninteractive refusal, genuine workspace/year/class
and roster browsing, duplicate names, B/M/Q, EOF, missing workspace,
unimplemented Standards, paging, invalid choices, byte-identical roster
after the visit, corrupt-year error routing, and stale year/student changes.

Run focused tests alongside A1, B1, Core menu, Notes and #241 service
regressions; then Ruff format, Ruff lint and strict mypy on changed files.
B2 is **not** installed-wheel acceptance or Core release approval.

## Next

**C:** compose guarded workspace/year/class/Standards management using existing
Core service and direct CLI authority, with one meaningful preview/confirm
per consequential action. No new writer or ad-hoc roster mutation is allowed.
**D:** compose full-roster and individual-student guarded preview/commit.
**E:** enable the qualified callable menu and Core entry points, with producer
return/revalidation tests.
**F:** integration gates, capability advertisement, installed-wheel
acceptance and PR review. No release until #244.

Related: [#242](https://github.com/Paper-Data-Suite/pds-core/issues/242),
[#241](https://github.com/Paper-Data-Suite/pds-core/issues/241),
[#244](https://github.com/Paper-Data-Suite/pds-core/issues/244).
