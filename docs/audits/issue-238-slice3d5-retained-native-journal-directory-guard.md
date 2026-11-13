# Core #238 — Slice 3D5: retained native journal-directory guard

**Pinned baseline:** `b341c8b482817f4c64725a8bb4704ed9174b6a49` (completed Slice 3D4).
**Authority:** approved Core #238 D0 contract, `docs/teacher_private_storage_contract_v1.md` §5.
**Status:** Internal, non-authorizing, no-write foundation for native continuity.

## Scope and ordering

An internal `_hold_existing_retained_journal_guard()` context manager takes the exact OS-account-local private root and a syntactically valid workspace root. It holds the **existing registry lock first, then the existing workspace coordination lock**, following Slice 3C9's ordered protocol. While those locks are held it opens an existing native directory handle for the owner-local `transactions/` directory, verifies protection and path identity, and **retains that same handle while the guarded scope executes**. It checks native owner and directory identity again before a normal exit, then closes the native handle and releases the two locks in reverse acquisition order. The context yields **only `None`**; no caller receives a directory FD, HANDLE, filesystem identity, owner identity, writable scope, or commit token.

On Linux, `_open_verified_parent` walks ancestry using no-follow directory descriptors and verifies effective UID, mode `0700`, ACL absence and allowlisted local backing. `fstat` of the retained directory FD and `lstat` of the expected path must match the same device/inode, mode, owner and ctime at entry and normal exit. Replaced/moved directories fail closed at exit; the original descriptor remains open until after that comparison. On Windows, native owner-restricted directory checks, fixed-volume checks, protective DACL review, and `FileIdInfo` comparison across a retained primary handle and an independently reopened path handle occur at entry and normal exit. A mismatch, reparse, access denial or unavailable native API is refused. All successfully opened handles are closed on both normal and exceptional paths.

## Non-authorizing boundary

This is **not** a journal admission API, durable lock, distributed/OneDrive guard, nor an atomic two-tree commit. Keeping one native handle open cannot exclude same-user hostile code, OS administrators, unsynchronized remote processes, or all ancestor replacement races. Its entry/exit checks do not prove uninterrupted path continuity at every instant. A caller's exception is preserved rather than replaced by a cleanup-time classification. Successful exit of this local guard **does not authorize** journal creation, metadata CAS or binding commits. No journal body, private registry, descriptor or Notes record is read, modified or created. Existing teacher-facing capabilities remain unchanged.

## Qualification and next work

Tests exercise continuous lock/handle lifetime, strict close ordering, native Windows handle identity checks with synthetic APIs, identity drift, malformed input, unavailable native APIs, owner changes and preservation of body exceptions. A non-root Linux test exercises native FD retention and directory replacement detection. Production Windows and complete Core qualification must run on the user's checkout before this slice may be committed. A future dedicated transaction service must maintain a complete set of qualified native handles, verify owner/ACL and exact expected registry/descriptor bytes under the same locks, recheck pending intents, write an owner-private fsynced journal and implement explicit reviewed CAS, recovery and committed-state proof before enabling association mutations.
