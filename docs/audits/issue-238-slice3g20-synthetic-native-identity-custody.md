# Core #238 — Slice 3G20: Synthetic native file-ID and guard-custody rehearsal

**Status:** additive candidate for guarded Windows qualification. The prior 3G19 full Core checkpoint passed (5,415 passed, 174 skipped). This document **does not authorize production metadata mutation**.

## Narrow change

Add a new private module and tests which execute one real `os.replace` on **fixed synthetic registry/stage bytes** in a fresh, module-allocated temporary directory. Reuse the previously qualified 3G19 scratch lock, exact-byte readers, synthetic journal/descriptor literals, and file-only sync request. No public teacher command or package export is added; there is no caller-supplied filesystem path, byte payload, callback, handles, native writer delegate, association intent, or token.

## Custody checks

Under one retained **scratch advisory lock**, verify the exact initial filename namespace and images, then obtain separate path and open-handle identities for the synthetic registry, stage, descriptor, journal, and lockfile. Each native identity is a `(st_dev, st_ino)` pair. The routine requires a nonzero inode, regular file, one link, and agreement between path `lstat` before/after the handle `fstat`; the handle is closed before the Windows replacement to avoid rename sharing conflicts.

After the native stage-to-registry replacement, verify exact postimage bytes and absence of the staged name, and require that the new registry file ID **equals the prior stage ID but differs from the prior registry ID**. Descriptor/journal/lockfile IDs must remain stable. Repeat postimage and identity checks after the file-sync request, all before releasing the scratch guard. A byte-identical copy-in-place, a byte-identical replacement of a sidecar file, changed native file IDs, absent IDs or unexpected bytes must not return the advisory observed state. All returned results contain only fixed sanitized enum/message values.

## Fault injection and tested refusals

In-process fault injection tests six requested states including after guard, preimage, replacement, postimage, and sync boundaries. Unexpected errors, lock refusal, invalid requests, missing native IDs, interrupted steps, wrong preimages or substituted postimages are classified conservatively. No interruption mode is treated as a completed commit.

## Limits and explicit nonclaims

- **Synthetic only.** A `TemporaryDirectory` is allocated internally, and only four fixed synthetic files plus the internally generated lockfile are touched. No teacher-private workspace file can be selected through the entry point.
- **Advisory, not hostile-writer-safe.** The `msvcrt`/`fcntl` scratch lock is effective only for cooperating processes. The code does not retain all production descriptor, journal, registry and directory anchor handles or protect against same-user adversarial namespace races, mount changes, reparse points or hard-link tricks outside this scratch fixture.
- **File ID observation, not atomic custody.** `lstat/fstat/lstat` under an advisory lock can catch simulated changes and offers evidence of rename identity propagation; it cannot establish the production native, anchored handle-lifetime invariant or guaranteed compare-and-swap for arbitrary changes.
- **No durability or recovery authority.** `os.replace` and file `fsync` on this scratch fixture cannot prove parent-directory persistence, Windows crash durability, journal retirement or power-loss reconciliation. A matching result is always `IDENTITY_OBSERVED_PERSISTENCE_UNQUALIFIED`.
- **No Notes.** This module cannot create a teacher record, initialize an association, activate Notes or expose any data-management command.

## Windows qualification and follow-on

The guarded runner must verify exact 3G19 HEAD, `origin/main`, inherited Git blob pins, clean working tree, exact three-file manifest and requested source ZIP hash. It must run the new scratch regression tests, the full focused Core #238 suite, repository Ruff and strict mypy, and conditionally commit/push only after every gate passes. The periodic full Core pytest run may be deferred because 3G19 completed its full 5,415-test checkpoint. A failure preserves candidate files and never resets the checkout.

3G21 must move toward *actual* production descriptor/registry/journal native anchor identity verification in a **read-only, fixture-backed scope** before even considering operation-authorizing writes. The 3G20 scratch result must not be reused as a teacher-private permit.
