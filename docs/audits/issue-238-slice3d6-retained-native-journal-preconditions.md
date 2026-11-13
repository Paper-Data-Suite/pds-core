# Core #238 — Slice 3D6: retained native journal and metadata preconditions

**Pinned baseline:** `b0ffa09c8da64883e34f2d4a106171a9c4d31b30` (completed 3D5).
**Authority:** D0 owner decision and `docs/teacher_private_storage_contract_v1.md` §5.
**Status:** Internal read-only advisory implementation; no journal admission or writes.

## Consolidated retained review

`review_retained_private_journal_preconditions()` validates the exact internal request and refuses initialization without separate, guarded proof of absent metadata. For noninitialization proposals it enters the existing 3D5 `_hold_existing_retained_journal_guard()` exactly once. This guard acquires preexisting private registry then workspace locks, retains a native handle to the owner-private `transactions/` directory, and checks the native directory's identity and protection again on normal scope exit. The reviewer acquires no nested locks and returns no handles.

Inside the uninterrupted guarded scope, Core samples the effective OS owner, performs a pending-journal census, reads the registry and descriptor twice each using internal no-nested-lock readers, repeats the census, samples the owner again, classifies paired metadata, matches the previous observation, then compares the proposed exact-before metadata/owner/workspace preconditions. Existing journals, changed directory observations, inconsistent metadata, stale earlier evidence, owner drift, and failed preconditions produce bounded refusal categories. A native identity/protection failure **on exit** overrides a potentially matching observation: the result cannot advertise the advisory success state after the retained guard detects a change. No transaction file content is read and no candidate journal is created.

## Explicit security limitations

`RECHECKED_RETAINED_REVIEW_REQUIRED` is an advisory classification only. It is **not** an approval, admission token, write handle, durable CAS reservation, cross-device lock, or proof of a safe two-tree transaction. Registry and descriptor readers still use separately opened paths rather than a complete retained chain of parent/file write handles; the workspace may be synced; other devices do not honor the two local lock files. Directory enumeration is not atomic against hostile same-user modification. Even a stable owner-private journal FD does not prove a future destination is safe for a write. None of this code exports the proposed public `teacher_private_storage` service or enables `notes.records.v1`, menu, CLI, Notes data, or existing-binding mutation.

## Qualification evidence and next gate

Additive scope: `_teacher_private_retained_admission_review.py`, its regressions, and this audit. Test coverage exercises two censuses and both metadata reads within one retained guard, early refusal for pending or unsafe journal state, stale/changed metadata, precondition mismatch, OS-owner drift, invalid/initialization inputs, native entry failures and native exit failure overriding an apparent successful review. This source-level qualification is not D2 installed-wheel/native deployment evidence. Before a writer exists, add retained native verification of the exact target parent/file chain and owner, exact-before byte/revision CAS under all appropriate guards, approved teacher intent, durable journal creation/fsync, crash recovery, and explicit denial of unsafe cloud or cross-device coordination. The first writer must be separately designed and accepted rather than treating this reviewer as authorization.
