# Core #238 Slice 3D7 — retained native private registry file guard

**Pinned baseline:** `e690683e9c9ba6cce35748631a737d51df9e7229` (completed Slice 3D6).
**Authority:** accepted `docs/teacher_private_storage_contract_v1.md` and Core #238.
**Status:** private, read-only, non-authorizing primitive; no teacher-facing service or metadata writes.

## Security purpose

Slice 3D6 rechecks canonical transaction before-state digests, registry revision, workspace association and empty pending-journal state under the protected registry/workspace locks and the retained native transactions-directory guard. It does not retain the actual owner-private `registry.json` file handle throughout those observations. Slice 3D7 supplies a *separate* scoped registry-file continuity primitive, to be integrated with the journal/metadata review in a later slice.

`_hold_existing_retained_registry_guard(existing_private_root, existing_workspace_root)` enters the existing Slice 3D5 journal guard exactly once, inherits its registry-first/workspace-second lock order, verifies the native effective owner, then retains a native read-only registry-file handle throughout its body. Neither the registry file handle nor any path, owner, file ID, metadata bytes, approval token or write-capable object is yielded. Registry and journal guards unwind on all paths. No file is created, deleted or modified.

## Linux behavior

The helper uses the existing root-ownership, mode, ACL and local-backing checks in `posix._open_verified_parent()`. It opens `registry.json` relative to the retained directory descriptor using `O_RDONLY|O_NOFOLLOW|O_CLOEXEC`. Entry and normal exit compare the native file FD and the no-follow directory entry, and the private-root FD with its no-follow current path. Device, inode, type/mode, UID, link count, size, mtime and ctime must remain unchanged. The file must be regular, single-linked, owned by the effective non-root UID, mode 0600, without an extended access ACL, and on a known locally backed filesystem. Missing, replaced, permission-changed or otherwise unqualified entries fail closed; retained descriptors are closed even if the caller raises.

## Windows behavior

The helper uses existing conservative native Windows backing and ancestor/DACL checks. It opens `registry.json` with native `CreateFileW(OPEN_EXISTING)` and reparse-point refusal, retaining that handle throughout the scope. `GetFileInformationByHandleEx` checks `FileIdInfo`, file standard metadata, and basic last-write/change timestamps. A second handle independently reopened by path must match the original object and metadata at entry and normal exit. The original and reopened handles must satisfy conservative native DACL checks; ancestry, reparse status and fixed-local-volume qualification are rechecked. An unavailable native identity or change detector refuses, rather than falling back to `os.access()` or path-name equivalence.

## Explicit non-guarantees and requirements before writing

- Holding an open file handle is *not* an exclusive lock against hostile same-user writers. Metadata can still change and revert between sampling points. File ID, modification/change time and hash comparisons are observational, not durable compare-and-swap.
- A Windows handle can retain the file object while a pathname changes. The separate no-follow path reopen is therefore necessary, but is still not equivalent to full parent-relative transaction creation.
- The workspace descriptor remains on a possibly synchronized filesystem. Neither current local lock nor file-handle continuity provides OneDrive distributed serialization or authorization for a copied workspace.
- This helper neither reads/validates registry contents nor checks the complete before/after transaction on its own. A subsequent review must keep this scope alive through *all* journal and metadata checks, preserve pending-intent recovery evidence, and independently qualify the workspace descriptor and native parent handles.
- Do not call `create_private_transaction_intent_file()` or modify the registry/sidecar on the strength of this guard alone. A future guarded writer still requires explicit teacher approval, exact-before native CAS, durable owner-private intent and crash recovery, and safe file replacement semantics.
- No new `notes.records.v1`, `notes.menu.v1` or `notes.cli.v1`; Core capabilities remain exactly `terminal.header.v1`, `terminal.notes_command.v1`.

## Verification

Isolated non-root Linux test harness: 16 passed (real local file and directory replacement, file metadata drift, synthetic Windows lifetime/refusal, no new capability). The guarded Windows runner must verify repository, baseline blobs, both remote heads, exact additive scope, SHA-256 archives, Ruff formatting/lint, strict mypy, focused and full pytest, Git hygiene. Commit/push only after all gates pass. No installed-wheel or multi-machine OneDrive admission test is asserted here.
