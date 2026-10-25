# Core #238 — Slice 3B1: Native no-write private-root preflight

**Source baseline:** `f196360fe49b9e70b8a6897d5261c011ddeb0916` (Slice 3A).
**Status:** Additive source-only, fail-closed *observation*; no qualified private-store activation or new Notes capability.
**Authority:** [`../teacher_private_storage_contract_v1.md`](../teacher_private_storage_contract_v1.md), [`../security/teacher-private-storage-threat-model.md`](../security/teacher-private-storage-threat-model.md), umbrella #235 / issue #238.

## Purpose

A strict metadata codec alone does not establish safe filesystem access. The new private `pds_core._teacher_private_native_preflight` adds one narrower native Linux refusal layer above Slice 2's read-only probe. It opens an absolute directory chain using `O_DIRECTORY|O_NOFOLLOW` and **directory-descriptor-relative** `os.open`, inspects each opened directory through `fstat`, rejects untrusted writable ancestors (except a root-owned sticky directory), and requires the application-private `/private/notes/v1` suffix to be owned by the effective UID with mode exactly `0700`. Each of the three protected directories must have **no POSIX access ACL xattr**, as verified on Linux; an extended ACL, unknown ACL support or verification error refuses. The directory FDs are always closed and **never returned to a writer**.

The result is a sanitized `NativePrivatePreflight` containing only a state and fixed message. It does **not** return a candidate path, verified principal, opened file descriptor, registry, association or access capability. The most favorable state is **`RESTRICTIVE_UNQUALIFIED`**, not `READY`. It means only that certain restrictive attributes were observed at one instant. It does **not** establish local-filesystem/mount assurance, resistance to a subsequent swap, interprocess serialization or native write protection.

### Cross-platform boundary

- **Linux:** actual read-only directory-descriptor walk and POSIX access-ACL xattr observation. No file is created; no positive authorization follows from these observations. Unrecognized filesystem, ACL, traversal and access failures refuse.
- **Windows:** Slice 2's process-token SID discovery and reparse inspection remain; Windows native security-descriptor DACL evaluation, owner/write validation, volume locality and protected creation are **not qualified** by this slice. Existing paths remain `UNSUPPORTED` rather than be called secure on the basis of Python modes.
- **macOS:** candidate-root inspection remains; native macOS ACL and local backing checks are **not qualified** by Linux-only tests and remain `UNSUPPORTED`.

Windows ARM64 and real macOS require their own native evidence. Linux tests do not substitute for either. Native Linux test cases use **synthetic temporary directories** and exercise missing roots without side effects, restrictive observation, unsafe mode/owner, nonsticky writable ancestors, links, ACL present, ACL unavailable and error sanitization. All writer behavior is intentionally absent.

## What remains for Slice 3B2 and later

1. Owner-reviewed D0 decision confirming the sidecar, registry and migration/conflict protocol, including district cloud-synced workspaces. No D0 owner approval is inferred from a passing test.
2. Windows process-token SID and **effective native DACL / inherited ACE** proof, Windows reparse and local backing safeguards; corresponding Linux/macOS local backing and effective ACL qualifications. A user-configured local-data path must not override OS ownership.
3. Protected opt-in directory/file creation with native ACLs or `0700`/`0600` from the initial creation operation, handle lifetime and race safeguards; **no automatic creation on inspection or import**.
4. Qualified cross-process locks, expected-version CAS, exclusive/atomic metadata writes, per-operation intent journal, crash recovery, and non-destructive failure handling.
5. Later explicit workspace `INITIALIZE`, `REBIND_MOVE` and `FORK_COPY` reviewed binding flows; Notes records (#239), menu/CLI (#240), portability (#243) and installed/core-platform qualification (#244).

The existing `.pds/workspace.json`, workspace configuration, Core CLI, #237 parser/header and the exact two teacher-experience capability tokens remain unchanged. No producer/Suite adoption, published package release, or private Notes content has been qualified. The current source package version is still `0.6.6`, distinct from its previously published artifact.

## Test and review gates

- `tests/test_teacher_private_native_preflight.py` — Linux native probe and synthetic cross-platform refusal tests.
- Existing `tests/test_teacher_private_inspection.py`, `tests/test_teacher_private_metadata.py`, `tests/test_teacher_private_storage_slice1.py`, Core workspace and teacher-experience tests — compatibility regressions.
- Full pytest, Ruff lint/format, strict mypy and Git whitespace/scope checks on the exact branch.

Any test failure **stops before commit/push**. A later installed native gate must independently reproduce the security behavior; no D2 claim is made here.
