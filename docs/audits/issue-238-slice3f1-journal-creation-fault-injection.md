# Core #238 — Slice 3F1: Journal creation crash/fault matrix

## Scope and baseline

Source branch: `238-establish-private-teacher-workspace-storage`, commit
`491b6704598643cf401141dec349561715dc2482`.

Add **only** `tests/test_teacher_private_journal_fault_injection.py` and this
security audit. Production code, module APIs, the Notes capability set, and
existing journal/registry/descriptor contents remain unchanged. All tested
payloads, Windows SIDs and paths are synthetic.

## Security invariant

The private journal create primitive is intentionally create-only. If any
operation fails **after exclusive creation**, the resulting candidate can be
complete, incomplete or otherwise uncertain. The creation attempt must not
silently unlink, truncate, retry against, overwrite or treat that candidate as
a completed binding. A later guarded operation must inspect pending journal
entries before accepting any new transaction. The only successful state is
`CREATED_RESTRICTIVE_UNQUALIFIED`: it does **not** mean durable transaction
admission, a completed metadata CAS, recovery authorization, or Notes access.

## Failure-point coverage

| Platform | Injection/observation | Required outcome |
|---|---|---|
| Windows simulation | Native `WriteFile` fails or reports a short write | `CREATION_UNVERIFIED`, no flush attempted, opened handle closed |
| Windows simulation | `FlushFileBuffers` fails or raises | `CREATION_UNVERIFIED`, candidate preserved for review |
| Windows simulation | Native file attribute query fails or shows a reparse tag | `CREATION_UNVERIFIED`, no journal promotion |
| Windows simulation | DACL verification refuses the newly created file | `CREATION_UNVERIFIED`, no journal promotion |
| Windows simulation | Exclusive create collides with an existing name (80/183) | `ALREADY_EXISTS`, no write/flush/foreign handle close |
| Windows simulation | Local volume or native directory protection fails before create | Refusal, no creation attempt |
| Linux native (non-root) | File `fsync` fails | `CREATION_UNVERIFIED`; exact candidate retained |
| Linux native (non-root) | Parent directory `fsync` fails | `CREATION_UNVERIFIED`; exact candidate retained |
| Linux native (non-root) | Short `write` followed by error | `CREATION_UNVERIFIED`; partial bytes retained, never auto-repaired |
| Linux native (non-root) | Existing name is a hard link | `ALREADY_EXISTS`; existing inode and contents unchanged |

Linux tests use only an isolated temporary XDG-local directory; they do not
modify a live private root. The Windows native calls are mocked in memory;
these tests validate refusal mapping, call order, handle closure and
write-through dispatch but are **not** a substitute for native Windows
filesystem crash/power-loss tests. The separate native Windows test from
Slice 3C0 and write-through tests from Slice 3F0 remain in the full suite.

## Distinctions and known gaps

- An injected exception is a simulated fault, not a physical power-loss test.
- Returning from `fsync`/`FlushFileBuffers` does not prove that every storage
  stack honors physical persistence under every controller or filesystem.
- The Windows journal file requests write-through and is flushed, but no
  cross-file durable commit point or journal namespace continuity has been
  established. The private root is subject to the existing strict local-volume
  and protection rules.
- A file that survives a failed create attempt must be treated as pending and
  reviewed; deleting it on an assumed failure risks losing the only recovery
  evidence.
- This test slice introduces **no live metadata writes**, no journal retirement,
  no automatic recovery and no public Notes or storage capability.

## Qualification gates

The guarded runner pins the exact baseline Git blobs, source ZIP SHA-256,
branch/remote heads, and clean worktree. It applies exactly the two additive
files and runs focused tests, Ruff lint and formatting, strict mypy, full Core
pytest, and Git hygiene. It commits/pushes only if all gates pass. Failure
leaves the worktree for narrowly scoped repair, without resets or cleanup.

## Next milestone

Design and qualify the **native metadata write-target continuity and exact
before-image CAS** within the existing retained journal, registry and
workspace-descriptor guards. This must distinguish the owner-private registry
from the untrusted, potentially synced workspace sidecar; it must not promote
journal candidate creation into authorization to update either document.
