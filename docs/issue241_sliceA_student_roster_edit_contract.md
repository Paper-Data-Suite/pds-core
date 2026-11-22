# Core #241 — Slice A: per-student roster-edit contract

**Status:** Proposed implementation contract on feature branch; source and Windows acceptance pending. **Owner:** Core. **Scope:** One class, one student, one action. **Baseline:** `main` at `3ff18cc01995c06776130cf3defed9df8379a503`. **Follow-up:** Slice B implementation, Slice C CLI, Slice D qualification. This document does **not** advertise a capability or describe an installed API.

## 1. Existing authority and invariants

- `pds_core.rosters` already has immutable `StudentRecord`/`Roster`, row validation, and the pure `add_student_record`, `replace_student_record`, and `remove_student_record` transformations. Reuse these; **never use upsert** for an explicit add/update.
- `pds_core.roster_imports` already has `roster-state-v1:absent` / `roster-state-v1:sha256:<digest>` freshness tokens, canonicalized CSV hashing, and a preview/commit discipline. Factor shared private helpers only if necessary; preserve the public full-import API and tokens.
- `pds_core._roster_write_lock.acquire_roster_write_lock` and `rosters._write_roster_unlocked` jointly protect canonical `classes/<class_id>/roster.csv` writes. The new service uses **that same lock** and atomic writer.
- `pds_core.classes.load_class_roster` validates the class identity; `class_metadata.load_class_metadata_for_class` validates existing `class.json` metadata. No other roster database, journal, owner identity, or storage location is introduced.
- Empty canonical rosters are currently invalid. Removing the **final student** is refused; this contract preserves that behavior.
- An edited student retains exact `class_id` and `student_id`; all IDs remain strings, including leading zeros. Unaffected row order and all existing optional columns, their order, and values are preserved.
- No roster operation deletes or rewrites producer-owned student history. Locks do not provide cross-machine/cloud-sync exclusion; concurrent sync conflicts require separate review.

## 2. First-student/legacy-class decision

**Existing roster:** For add, update, and remove, `load_class_roster` remains authoritative even if the class predates `class.json`. A missing or invalid class metadata document must not silently invalidate an otherwise valid existing legacy roster.

**Absent roster, first add:** Require an already existing canonical class directory **and a present, valid, class-ID-matching `class.json`**. Verify the requested class metadata independently before any write. Do not treat a newly invented class directory or a bare folder as an authorized class; do not create class metadata. First add creates only the validated roster in that existing class after a guarded preview and confirmation.

**Absent roster, update/remove:** Refuse as missing enrollment/roster. **Last-student removal:** refuse `empty_roster`; do not implement an implicit delete-roster operation. A stale absence-to-presence transition fails the current-state token check.

Class metadata's school-year field remains Core-owned. A caller-selected workspace/class hint alone is not an authority grant; the CLI resolves the requested workspace using existing Core semantics, and the service must refuse unsafe canonical path redirection.

## 3. Frozen service API target (not yet implemented)

New module: `pds_core.roster_edits`. All types are immutable and validated; exact fields/behavior below are the source contract for Slices B–C.

```python
RosterEditOperation = Literal["add", "update", "remove"]
RosterEditOutcome = Literal["committed", "no_change"]

@dataclass(frozen=True, slots=True)
class StudentRosterChange:
    operation: RosterEditOperation
    student_id: str
    fields: Mapping[str, str]  # defensive immutable snapshot

@dataclass(frozen=True, slots=True)
class StudentRosterEditPreview:
    class_id: str
    operation: RosterEditOperation
    student_id: str
    current_roster_present: bool
    current_record: StudentRecord | None
    proposed_record: StudentRecord | None
    changed_fields: tuple[str, ...]
    current_state_token: str
    candidate_state_token: str
    current_count: int
    proposed_count: int
    no_change: bool

@dataclass(frozen=True, slots=True)
class StudentRosterEditCommitResult:
    class_id: str
    operation: RosterEditOperation
    student_id: str
    outcome: RosterEditOutcome
    previous_state_token: str
    committed_state_token: str
    roster_path: Path

def plan_student_roster_edit(
    workspace_root: str | Path,
    class_id: str,
    change: StudentRosterChange,
) -> StudentRosterEditPreview: ...

def commit_student_roster_edit(
    workspace_root: str | Path,
    class_id: str,
    change: StudentRosterChange,
    *,
    expected_current_state_token: str,
    expected_candidate_state_token: str,
    confirmed: bool,
) -> StudentRosterEditCommitResult: ...
```

