# Core #238 — Slice 3C8: create-only workspace coordination file

**Pinned baseline:** `69197d0b40bf2617a766cde2066cae3011311d2c` (completed Slice 3C7).
**Authority:** approved D0 architecture in #238; `docs/teacher_private_storage_contract_v1.md` §5.
**Boundary:** a nonsecret, explicit, create-only *local-process* coordination artifact, not binding, registry, Notes, or cross-device synchronization.

## Gap and primitive

Slice 3C7 can recheck currentness while holding the existing owner-private `.registry.lock`, but a future metadata writer additionally needs a workspace-side coordination guard. Slice 3C8 introduces internal `create_workspace_coordination_file(workspace_root: Path)` and the fixed name `<workspace>/.pds/.teacher-private-association.lock`. The payload is exactly one NUL byte, suitable for the previously implemented `hold_existing_private_lock`. The helper never calls Core workspace initialization and **requires the `.pds` directory to preexist**. It does not create or change `teacher-private-association.json`, the generic `.pds/workspace.json`, the private registry, a journal, a private collection, or any Notes record. Its successful status is `CREATED_UNQUALIFIED`, not `READY` or a transaction permit.

A preexisting target of **any kind**, including a symlink, causes an `ALREADY_EXISTS` status without opening, truncating, following, removing, repairing or verifying that entry. Consumers must separately qualify an existing candidate before using the ordinary file-lock primitive. Post-create verification failure leaves possible partial bytes in place, returning `CREATION_UNVERIFIED` for human review, not automatic deletion or overwrite. Return messages never include the workspace path or native user identity.

## Linux

The native implementation rejects invalid/relative/traversal roots, root-account use, absent `.pds`, symlink traversal and suspicious writable/foreign-owned ancestors. It walks from `/` using held, no-follow directory descriptors, requires final `.pds` to be owned by effective UID and have no group/world permission or extended access ACL, and applies the existing restrictive filesystem locality allowlist. It creates only the fixed file with `openat(O_CREAT | O_EXCL | O_NOFOLLOW, 0600)` and a one-byte write. It checks file UID, mode `0600`, one hard link, exact byte count, FD-to-name identity, matching parent device, ACL absence and local backing, then fsyncs file and parent. This is native *source-level* evidence; allowlisted filesystem and verified ACL remain requirements on the actual install.

## Windows

The implementation requires an absolute Windows workspace path and non-reparse ancestry through the existing `.pds` directory. It verifies current **process-token** SID, fixed NTFS/ReFS backing and an owner/SYSTEM/Administrators-only DACL on `.pds` using an open handle with **READ_CONTROL**. It reuses the earlier native `CreateFileW(CREATE_NEW)` helper, which applies `D:P` restrictive SDDL at creation rather than after an inherited-permission window. A successful one-byte `WriteFile`/`FlushFileBuffers` must be followed by native handle attribute, link-count, length, owner/DACL, unchanged parent and backing checks. If native security information is unavailable, the operation fails closed. Parent-handle continuity across `CreateFileW` and all filesystem alias races is not proven by this primitive and remains a future transaction gate. Native Windows validation must occur on the user's actual checkout.

**Conservative behavior:** Common default `.pds` permissions may fail this check. The helper does not silently change existing ACLs. A deliberate private-metadata directory protection policy and user remediation remain part of the binding transaction review, not an excuse to relax security in this slice.

## Coordination policy and exclusions

The future transaction coordinator must acquire **registry lock first, workspace lock second**, consistently across every writer, then recheck identity, registry, descriptor, revision, paths and active handles before applying a journaled CAS commit. A single-file lock does not persist authorization past release and does not guarantee cross-tree atomicity. An OS-local lock is **not** a distributed lock: cloud sync/OneDrive, an offline replica, another PC, or an adversarial same-account process may change the sidecar without observing this file's lock. The service must decline unsupported cross-device coordination or require explicit recovery; it must not assert that a synced lock file serializes remote devices. No records are created, and no `notes.records.v1`, `notes.menu.v1`, `notes.cli.v1` or portability capability is advertised.

## Qualification and next step

New regressions cover valid/invalid roots, no creation of `.pds`, Linux protected exclusive creation and native lock compatibility, symlinks, permissive modes, unqualified backing, restrictive umask/partial state, no Notes capability, and a native Windows file/DACL/lock case. Synthetic locality checks are **D1 only**, not proof of deployed volume security. The guarded runner pins the exact branch, `origin`, `main`, SHA-1 baseline blobs and clean worktree; verifies ZIP SHA-256/manifest scope; applies only three new files, formats Python without AST change, runs focused tests + Ruff + strict mypy + full pytest; only then commits/pushes after remote recheck. Windows CI, installed-wheel D2 and full transaction authorization remain outstanding.

**Next:** require a paired ordered lock/read-and-write transaction protocol with durable journal, exact-before checks and interruption recovery before any binding commit. Do not shortcut to another advisory check or enable Notes writes.
