# Core #238 — Slice 3G57: disposable native dual-stage one-shot replacement

**Scope:** Three additive files, scratch-only `FORK_COPY` attempt and regression tests. The previous 3G56 protected production-native observation and its production write barrier are unchanged. This audit is an implementation record, not installed-artifact, production or power-loss qualification.

## Specific gap resolved

3G53 retained the four parent directory identities during a canonical scratch two-document replacement, but did not retain both *stage-file identities* across the native replacements. 3G55 introduced a protected, non-mutating native descriptor-stage reader, and 3G56 combined descriptor-stage observations with the existing registry-stage scope. This slice rehearses the missing **operation-owned transition of the two actual staged native file identities into their respective final names** on fresh disposable scratch.

## Invariants of the scratch operation

1. The entry point accepts a fixed interruption enum only. No caller path, account identity, private data, callback, file handle, transaction token, or external write destination can enter the operation. The function creates all files in an internally owned `TemporaryDirectory`.
2. The transaction is a genuine canonical Core `FORK_COPY` intent with distinct before/after registry and descriptor images. The canonical pending journal is written before both replacement attempts.
3. The operation retains a scratch lock, native handles to the private root, transaction journal directory, workspace root and `.pds` association directory, plus a separate native file FD/HANDLE for **each** staged after-image. On Windows, stage handles open with native read-only sharing that permits the operation's own rename; on Linux, stage handles use no-follow file descriptors.
4. Each stage is checked for a regular non-reparse single-linked file, exact expected size/image, unchanged native identity while prepared, and the identity's presence at the correct destination after its `os.replace`. The original stage name must no longer exist. The two stage attempts are marked separately and exactly once before their replacement calls.
5. File and parent persistence requests occur before the first replacement and after each returned replacement. Returned flush requests are **not a durable-write certificate**. The journal is never unlinked, rewritten or retired by this operation.
6. A failing or uncertain `os.replace` is never repeated. The operation releases all original native handles and locks before acquiring an independent restart lock and fresh parent handles. Restart classification uses the exact existing canonical journal and image classifier. Every result is a HOLD or refusal with `automatic_retry_forbidden`, `automatic_replay_forbidden`, `journal_retirement_forbidden`, `durability_unqualified` and `production_writes_blocked` set.

## Failure matrix exercised

- Invalid enum and unsupported OS: refuse before scratch creation.
- Prepared-image corruption; missing, linked or redirected stage; native identity mismatch: refuse and preserve evidence.
- Failure before/after each separate attempt mark, replacement, or flush: preserve journal and classify independent restart checkpoint.
- First or second `os.replace` refusal: **one call only** for that stage; no retry. The attempt marker remains conservatively set when outcome is uncertain.
- Native parent failure, stage-handle failure, preparation flush refusal, changed restart namespace, and independent restart-lock/parent failure: fail closed.
- Real POSIX descriptor holds: stage handle retains the same native identity as the destination after replacement; alias/hardlink/wrong-size and in-place image mutation are rejected.

## Deferred security and acceptance gates

This is synthetic, self-owned temporary storage. It does **not** establish production Windows ACL/token-SID binding, qualified workspace descriptor or registry custody, cross-root transactional atomicity, cross-device/cloud coordination, power-loss survival, automatic crash replay, final commit, journal retirement or Notes readiness. In-process interruption tests do not simulate sudden power removal. The OS-native Windows qualification remains pending until the guarded runner executes. The issue #238 production writer barrier stays unchanged and blocked.

Next engineering work should connect the two retained stage-file identities with the continuously held **protected operation-owned** native guard, including owner/binding checks and the existing write barrier. It must not treat this disposable drill as a production capability or claim that a successful native file flush or directory flush is a verified durability guarantee.
