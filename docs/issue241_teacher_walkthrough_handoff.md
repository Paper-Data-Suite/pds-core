# Core #241 — Guarded individual roster edits: teacher walkthrough and #242 handoff

**Status:** #241 source service, direct CLI, and a pre-capability installed
candidate passed maintainer Windows qualification. This document accompanies
the capability-bearing candidate, which still requires final full Core
regression, installed-wheel acceptance, CI and owner review. **No release.**

## What a teacher can do

The teacher selects an **existing class** and performs **one student edit
at a time**. A preview is always read-only. The save action requires the
exact reviewed change, both opaque tokens from that preview, and an explicit
confirmation. Core modifies only the canonical class roster, preserving
other student records and historical producer-owned work.

The following examples are **synthetic**. They demonstrate the direct CLI;
the teacher-facing interactive menu is a separate deliverable in #242.

Use a selected workspace with a known class `english12_p2`:

```text
pds-core --workspace WORKSPACE roster student-preview english12_p2 --change-file change.json --format text
pds-core --workspace WORKSPACE roster student-commit english12_p2 --change-file change.json --expected-current-state-token CURRENT --expected-candidate-state-token CANDIDATE --confirm --format json
```

Here, `CURRENT` and `CANDIDATE` must be copied *unchanged* from the
preview for that exact JSON file. In #242 the interactive controller should
carry those opaque tokens between preview and confirmation internally;
teachers must not have to type them.

### First student / add

An existing class may have no `roster.csv`; the first add is permitted
**only** if the canonical class directory and class metadata already
exist and validate. A typo must not create a new class.

```json
{
  "schema_version": "1",
  "operation": "add",
  "student_id": "0007",
  "fields": {
    "first_name": "Ari",
    "last_name": "Rivera",
    "period": "2"
  }
}
```

Preview identifies the absence of the roster and shows one new student.
Commit writes a validated one-student roster only when both reviewed tokens
are still current. Adding a student to an existing roster retains all its
columns and other rows, and never silently expands its optional fields.

### Correct one field

```json
{
  "schema_version": "1",
  "operation": "update",
  "student_id": "0007",
  "fields": {"period": "3"}
}
```

Preview shows `period: "2" -> "3"`, not the full roster. This is a
partial patch; untouched fields remain identical. If the proposed field
already matches, Core returns a **no-change** preview and a guarded
`no_change` receipt without rewriting the CSV. Student and class IDs
are immutable.

### Remove one class enrollment

```json
{
  "schema_version": "1",
  "operation": "remove",
  "student_id": "0007"
}
```

The preview identifies the selected enrollment, before/after row counts,
and the pending removal. The *last* enrolled student cannot be removed
because Core forbids an empty persisted roster. A confirmed removal never
touches historical scans, assessments, grades, attendance, submissions,
metadata for other classes, or other producer-owned records.

### Stale or unsafe conditions

If a complete roster import, another student edit, or any external writer
changes the canonical roster between preview and confirmation, commit
refuses with `current_state_changed`. If the change file differs, Core
refuses with `candidate_changed`. The teacher must inspect a **new
preview**; do not automatically replay old tokens.

Unsafe paths, malformed roster state, invalid columns, duplicate IDs, an
unknown class, the final-student rule, and contested write locks refuse
without intentional mutation. A returned `write_outcome_uncertain` is
different from a definite failure: **inspect the canonical roster before
retrying**. Neither local lock files nor roster tokens guarantee
cross-device OneDrive/Google Drive/Dropbox synchronization.

## Integration contract for Core #242

The callable Workspace & Classroom Management controller should:

1. Resolve the selected workspace/class using Core's existing APIs.
2. Offer readable class/student choices, displaying student ID to
   disambiguate identical or similar names.
3. Construct exactly one `StudentRosterChange` and call
   `plan_student_roster_edit(root, class_id, change)`.
4. Render the reviewed student-specific before/after summary (and clear
   enrollment-removal wording); require an explicit confirmation.
5. Call `commit_student_roster_edit(root, class_id, change,
   expected_current_state_token=preview.current_state_token,
   expected_candidate_state_token=preview.candidate_state_token,
   confirmed=True)`, with no separate roster writer or token invention.
6. After returning to the producer's original screen, **revalidate**
   its selected workspace, class, roster and student context. Menu return
   is not proof the caller's previous selection is still current.
7. Preserve the caller's existing navigation, pending work and error
   boundary. Do not make Core into a Suite launcher.

Relevant public service objects:
`StudentRosterChange`, `StudentRosterEditPreview`,
`StudentRosterEditCommitResult`, `StudentRosterEditError`
and its bounded subclasses. Direct CLI:
`roster student-preview` and `roster student-commit`.

`classroom.roster_edits.v1` denotes Core's implemented service/CLI only;
`classroom.menu.v1` remains absent and belongs to #242. Producers and
Suite must explicitly adopt and qualify the interface; a Core capability
token does not authorize producer operations by itself.

## Limits, backups and release

Only the selected local canonical CSV is changed, via Core's shared
per-roster lock and same-directory atomic replacement. The change is
not a bulk roster merge, an identifier correction, a transfer between
classes, a historical work deletion or an online synchronization
transaction. Existing backup/restore and provider conflict handling
remain in effect; no new server or central roster authority is introduced.

Before treating this branch as ready to merge, obtain a clean full Core
regression, normal Ruff and strict mypy gates, an installed candidate
wheel with the **new** capability token, and GitHub Windows/Ubuntu CI.
Open/review a PR and obtain maintainer approval before merging.
No official release until Core #244.

Related: [#241](https://github.com/Paper-Data-Suite/pds-core/issues/241),
[#242](https://github.com/Paper-Data-Suite/pds-core/issues/242),
[#244](https://github.com/Paper-Data-Suite/pds-core/issues/244).
