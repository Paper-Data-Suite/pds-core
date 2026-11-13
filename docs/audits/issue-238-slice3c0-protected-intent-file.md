# Core #238 — Slice 3C0 protected transaction-intent candidate creation

**Required branch baseline:** `0ed67507962f971016965d8375f290eb84511b1e` (qualified Slice 3B9).
**D0:** Five architecture decisions approved by project owner 2026-10-25, documented in issue #238 and Slice 3B7 audit.
**Status:** Internal, explicitly invoked **create-only** primitive, deliberately not a transaction service or an active Notes capability.

## Motivation and exact scope

Existing Slices 3B3–3B5 define immutable transaction witnesses, bounded exact-byte intent envelopes and non-mutating interrupted-write review. Slices 3B6–3B9 add existing-file locking, guarded private directory creation and initial `.registry.lock` creation. None of those pieces creates persistent transaction-intent metadata. A future guarded commit must durably stage a recoverable intent *before* touching the workspace sidecar and owner-private registry. The gap is addressed here narrowly, without implementing a commit protocol.

`pds_core._teacher_private_journal_provision.create_private_transaction_intent_file` can create a single protected `<UUIDv4-transaction-id>.json` under an **existing** `<approved user-local Notes v1 root>/transactions` directory. It does **not** create the parent, any private root, the `.registry.lock`, registry, workspace sidecar, or Notes records. The caller provides already encoded bytes; the module refuses noncanonical or malformed intent envelopes and checks that the enclosed registry owner kind/value matches the freshly observed OS security principal. A transaction UUID is a filename key, never authorization.

### Linux

Uses held, `O_DIRECTORY | O_NOFOLLOW` directory descriptors from the existing native helper; verifies ordinary non-root effective-UID ownership, mode `0700`, POSIX access ACL absence and conservative local backing. Uses `O_CREAT | O_EXCL | O_NOFOLLOW` and mode `0600` for the new file, writes all bytes, `fsync`s file and directory, and rechecks ownership/mode, single-link identity, file size, ACL and local backing before reporting restrictive creation. No existing target—including dangling symlinks—is overwritten or repaired.

### Windows

Requires the exact `%LOCALAPPDATA%`-derived private `transactions` subtree, current process-token SID, supported fixed NTFS/ReFS volume and native parent no-reparse/owner/DACL refusal check. Reuses the proven 3B9 `CREATE_NEW` helper to create the file with an explicit inheritance-protected DACL for that account, SYSTEM and Administrators. Uses `WriteFile` and `FlushFileBuffers`, checks opened-handle attributes/DACL and repeats the parent/volume refusal checks. The parent path is re-evaluated but **not held as one race-free directory-handle chain** across all operations. This primitive's positive result remains **RESTRICTIVE_UNQUALIFIED**, never `READY` or transaction-committed. Native Windows behavior and installed-package qualification must be verified on a genuine Windows checkout.

### Refusal and partial state

Every result is an enum plus fixed sanitized text. No paths, owner IDs, Note contents, handles, or decoded private metadata appear in results. Existing entries are preserved byte-for-byte, even if corrupt; there is no overwrite, rename, deletion, chmod/chown repair, or stale-file cleanup. If an error occurs **after** exclusive file creation, the result is `CREATION_UNVERIFIED` and the file is deliberately preserved for human/security review. Unknown filesystem backing or ACLs fail closed. macOS remains explicitly unsupported.

## Missing protections before live transaction writes

- This helper **does not acquire** the existing `.registry.lock` or a workspace-sidecar coordination guard. A future service must acquire both in documented order under stable native handles, re-read revision and owner/security context, and perform CAS checks before using any journal.
- It does not implement atomic registry/descriptor writes, anti-rollback revision control, durable intent completion markers or automatic crash recovery. The journal file's mere presence never asserts a valid, started or completed binding.
- It does not establish race-resistant Windows parent handle identity across directory checks/creation, nor local backing proof beyond conservative filesystem-type checks. Native adversarial security and D2 installed-wheel validation remain required.
- It does not call the helper from `teacher_experience`, CLI, Suite, producer modules or a Notes record service. The capability set remains exactly `terminal.header.v1` and `terminal.notes_command.v1`.

## Evidence and qualification

Synthetic tests cover strict canonical data, wrong owner kind/value, unsupported platform, no activation/capabilities, duplicate preservation, no symlink overwrite, parent mode and backing refusal, and partial state on restrictive umask. A non-root Linux sandbox has exercised the actual create path. Windows fixtures explicitly create a synthetic restricted tree and test the native API on Windows; those cannot be claimed completed by Linux test results alone. The guarded local runner must pass focused tests, Ruff, strict mypy, full pytest, exact three-file source diff and remote HEAD checks before commit/push. **No live teacher data or real workspace is used in these tests.**
