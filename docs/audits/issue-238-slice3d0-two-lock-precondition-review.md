# Core #238 — Slice 3D0: two-lock local precondition recheck

**Pinned baseline:** `af92a1eec0da2069aaaba6d68322f58bd8ce0879` (completed Slice 3C9).
**Authority:** owner-approved D0 policy and `docs/teacher_private_storage_contract_v1.md` §5.
**Status:** Internal, read-only, non-authorizing prerequisite to guarded journal admission.

## Purpose

The 3C7 currentness reviewer held only the private registry lock. Slice 3C9 added registry-first, workspace-second *local* coordination, but did not connect the two-lock set to currentness checking. Slice 3D0 combines those primitives in `review_ordered_private_binding_preconditions`. A valid proposed `REBIND_MOVE` or `FORK_COPY` is reviewed using the exact local private-root candidate and a syntactically valid workspace root. `INITIALIZE` is deliberately refused pending a separate guarded proof of absent state; it must never be inferred from a read-only missing-file observation.

The new reviewer requires an earlier qualified paired observation, then acquires **existing** registry and workspace locks (in that order), rechecks the native OS owner, reads private registry and workspace descriptor twice in opposite sequence, rechecks owner again, and compares the fresh repeated observation against the prior revision, binding count, association and exact SHA-256 digests. It delegates canonical proposal and owner/workspace comparisons to the existing Slice 3C6 precondition evaluator. It releases the two locks in reverse order, including on invalid currentness, contention, owner drift and I/O failure.

## Non-authorizing result

`RECHECKED_REVIEW_REQUIRED` means **only** that a local cooperating-process observation matched. It is not `READY`, journal admission, human review acceptance, a durable revision reservation, or authorization to write any descriptor/registry/Notes bytes. The result has no handles, OS owner, paths, UUID, journal bytes or credentials. Failures are classified with bounded sanitized states. Nothing is initialized, created, overwritten, repaired, deleted or advertised in teacher-facing capabilities.

## Known limitations / next steps

Workspace directories may be OneDrive/cloud-synced; a local sidecar lock cannot coordinate another device. The lower-level file-lock and snapshot functions do not retain native parent and target handles continuously, prove persistent volume/ACL identity, or prevent same-user hostile processes. Matching hashes cannot validate the *actual approved registry binding* or rule out pending/conflicting transaction journals. A later write-side protocol must retain native filesystem identity, enforce actual registry membership and owner scope, detect existing journals, validate teacher-reviewed operation, perform exact-before CAS checks, durably stage the protected intent, modify documents with crash-safe recovery, and requalify before activation. This slice does not enable any of those writes, Notes record CRUD, menu, CLI, portability or installed D2 security claims.

## Tests / qualification

Tests use synthetic owner and reader behavior to exercise the ordered local bracket, reverse release, changed registry and descriptor, prior staleness, changed/unavailable principal, second-lock contention, invalid initialization and request types, unqualified prior, precondition mismatch, sanitized I/O errors, unsupported OS and negative capabilities. Source-level D1 checks are not Windows installed-wheel proof or cross-device serialization. Guarded Windows runner must verify exact source HEAD, upstream refs, clean worktree and payload hashes, then run focused pytest, Ruff, strict mypy, full pytest and Git hygiene before conditional commit/push.
