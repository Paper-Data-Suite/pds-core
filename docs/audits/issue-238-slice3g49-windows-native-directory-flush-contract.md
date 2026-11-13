# Core #238 — Slice 3G49: Windows native directory-flush contract census

**Branch baseline:** `a76cc6cccb133deb02c256fe549fbcd8c1564c93`
**Base `main`:** `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`
**Scope:** One private, scratch-only capability probe, one regression-test file, this audit.
**Previous qualification:** 3G48 Windows focused suite: 3,964 passed, 163 skipped; Ruff and strict mypy green. 3G40 full suite checkpoint: 6,864 passed, 179 skipped.

## Why this probe exists

3G48's disposable journal/registry/descriptor sequence verifies ordering of file flush and parent-directory flush **requests**. Windows user-mode API documentation separately specifies opening directory handles via `FILE_FLAG_BACKUP_SEMANTICS` and flushing *file* buffers via a handle opened with `GENERIC_WRITE`. The supported directory-handle operation list does not include `FlushFileBuffers`. Neither a successful file-buffer flush nor an apparently successful rename proves that a **two-document transaction** and its journal state will survive power loss. `MOVEFILE_WRITE_THROUGH` documentation's specified flushing scope is not an independent multi-file transaction or parent-directory crash-durability guarantee.

3G49 therefore probes, **only in newly generated scratch** on the current Windows host/temporary volume, the native directory-handle open and flush contract for three parent roles:

1. `journal`: synthetic pending-intent parent;
2. `registry`: synthetic registry-stage parent;
3. `descriptor`: synthetic workspace-association parent.

All three synthetic files first receive a native file flush request; parent probes are not run if file content and identity are not stable. Each directory is opened `OPEN_EXISTING` with `FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT`, requested `GENERIC_WRITE | FILE_READ_ATTRIBUTES` and `FILE_SHARE_READ | WRITE | DELETE`. The native parent identity is checked through `GetFileInformationByHandle` before and after one `FlushFileBuffers` request, and independently re-opened. Handles are closed on all paths. No `os.replace`, production files, caller paths, stage replay, volume-wide privileged flush, ACL remediation or Notes work is performed.

## Result vocabulary and exact limits

- `REQUESTS_RETURNED_UNQUALIFIED`: all three native scratch parent flush requests returned. **Still not proof of durable directory entries or a multi-file commit.**
- `OPEN_REFUSED`: at least one directory could not be opened with the specified access and flags. Denial and unsupported access are distinct per-parent observations.
- `FLUSH_REFUSED`: a directory handle was opened but the flush was refused. Known unsupported codes (1, 6, 50, 87), access/sharing denial (5, 32, 33), and other refusals are distinct per-parent observations.
- `IDENTITY_CHANGED`: native parent identity or synthetic file evidence was unqualified. No inference of persistence.
- `FILE_FLUSH_REFUSED`, `NATIVE_UNAVAILABLE`, `INTERRUPTED_PRESERVE`, `IO_ERROR_PRESERVE`, `UNSUPPORTED_PLATFORM`: all fail closed.

All results have `production_writes_blocked`, `journal_retirement_forbidden`, `pending_evidence_must_remain`, and `directory_durability_unqualified` set to `True`. Results and exception messages contain **no raw paths, SIDs, handles, native file IDs, student/teacher content or filesystem contents**; observed names are fixed synthetic roles. Probe output must never serve as a cached production-write certificate, since a different production volume, process identity or filesystem can behave differently.

## Remaining gates before live mutation

1. A real operation-owned journal/registry/descriptor state machine with native ownership, ACL and binding checks, current canonical images, locked CAS, and a defined crash-recovery policy.
2. A **documented, supported** platform-specific durability strategy for Windows directory-entry replacement. A returned `FlushFileBuffers` on a file, or a temporary directory probe on a different volume, does not suffice. When this cannot be qualified, production writes must refuse rather than silently degrade.
3. Tested partial-state recovery after registry-only and descriptor-only changes; no blind retry, no unreviewed journal retirement; first-binding separate absence protocol.
4. Linux and native Windows installed-wheel qualification, native macOS gate tracked honestly, complete Core CI and a reviewed #239 handoff.

## Documentation consulted

- Microsoft Learn: [Directory Handles](https://learn.microsoft.com/en-us/windows/win32/fileio/obtaining-a-handle-to-a-directory)
- Microsoft Learn: [FlushFileBuffers](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers)
- Microsoft Learn: [MoveFileEx](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexa)

**Conclusion:** 3G49 is a disposable environment diagnostic and negative durability boundary, not an installation, production writer, private Notes service, durable commit, or authorization to retire a journal.
