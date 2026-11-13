# Core #238 — Slice 3C9: ordered, preexisting local coordination

**Pinned baseline:** `aed2fd8c7241a4b5a7b6b0e63e1773609d9e3e22` (Slice 3C8).
**Authority:** approved D0 binding policy and `docs/teacher_private_storage_contract_v1.md` §5.
**Status:** Internal, no-write, non-authorizing coordination foundation.

## Defined lock order

A future guarded binding transaction needs both its owner-private registry guard and its non-secret workspace-side coordination guard. Slice 3C8 established safe create-only provisioning of the latter. This slice adds `_hold_existing_ordered_coordination`, which takes only an exact local-user v1 private-root candidate and a syntactically valid workspace root. It acquires the **existing** `.registry.lock` first and then the **existing** `.pds/.teacher-private-association.lock`; it releases in the opposite order, including after contention, owner drift, exceptions or early exits. It never creates, deletes, resets, repairs, truncates or writes lock bytes, metadata documents, intents, collections or Notes records. Each lock must satisfy the preexisting-file primitive's local regular-file checks.

The qualified OS principal is read before and after both acquisitions. A changed/unverifiable effective owner refuses use and releases any acquired locks. Errors use bounded, path-free categories. No lock handle, principal, file contents, association identifier, transaction token or write capability is returned. Linux rejects root as an ordinary-user scope; unknown OS platforms fail closed.

## What it **does not** prove

This is a *local cooperating-process lock ordering* primitive, not a distributed lock, cross-tree atomic operation, or authorization. No process on another OneDrive/cloud device must honor these locks. `Path` syntax and the previous file-lock primitive cannot prove continuous directory ancestry/DACL protection while in use. Windows native parent/file-handle continuity, link/reparse/mount races, effective permissions, registry membership and stale CAS bytes must be independently validated by a future transaction service under the full guard. A passed owner recheck does not immunize later mutation. Same-user hostile code and privileged admins remain outside the security model.

## Tests and limits

Synthetic tests prove ordered acquisition, reverse release, release after a busy second lock, validation before owner I/O, owner-kind and owner-drift refusal, exception unwinding and negative Notes capabilities. A non-root Linux test on synthetic local temporary files confirms the actual two-lock helper leaves both bytes intact. These are source-level D1 checks only; they are not Windows installed-wheel or cross-device evidence. A future journaled metadata transaction must use the ordered lock set, verify actual native handles, exact registry member/descriptor before-state and authorization of an explicit teacher-reviewed action, write a durable owner-private intent, perform CAS-protected writes and recover interrupted commits. Do not advertise Notes records, menu, CLI, or portability from this slice.
