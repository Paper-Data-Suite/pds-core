# Core #238 — Slice 3D1: ordered read-only pending-journal census

**Baseline:** `01ccd98c0047cadfc639da842efbba6c0e650e8e` (qualified Slice 3D0).
**Authority:** owner-approved Core #238 private storage D0 architecture and `docs/teacher_private_storage_contract_v1.md` §5.
**Boundary:** Existing private transaction-directory review, not admission, journal creation, recovery, binding, Notes storage or an owner-scoped authorization handle.

## Purpose

Before any writer can safely admit a private metadata transaction, it must establish whether earlier protected intent candidates are pending. A directory containing an abandoned or unknown entry cannot be mistaken for a clean, empty store. Slice 3D1 adds `review_existing_private_pending_journals(existing_private_root, existing_workspace_root)` as a **non-authorizing** census of an already existing owner-private `transactions` directory. It acquires the previously implemented local registry-first/workspace-second coordination locks and samples the native effective principal before and after the observation. The caller provides neither an owner SID/UID nor a directory to list directly: the transaction directory is derived solely from the exact platform v1 private-root candidate.

## Conservative outcomes

- `EMPTY_REVIEW_REQUIRED` means that a protected local transaction directory was observed empty twice under the currently held local locks. It is **not** permission to create a journal or to bind Notes.
- `PENDING_REVIEW_REQUIRED` means one or more directory entries of any kind were observed. The scanner does not open, parse, log, delete, overwrite, classify as stale or silently complete any file, symlink or temporary entry. Every entry blocks any inferred journal admission.
- A missing directory is a distinct `MISSING_DIRECTORY` result, **not** empty.
- Changed directory object identity, timestamps or observed entries result in `CHANGED_DURING_REVIEW` where detectable. Unverifiable ancestry, ownership, ACL/mode, backing, coordination, native owner and I/O fail closed into bounded refusal categories.

## Platform and threat details

Linux uses the existing conservative effective-UID-owned, `0700`, ACL and local-filesystem `openat` parent-chain check to retain a no-follow directory descriptor. It compares `fstat` and `lstat` identity with two fd-relative enumerations and refuses unqualified/missing directories. It does not open or read individual transaction entries. Windows uses the existing token-SID, native DACL/reparse directory walker and fixed NTFS/ReFS backing filter, then compares non-follow directory observations and two listings; it rechecks protections after enumeration. No Windows OS-native directory handle is retained throughout the entire listing. This is **advisory**, not a continuously held native write-path proof. macOS, unknown OS accounts, network/cloud-backed private transaction roots and ambiguous protections remain unsupported.

The locks cover only cooperating **local** processes. OneDrive/cloud replication and other devices do not participate in the two-lock protocol. Directory enumeration can race with same-user code, and observing an empty directory does not prove future emptiness after lock release. Windows parent-handle continuity, exact intent admission CAS, human-reviewed consent, protected journal creation *while ordered locks are held*, registry membership, writable descriptor handles, durable cross-tree updates and crash recovery remain **explicit future gates**. Never elevate `EMPTY_REVIEW_REQUIRED` to `READY` or a write token.

## Verification and downstream gate

Unit regressions check ordering, reverse release, denied coordination, principal drift, wrong roots, no capabilities, sanitized outcomes, pending arbitrary files/symlinks, unsafe Linux modes, missing directory distinction, Windows refusal classification and changed-directory evidence. A synthetic-locality non-root Linux test exercises the actual fd-based directory census. Windows native installed-wheel permission and directory-handle behavior are not qualified by these synthetic tests and require later D2 evidence. Existing Core tests, Ruff, strict mypy and Git hygiene must pass on the user's Windows checkout before commit/push.

Next: combine a *current* two-lock metadata review with a verified pending-journal census while preserving native directory/file handles and rejecting ambiguous original/current registry membership. Only after that can an explicitly reviewed, protected create-only intent be **considered** for admission, followed by recoverable cross-tree CAS/atomic writes. #239 Notes records, #240 menus and #243 portability remain excluded.
