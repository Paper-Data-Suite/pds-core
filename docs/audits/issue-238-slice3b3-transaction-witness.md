# Core #238 — Slice 3B3: Pure transaction-intent and recovery-state witnesses

**Baseline:** `9e3d64d3575e1e3f23591e6cab6f694530f8bb87` (Slice 3B2).
**Design authority:** `docs/teacher_private_storage_contract_v1.md` §5 and `docs/security/teacher-private-storage-threat-model.md`.
**Status:** Internal non-mutating correctness primitive; **not** D0 owner approval, protected creation, locking, journaling, crash recovery, or a released service.

## Why this boundary precedes durable private metadata

The reviewed association design separates a nonsecret workspace sidecar from an OS-user-private registry. Those files live under different directory trees. Two `os.replace` calls cannot provide a single atomic two-document transaction. A crash can leave only one new document visible; an existing valid collection must never be relabeled as empty or silently shared.

`pds_core._teacher_private_transaction_witness` defines a **pure**, typed operation witness for `INITIALIZE`, `REBIND_MOVE` and `FORK_COPY`. It records an opaque synthetic transaction ID, old/new association UUIDs, old/new registry revisions, and expected SHA-256 byte digests for both documents. No account identity, private path, student ID, note text, credentials, or producer payload belongs in the witness. Input validation rejects noncanonical UUIDs/digests, wrong revision increments, illegal identity transitions, and inconsistent absent-registry baselines.

Given an already observed pair of exact document digests, the pure classifier returns one of:

- `NOT_APPLIED` — both observations match the reviewed before-state.
- `DESCRIPTOR_ONLY` — sidecar matches after-state; registry still matches before-state.
- `REGISTRY_ONLY` — registry matches after-state; sidecar still matches before-state.
- `BOTH_APPLIED_REVIEW_REQUIRED` — both observations match after-state, but durability, lock/currentness and native security **are not proven**.
- `CONFLICT` — any unexpected, missing or otherwise unmatched observed state.

For `REBIND_MOVE`, an unchanged descriptor is intentional; the registry revision changes. The classifier handles this without falsely treating the old descriptor as a partial commit. No state requests an automatic replay, rollback, deletion, or promotion to a qualified ready private collection.

## Ownership and test boundary

This module has no filesystem calls, no import-time effects, no native security checks, no capability token, no persistence and no public producer-facing API. It does **not** accept an untrusted caller's transaction witness as authorization. It is a reusable internal decision helper for a **future** transaction protocol, after the backend locks, protected handles, exact bytes, journal and trust policy are qualified.

`tests/test_teacher_private_transaction_witness.py` covers all operation shapes; interrupted initialize and fork; unchanged-sidecar rebind; conflicting states; immutable witness; strict digest/revision/UUID validation; sanitized errors; negative Notes capabilities; and no import-time writes. The tests use synthetic identifiers/digests and do not touch user private data.

## Work still blocked by security/design gates

Before the code can be used to carry out durable operations, separately qualify:

1. Formal owner D0 approval of the sidecar/private registry, move/fork/rebind semantics, permission and conflict protocol.
2. Native Windows, Linux and (if supported) macOS effective ACL, local backing, stable directory-handle and safe creation/verification policies.
3. Cross-process registry + descriptor coordination and a bounded lock acquisition/recovery policy; no undocumented stale-lock deletion.
4. Versioned journal **on disk**, exact before/after byte preconditions, fsync/atomic replacement guarantees, interrupted-write reconciliation, and audit of partial commits.
5. Explicit, guarded first binding (#238 Slice 4), followed by reviewed moved/copied workspace resolution (Slice 5), adversarial D1/D2 tests and installed-wheel gates. Actual Notes records and CLI remain #239/#240.

No private Notes directory, sidecar, registry, lock file or publication is created by this slice. The two advertised Core capabilities remain `terminal.header.v1` and `terminal.notes_command.v1`; version `0.6.6` in source is not a newly published distribution.
