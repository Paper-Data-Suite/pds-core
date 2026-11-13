# Core #238 — Slice 3G53: Canonical transaction under retained native parent custody

## Scope and acceptance

This additive, internal-only slice takes the **disposable canonical `FORK_COPY`** transaction from Slice 3G52 and holds all four native directory identities through the operation. Native FD/HANDLE checks are provided by the existing 3G29 `_held_native_parent` primitive; the transaction's exact metadata and journal images are checked by 3G52's canonical classifier. The prior *synthetic* operation lock remains held until both replacements and flush checkpoints end. After it releases, a **new** scratch lock and four **newly opened** native parent handles independently observe the pending journal, registry, and association descriptor.

This closes a rehearsal gap: 3G52 checked exact bytes and a fresh lock, but did not continuously retain all native two-root directory handles during its replacements.

### Native parent custody

The four retained parents, in a fixed order, are:

1. The scratch private registry root, containing `registry.json` and its registry stage.
2. The private `transactions` directory, containing the immutable pending journal.
3. The scratch workspace root, containing `.pds`.
4. The association directory `.pds`, containing the association descriptor and its prepared stage.

Each parent is opened natively, checked immediately, checked after every mutation/flush boundary, and checked during context release. The native handle is **not** handed to the caller or reused for restart. On the restart path the scratch lock is reacquired independently and an entirely new set of four native parents is retained.

### Operation and interruption ordering

- Construct a genuine canonical `FORK_COPY` witness with distinct before/after images for **both** metadata documents and a fixed non-OS synthetic owner; no caller-owned path, intent, content, owner, handle, or callback enters.
- Under the scratch lock and four native parents, write the pending journal and two stages as exclusive new files and verify exact canonical prepared images.
- Request journal/stage flushes, then parent-directory flushes; check native parent identities and the canonical prepared checkpoint again.
- Attempt one stage-to-registry replacement. Mark the attempt *before* the call. Recheck native parents and the exact registry-after, descriptor-before checkpoint. Flush registry and its parent.
- Attempt one descriptor-stage replacement, recheck native parents and both after-images, and request descriptor and association-directory flushes.
- Release all four original native parent handles and the operation lock. Reacquire a fresh restart lock and four native parents to observe exact journal, stage absence, registry, and descriptor images.
- Classify each injected interruption/refusal conservatively. A native attempt that raises or yields uncertain evidence is **not retried**. The pending journal is preserved throughout the execution and is never retired.

A returned flush request is **not** a power-loss durability certificate. An in-process interruption is not a power-cut test. Windows directory-flush returns may be observational but cannot prove durable namespace ordering.

### Explicit exclusions

This module is not the protected teacher-private transaction writer. It does not accept production paths, validate a real local OS owner or restrictive production ACLs, establish hostile same-user exclusion, provide cross-device CAS, guarantee filesystem crash durability, implement recoverable descriptor completion, execute journal retirement, or enable Notes. The temporary-directory lifetime is solely a test harness; its cleanup is not a production transaction cleanup protocol. The existing production write barrier remains unchanged.

### Qualification

The local isolated dependency-stub suite exercises native-parent lifetime composition and synthetic byte-image checkpoints. Native Windows behavior, Ruff, strict mypy, and the broader Core focused suite are separately qualified by the guarded Windows runner. The runner demands the exact 3G52 Git baseline and inherited blob pins and commits exactly these three additive files only if every gate passes.
