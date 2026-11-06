# Core #238 — Slice 3G40: single-scope native sharing/replacement rehearsal

## Scope and baseline

**Additive-only and synthetic-only.** Baseline: `8963fbaac4aed1bb5f3b54ccd682ebe7f754be5e` (qualified 3G39). Three new files: this audit, the private `single_scope_share_replace` implementation, and its regression tests. No existing Core file, Notes API, owner registry, private journal or transaction is mutated by the installed feature.

The 3G34 canonical two-root rehearsal originally released a restrictive Windows registry reader before its `os.replace`; the 3G39 transition model explicitly acknowledged that its separate sharing probe did not prove the actual operation's sharing conditions. This slice tests that gap in **disposable scratch only**.

## Executable boundary

`rehearse_synthetic_share_safe_single_scope_replace(step, interruption)` accepts only exact typed enums. It creates its own temporary two-root fixture with a fixed, canonical transaction and fixed synthetic registry/descriptor/journal/stage bytes. It neither accepts nor returns real filesystem locations, metadata, user identities, native handles, callbacks, permission flags or transaction tokens.

Within **one** scratch lock and four retained native parent scopes:

1. Recompute the strict canonical transaction and its prepared-stage fingerprint.
2. Open the **actual scratch destination and stage** as native read handles. On Windows both handles explicitly request `FILE_SHARE_READ | FILE_SHARE_DELETE`, with no write-sharing or write access. A sharing permit to *attempt* `os.replace` is not a guarantee of OS acceptance.
3. Validate exact preimage content and native file identities through the two held handles; check the journal, descriptor, registry and stage namespace, then perform three fresh pre-operation censuses without releasing either read handle or parent custody.
4. Invoke **one** `os.replace(stage, registry)` in the disposable scratch root. No fallback, alternate target, replay or automatic retry exists.
5. If native replacement returns success, compare exact postimage bytes, namespace and native IDs; verify the old registry image remains on the original held target handle and the stage after-image remains on the held stage handle. Recheck after a bounded file-only `fsync` request. The original stage must no longer exist at its old pathname.
6. Release both file handles, all parent handles and the scratch lock before returning an immutable, sanitized status. A failed release cannot yield the positive status.

A documented Windows access/sharing/lock refusal is not treated as success. The code checks whether the original scratch namespace is still present; any conflicting census becomes **post-attempt unknown**, not an invitation to retry. Unknown OS failures, post-attempt interruptions, and an exception after a successful native replace are also classified as potentially completed, with pending evidence to be preserved. This remains conservative even if an individual local filesystem returns a strong refusal code.

## Explicit non-claims

- Native scratch delete-sharing observations do **not** authorize production replacement or establish cloud/distributed locking.
- A process-local advisory lock cannot prevent an uncooperative or same-owner external writer.
- The disposable canonical owner is fixed synthetic data, not the real effective OS owner.
- File-only sync does **not** establish directory-entry durability, power-loss atomicity, restart safety or a committed transaction.
- The stage disappears from the scratch pathname only after a native replace; no real registry stage, journal, association descriptor, or Notes collection is touched.
- The 3G35 production write barrier remains in force. No new public service, private writer, journal retirement or Notes activation is introduced.

## Refusal/regression matrix

- Invalid request types, all non-stage operations, unsupported OS.
- Each deliberate interruption, before vs. after the exact replace invocation.
- Native source/target handles with delete-sharing, owner/parent retention and preimage drift.
- Held byte identity mismatch before and after replacement; stage/registry ID swap; postimage namespace and file-only sync.
- Windows access, sharing, lock and unknown I/O classification; refusal without mutation and ambiguous replacement despite a reported error.
- Scope-release failure and no emitted capability/handle/path or retry permission.

## Qualification plan

The Windows runner pins the 3G39 commit, main and feature remote refs, all 223 inherited Git blobs, exact three-file additive scope, source ZIP hash and manifest. It runs the 3G40 tests, 92-file focused #238 suite, Ruff and strict mypy. The periodic **full Core suite** also runs at this 3G40 milestone (the previous full checkpoint was 3G30). Commit/push occurs only after every gate passes. A failure preserves the untracked candidate files without resets or cleanups.

**Until actual Windows qualification succeeds, this slice is only packaged and locally simulated, not released or certified.**
