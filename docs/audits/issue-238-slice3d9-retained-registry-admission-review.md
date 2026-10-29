# Core #238 — Slice 3D9: retained registry and journal admission review (read-only)

**Branch:** `238-establish-private-teacher-workspace-storage`
**Required baseline:** `e200b7a3c488f922075fe04b43066155a2339ee5`
**Scope:** three new files; no edits to existing modules or public API.

## Why

3D6 checked the registry and workspace descriptor while retaining the journal
folder, but the private registry file could be replaced independently. 3D7
introduced a second, nested native registry-file guard. 3D8 removed a Windows
share-mode conflict, so the existing protected registry reader can coexist
with a retained read handle without granting write/delete sharing.

## Implementation

`review_retained_registry_journal_preconditions` enters
`_hold_existing_retained_registry_guard` **once**, which itself nests the
retained journal-directory guard and both existing local locks. Under this
continuous scope it performs two pending-entry censuses, paired registry and
workspace descriptor observations, effective-owner rechecks, exact previous
revision/digest comparison and strict intent before-state review.

The function never recursively acquires either lock and never returns a file
handle, registry/descriptor bytes, identity, token or capability. Its strongest
state, `RECHECKED_RETAINED_REGISTRY_REVIEW_REQUIRED`, is advisory. Registry
file/directory identity or journal-directory drift detected on guard exit
**overrides** an apparent match and is sanitized to refusal.

## Refusal and limits

Unsupported platform; unqualified arguments or previous observation; missing
registry or pending journal; stale or corrupt metadata; owner change; unsafe
ACL/backing; and native guard failure must fail closed. `INITIALIZE` requires
a separate reviewed absence protocol. No recovery is executed.

The local locks cannot serialize cloud sync or hostile same-user writers.
Retaining these two native objects does **not** retain the workspace descriptor
or its parent chain and is not native CAS. Existing reads still reopen files
by path and could race third-party changes. A safe durable write also needs
explicit teacher confirmation, exact-before CAS under retained/native write
handles, journal fsync/atomicity evidence and crash recovery. No `READY`,
`notes.records.v1`, Notes CLI or binding-commit authority is introduced.

## Qualification

- New focused tests: ordering, matched advisory result, first/second census
  refusals, stale metadata, owner change, bad preconditions, invalid requests,
  entry failures and exit failures overriding a match.
- Existing 3D6, 3D7 and 3D8 tests remain included in the focused run.
- Mandatory Ruff, strict mypy, full Windows Core pytest, staged hygiene,
  clean-worktree and exact baseline/remote checks before auto-commit/push.
