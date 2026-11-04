# Core #238 — Slice 3G24: Windows native sharing-mode compatibility

**Status:** Candidate; requires guarded Windows qualification. No production-write authorization.

## Why this is needed

3G23 established the distinction between a retained file HANDLE and its current pathname across a synthetic replacement. Windows native sharing introduces a separate constraint: an already-open target handle that did **not** grant `FILE_SHARE_DELETE` can prevent rename/replacement even when an exclusive application-level advisory lock is held. A handle that grants delete sharing may permit replacement, but no particular filesystem, file-filter driver, or antivirus configuration is guaranteed to accept it.

## Exact scope

This additive slice introduces `pds_core/_teacher_private_recovery_synthetic_windows_share.py` and matching regression tests. Its only public argument types are exact synthetic enums selecting `NO_DELETE_SHARE` or `ALLOW_DELETE_SHARE` and optional interruption injection. It accepts **no caller pathname, metadata, raw bytes, callback, transaction, owner, handle, guard, or writer token**. It creates four fixed synthetic files inside a fresh module-owned `TemporaryDirectory`. It creates/acquires the existing 3G19 disposable native advisory lock and verifies exact preimages, file IDs and lockfile identity before touching the scratch target.

A native Windows `CreateFileW` opens the synthetic registry with `GENERIC_READ`, `OPEN_EXISTING` and `FILE_FLAG_OPEN_REPARSE_POINT`. The `NO_DELETE_SHARE` case passes `FILE_SHARE_READ` only. The `ALLOW_DELETE_SHARE` case passes `FILE_SHARE_READ | FILE_SHARE_DELETE`. Neither mode enables write-sharing or grants write access. The native HANDLE is converted into a Python binary descriptor with ownership transfer, closed on all normal paths, and used to re-read the **original synthetic bytes** and original native file ID before/after one `os.replace` attempt. The observed current pathname is independently verified against the original or staged file identity, exact byte images, descriptor and journal identities and lockfile identity; checks repeat after the target HANDLE is released, while the synthetic advisory lock is still held.

A sharing-denied native replacement is **not** silently retried after releasing the HANDLE. An unexpected replacement in `NO_DELETE_SHARE` mode is a sharing-invariant conflict. An allowed-delete replacement returning from `os.replace` yields only `DELETE_SHARED_REPLACEMENT_UNQUALIFIED`, not a durable commit. File-ID or byte conflicts, an unexpected native I/O error, advisory-lock refusal and controlled interruption cannot yield a success/authorization result.

## Native behavior, test scope, and limitations

- The two actual Windows tests create disposable files and use real Win32 `CreateFileW` sharing masks and a real replacement. They do not exercise protected teacher-private locations.
- All other tests use a deterministic, read-only in-memory snapshot representing the old native HANDLE, on both Linux and Windows. The snapshot supplies old-byte and file-ID checks without opening an OS target HANDLE that would itself block `os.replace` on Windows. Scratch-file I/O, native advisory locking, identity checks, and filesystem replacement remain real. Mocked `os.replace` branches model both allowed and blocked outcomes, and do **not** prove Windows sharing-mode behavior; the two separate unmocked `CreateFileW` tests exercise that contract.
- On Windows the absent-delete-share case is expected to block, while the delete-shared case accepts a verified replacement or a verified OS sharing refusal. Neither result is a production writer permit.
- The exercise is single-process and local. It does not certify cross-process coordination, adversarial same-user writers, cloud sync/file filter races, native protected ACLs, a stable network filesystem, lock ownership at the real registry/descriptor/journal boundary, durable directory entry ordering, reboot recovery, or crash-safe journal retirement.
- `os.replace` success and exact file IDs prove neither durable persistence nor a canonical transaction compare-and-swap. No journal is retired, no association is changed, and Notes remains disabled.
- Unexpected OS errors fail closed; sanitized status/result messages never return a path, file ID, user identity, or native handle.

## Windows qualification gates

The guarded runner requires exact 3G23 feature/main refs and 175 inherited Git blob pins, a clean branch, an intact three-file source-only ZIP manifest, and absence of any active `teacher_private_storage.py`. It formats and lints the two Python candidates off-checkout while checking AST equivalence, then writes exactly three additive files. It runs the isolated Windows regression suite, a 76-file focused private-Core selection, Ruff, strict mypy and the periodic full Core pytest checkpoint. Only after all gates pass may it commit and push exactly the three 3G24 files; every failure leaves the files for surgical repair without reset/stash/cleanup.

## Next boundary

3G25 should check sharing-mode compatibility of retained, *read-only* native private registry/descriptor/journal guard HANDLE contracts against an intended writer. A mere sharing-mode observation must never enable production mutation; durable persistence, replay, journal retirement and Notes activation remain separate issue gates.
