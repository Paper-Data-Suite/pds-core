# Core #238 — Slice 3B8: Windows guarded protected-child creation

**Baseline:** `ec220fc0bfc20fb5b092a3c1a87183bd16ade079` (Slice 3B7).
**Authority:** D0 approval recorded in GitHub Core #238 and `issue-238-slice3b7-approved-d0-and-linux-provision.md`.
**Scope:** Internal explicitly invoked Windows primitive for creating *one* child under an already present, protected local Notes parent. **Not** live Notes storage, parent-tree bootstrap, metadata commits, or a storage-access credential.

## Implemented mechanism

`pds_core._teacher_private_windows_provision.create_restrictive_child_windows(existing_private_parent, child_name)` requires Windows and a bounded, safe, single-component child name. It accepts only a parent at or beneath the configured local `%LOCALAPPDATA%/Paper Data Suite/private/notes/v1` candidate; this path is **a location hint, not authorization**. It reacquires the current native process-token SID and refuses caller-supplied actor identities or unqualified owner evidence. It screens for a fixed NTFS/ReFS volume, rejects nonqualified existing parent security using Windows directory-handle/DACL/reparse preflight, and refuses an absent or unrelated parent.

A successful, explicitly requested `CreateDirectoryW` call passes `SECURITY_ATTRIBUTES` containing a new **protected** DACL (`D:P`) that grants full rights to only the process-token account SID, SYSTEM, and Administrators; it does **not** first create an insecure inherited-ACL folder and repair it afterward. Its native `LocalFree` cleanup is unconditional after descriptor allocation. Existing names are left untouched, never deleted or overwritten. Following creation, the primitive rechecks parent, new child and volume through the native refusal probes. Unknown postconditions return `CREATION_UNVERIFIED` and leave the created child in place for review. No path, SID, file handle or private note content is exposed in result messages.

The implementation reuses the restricted state vocabulary introduced by the Linux Slice 3B7 primitive, with `CREATED_RESTRICTIVE_UNQUALIFIED` **not** meaning `READY` or a live private store. The module has no import-time initialization, Notes record API or new `notes.*` capability. Linux/macOS deliberately refuse this Windows entrypoint.

## Qualification and known limits

Synthetic cross-platform tests validate names (including Windows device names), strict app-data containment, user-SID injection resistance, protected SDDL ACL construction, security-descriptor cleanup, status mapping and negative capability boundaries. On native Windows, a test creates a separate synthetic private parent chain **under pytest's temporary directory**, using explicit protected DACLs, then verifies that a `collections` child is created without overwriting it on a second attempt. Nothing is created under the teacher's actual Notes app-data root by these tests; the test temporarily points `LOCALAPPDATA` to its own temporary path. These tests must pass on the actual Windows checkout to qualify even this constrained behavior. The test skips a host volume that is not a supported fixed NTFS/ReFS volume rather than treating it as qualified.

**Important exclusions:** Windows `CreateDirectoryW` takes a *path*, not a parent-directory handle. Native parent/child DACL inspection is currently a check/recheck protocol, **not an atomic handle-relative path-swap guarantee**. A fixed NTFS/ReFS volume filter also cannot prove that a folder is free from cloud replication or all mount/backup redirection. The threat model excludes arbitrary malware operating with the same local account, but the final storage service still must qualify path integrity, locality, lock placement and race handling before actual records are persisted. No installed wheel or physical Windows ARM64 qualification is claimed by source tests.

### Remaining #238 gates

- Protected platform-owned private root bootstrap and locked initial lock-file creation; existing private parents are prerequisites, not created by this slice.
- Native handle identity continuity, stronger Windows locality/race security and Linux non-root/local installed tests; native macOS remains unqualified.
- Guarded journal and metadata file writes, cross-process descriptor+registry synchronization, fsync/CAS, and reviewed crash recovery.
- Explicit initial association/binding, move/fork decisions, adversarial and installed-artifact qualification before consumer access.
- #239 owns Note record storage; #240 the menu/CLI; #243 portability. No automatic workspace initialization, Notes creation, or publication of `notes.records.v1` under #238.

**Evidence status:** This audit documents the required runner tests, not their future outcomes. Record actual focused/full pytest, Ruff, strict mypy, Windows native test and commit on guarded execution before calling Slice 3B8 complete.
