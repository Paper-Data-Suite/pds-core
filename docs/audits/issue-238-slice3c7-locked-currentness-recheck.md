# Core #238 — Slice 3C7: Lock-scoped binding-currentness recheck

**Pinned baseline:** `5f019772b2f76d980280ea97ae5405641210b6a6` (Slice 3C6)
**Authority:** User-approved D0 private storage boundaries; `docs/teacher_private_storage_contract_v1.md`.
**Status:** Internal, read-only, deliberately **non-authorizing** building block.

## Purpose and exact scope

Slice 3C6 validated the proposed before-state against a *previous* paired observation. Slice 3C7 supplies a new read-only comparison under an acquired existing registry coordination lock, with a newly observed native OS owner. It never creates a lock, descriptor, registry, journal, directory, record or Notes capability. There is no human-review acceptance or commit-path dispatch.

`review_current_private_binding_preconditions(proposed, prior, existing_private_root, existing_workspace_root)` requires the exact native local private Notes v1 root, an absolute acceptable workspace root, a valid internal v1 transaction-intent object, and an already qualified paired observation. Initialization is **never** accepted through this helper: its absent-before-state requires a separate guarded absence check and an explicit reviewed write protocol.

After acquiring the **existing** `.registry.lock` via the nonblocking cross-process primitive, the helper reads the effective OS owner, the native-checked private registry, the potentially synced workspace descriptor twice, the registry again, then the OS owner again. The established Slice 3C5 classifier rejects changing, missing, unsafe or ambiguous metadata. The helper compares the *current* observation to the *prior* observation's exact revisions, binding count, association ID, and SHA-256 digests, then invokes the pure Slice 3C6 before-state comparison using the freshly observed owner while the lock remains held.

The strongest status is `RECHECKED_REVIEW_REQUIRED`, with **no** owner/path/hash/secret details and no authorization flag, storage handle, commit reservation, or write token. Other states include stale/unsafe observations, principal drift, unavailable OS identity or lock, and specific sanitized precondition refusal. Intent and private records are never emitted in diagnostics.

## Limits and future write gate

The lock protects coordination only among processes honoring it. It is *not* a persistent exclusive lock on the synced workspace descriptor, does not hold parent directory handles continuously, does not establish all native filesystem continuity requirements, and cannot prevent a concurrent OneDrive/sync process or same-OS-account process from changing workspace bytes after inspection. This check does **not** prove a descriptor UUID appears in the protected registry as an approved binding. A matching digest/revision is not a durable CAS token and is not sufficient to authorize storage.

No automatic initialization, migration, fork, move, restore, reconciliation, cross-tree rename or journal state transition is permitted. Future live writes must acquire and preserve the full ordered native transaction lock set, verify actual registry membership and path identity from protected open handles, enforce exact-before revisions/bytes, stage a durable journal first, apply protected atomic replacements, requalify state before activation, and reconcile interruptions. D2 platform qualification and installed security tests remain separate gates; sandbox Linux tests with synthetic filesystem allowlists do not assert installed storage qualification.

## Tests and qualification

`tests/test_teacher_private_currentness_review.py` covers synthetic Windows/Linux-agnostic lock ordering, native owner rechecks, changed registry/descriptor during the pair, earlier stale snapshots, path and principal mismatches, missing descriptor, initialization refusal before touching the lock, contention, owner-query failure, read error hygiene, unsupported platforms, sanitized result values and no Notes activation. One Linux nonroot synthetic-local-filesystem test exercises the actual file read-only path end-to-end, preserving lock, registry and descriptor bytes. Native Windows platform behavior relies on the user's actual Windows qualification suite and the pre-existing dedicated readers' tests.

A runner will check exact branch, remote, baseline hashes and worktree, apply three new files, Ruff-format Python without AST changes, run focused tests, lint, strict mypy, full pytest and Git hygiene. Commit/push is conditional on all gates. Failed qualification must preserve changes for a guarded repair rather than reset or delete user work.
