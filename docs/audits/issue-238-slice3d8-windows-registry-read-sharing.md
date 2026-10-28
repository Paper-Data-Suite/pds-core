# Core #238 — Slice 3D8: Windows read-sharing compatibility for retained registry identity

## Context and exact scope

Baseline: `48c393889b2807c7dbdcee3f925c31057ca0212f` on `238-establish-private-teacher-workspace-storage`. The protected registry snapshot reader in `_teacher_private_registry_snapshot._windows_read()` previously invoked `CreateFileW()` with `dwShareMode=0`. Slice 3D7's read-only retained registry guard keeps a separate read/attribute handle open, so the exclusive snapshot open could fail with `ERROR_SHARING_VIOLATION` even for one cooperating process holding the ordered locks. Slice 3D8 changes only the registry snapshot's **share-mode argument**, from `0` to `FILE_SHARE_READ (0x1)`, and adds dedicated regressions. It preserves the access mask, `OPEN_EXISTING`, no-reparse-point flags, volume-locality checks, protected DACL/owner checks, existing registry lock, strict bounded bytes and schema validation, file metadata checks, and sanitized outcomes.

## Security properties and limitations

- The snapshot handle allows other *readers* but does not share write or delete access while that handle is open. This is not a distributed lock and does not prevent uncooperative writers from changing bytes before or after the bounded read. Retained Slice 3D7 handles still use share-all for continuity, not exclusive mutation prevention.
- The native file must already exist. No registry, workspace descriptor, journal, collection or Notes record is created, modified, repaired, deleted, or authorized by this change.
- The new synthetic test records the exact native access, share and opening flags on every platform. A native Windows regression independently creates owner-DACL-protected metadata, opens a read-only retained registry guard, and verifies two registry snapshots succeed *while the native handle remains retained*. That native test is skipped on other platforms.
- The original snapshot reader's stricter refusal on invalid ACLs, cloud/reparse/unknown backing, missing files and inconsistent metadata remains. Readers of protected registry content must never present a digest as a commit token.
- Slice 3D8 is a compatibility prerequisite, not the retained registry+journal+metadata integrated admission review. That next review must still compare exact-before bytes under all guards, detect pending recovery, and fail closed on guard exit. Durable CAS, cross-device semantics, reviewed consent, journal creation and recovery remain out of scope.

## Acceptance gates

One precisely guarded tracked-file modification, one new test and one audit, protected source-only ZIP, reproducible archive SHA-256 manifest; focused pytest, Ruff lint/format, strict mypy, full Core pytest, Git hygiene, and conditional commit/push on an unchanged exact branch and remote baseline. Unexpected files, source drift, missing security primitives or any test failure stop without commits.
