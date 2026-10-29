# Core #238 Slice 3E0 — Retained workspace descriptor identity

## Scope and baseline

- Branch: `238-establish-private-teacher-workspace-storage`.
- Exact predecessor: `771c2b7ad097edee8ad20a10781b58fc891b538c` (Slice 3D9).
- Additive files: private module `_teacher_private_retained_descriptor_guard.py`, its test module, this audit.
- No existing Core code, capabilities, public API, file contents, or Notes records are changed.

## Trust boundary

The workspace `.pds/teacher-private-association.json` may be synchronized and copied. A UUID, file ID, OS owner, successful native observation, or local advisory lock on that workspace does **not** authenticate the teacher, prove current binding, serialize remote machines, or authorize a metadata write. The owner-private registry is still authoritative. No `READY` state, commit/write token, binding mutation, new journal admission, or Notes capability is introduced.

### Guard composition

`_hold_existing_retained_descriptor_guard(private_root, workspace_root)` enters the **existing** registry/journal guard (`_hold_existing_retained_registry_guard`) once. That outer context owns both local locks, the native transactions directory handle, and the native private registry-file handle. The new inner context opens the workspace sidecar and its `.pds` parent **for reading only**, retains both native handles across the caller's body, verifies their identity and metadata at normal exit, and closes them on all exit paths. The context yields only `None`; the file handles and observed private identifiers never escape. A failure on guard exit propagates and overrides any successful advisory work performed inside the scope. Underlying retained-registry failures are mapped to bounded, sanitized refusal categories.

### Linux

From `/`, use `O_DIRECTORY | O_NOFOLLOW` for each existing ancestor through `.pds`. Open the descriptor with `O_NOFOLLOW`, retain both descriptors, and check `fstat` versus `lstat`/`stat(..., follow_symlinks=False)` identities and metadata (device, inode, mode, UID, link count, size, mtime and ctime). Reject symlinks, missing entries, replacements, changes and non-regular files. Require a single descriptor hard link and bounded nonempty file size. The workspace sidecar is **not** required to be owner-private; that is appropriate only for owner-local private files.

### Windows

Use the existing descriptor snapshot's Windows API binding and no-follow open logic. Retain two `CreateFileW` read-only handles with the existing share semantics. Compare `FileIdInfo` volume serial and 128-bit IDs, basic write/change times, size, link count, directory and reparse attributes; require bounded descriptor length, and independently reopen each current path at entry and exit. Rewalk the workspace ancestry to refuse known reparse points. Descriptor information is untrusted, and these checks make no DACL-owner claim about the synced workspace.

### Known limits

Handle retention alone does not prevent same-principal writes, protect a cloud replica, or provide an atomic cross-filesystem snapshot. Ancestor checks not retained for the full transaction, ABA-style replacement between observations, malicious same-size/metadata-restoring changes, and cloud synchronization can defeat these observations. The next slice must compose retained identity and metadata digest reviews, and must not treat such a composite result as CAS or journal admission. Future binding commits still need explicit teacher confirmation, exact-before atomicity, journal admission and crash recovery.

### Failure policy

Unsupported platform, unsafe paths, native identity mismatch, missing sidecar, ACL/permission error, OS-owner drift and underlying guard refusal all abort without creating, truncating, overwriting, removing or repairing any file. Successful body completion is never reported when native exit checks reject continuity. Caller-raised exceptions pass through intact while native handles are closed.

## Qualification

- Standalone isolated dependency-stub harness on non-root Linux: **18 passed** (native positive, replacement/mutation, synthetic Windows, parent, nesting and exit failures).
- The guarded Windows runner must independently pass focused pytest, Ruff, strict mypy, full pytest, exact Git scope, and remote-head checks before committing or pushing.
- Published Core 0.6.6 and the public `get_teacher_experience_capabilities()` tokens remain unchanged.