- **Add**: `fields` contains required `first_name`, `last_name`, `period`; optional fields must be existing header names. For a first student only, extra field names may form a newly validated canonical header appended in sorted order after the required columns. No caller-supplied `class_id` or `student_id` in `fields`.
- **Update**: `fields` is a nonempty partial patch of `first_name`, `last_name`, `period`, and existing optional columns. Omitted values remain unchanged; `""` is allowed only for optional fields. A patch with the same values is a **no-change** preview; commit returns `no_change` with **no write**.
- **Remove**: `fields` must be empty and `student_id` must exist. Preview shows the selected record and resulting count, but never deletes historical artifacts.
- For all operations, missing, invalid, duplicate or unknown identifiers/columns fail closed before writing. Never coerce non-string data or implicitly widen an existing header.

## 4. Two-stage freshness and durability requirements

1. **Plan:** Validate request and class scope; inspect canonical state without creating any folder, lock, temp file, or receipt. Construct the complete proposed roster through existing validation and pure transformations. Return reviewed current/candidate state tokens and the scoped before/after record details.
2. **Commit (pre-lock):** Require `confirmed is True`; validate both tokens with existing grammar; revalidate the exact change. Reject malformed/stale candidate data.
3. **Commit (under shared lock):** Re-read current canonical state. Compare against `expected_current_state_token`, recalculate resulting candidate from that state, and compare its token to `expected_candidate_state_token`. Recheck canonical scope and all row invariants; reject any state transition or competing writer.
4. **Persist:** For a real change only, perform the existing same-directory temporary+fsync+atomic-replace write while holding the shared lock. Return `committed` only after the writer succeeds. A valid no-op returns `no_change`, leaving the bytes unchanged.
5. **Failures:** No hidden retry, partial overwrite, auto-resolution of sync copies, or claimed distributed transaction. Treat uncertain post-write outcomes distinctly from a definite refusal.

Public bounded typed errors (subclassing a common `StudentRosterEditError`), at minimum:

- `StudentRosterEditRequestError`: malformed operation, patch, tokens, or absent explicit confirmation.
- `StudentRosterEditClassNotFoundError`: unknown class / invalid metadata on first add.
- `StudentRosterEditValidationError`: duplicate or missing student, bad field, invalid roster, or final-student removal; preserve structured roster diagnostics internally.
- `StudentRosterEditConflictError`: changed current state, changed candidate, or held writer lock; include a safe reason code.
- `StudentRosterEditWriteError`: safe, bounded write/path failure, including a distinct uncertain-outcome reason when applicable.

Do not include student names, row contents, absolute school paths, unredacted exceptions, or secrets in fixed error text. Teacher-facing explicit preview may display only the selected student context.

## 5. Direct CLI contract owned by Slice C

Preserve `roster import-preview` and `roster import-commit` exactly. Add:

```text
pds-core [--workspace PATH] roster student-preview CLASS_ID --change-file FILE [--format text|json]
pds-core [--workspace PATH] roster student-commit CLASS_ID --change-file FILE --expected-current-state-token TOKEN --expected-candidate-state-token TOKEN --confirm [--format text|json]
```

`--change-file FILE` accepts bounded UTF-8 JSON; `-` reads stdin without prompting. Accept exactly a single object with `schema_version="1"`, `operation`, `student_id`, and `fields` (omitted or `{}` for remove). Reject unknown top-level keys, duplicate JSON keys, malformed UTF-8, excessive size, non-string field values and identifiers. Example **synthetic** input:

```json
{
  "schema_version": "1",
  "operation": "update",
  "student_id": "0007",
  "fields": {"period": "3"}
}
```

`--confirm` plus both exact reviewed state tokens is mandatory to commit. Text/JSON outputs use the existing CLI envelope with bounded `error.code` and `error.message`; an unchanged preview must not claim a write. Standardize deterministic, script-safe status codes before CLI implementation. Student names/IDs belong in the change-file contents rather than the shell argument list.

## 6. Evidence and rollout gates

Slice A commits only this contract and a **deferred executable acceptance fixture**. The fixture intentionally skips service-dependent cases until the new module exists; **a skipped contract test is not acceptance**. Existing baseline roster tests must still pass.

Slice B implements the service and activates deferred tests. Prove unchanged columns and rows, leading zeros, required-field refusal, duplicate/missing IDs, final-student guard, first add with metadata, stale current/candidate/absent transitions, lock conflict, no-op and write-failure preservation. Test symlinks/junctions to the degree supported on each OS, without making unsupported protection claims.

Slice C implements CLI/JSON parity with the same service, bounded diagnostics, noninteractive operation and user-visible preview. `classroom.roster_edits.v1` must be advertised only **after** service and CLI are qualified; `classroom.menu.v1` remains withheld for #242.

Slice D completes a single final full Core regression, Ruff, mypy, isolated installed-wheel acceptance and refreshed GitHub CI. Update #242 handoff docs. No merge without maintainer approval; no official release before #244.