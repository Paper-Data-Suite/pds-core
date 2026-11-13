# Core #238 — Slice 3G60: second-generation recovery lock exclusion after forced termination

## Scope

Test-only additive evidence against the canonical scratch `FORK_COPY` pipeline. No production runtime module, teacher-private path, Notes service, storage mutation API, automatic replay or journal retirement is added.

## Qualification boundary

1. A nonce-marked synthetic fixture starts the existing 3G59 writer worker at one of four prepared/installed checkpoints while it holds the one-shot native lock and stage custody.
2. Its parent forcibly terminates the worker without Python context-manager unwind.
3. A **second recovery process** acquires the existing restart lock and four native parent handles, independently classifies the pending canonical transaction, publishes a synthetic-only handshake, and retains the lock.
4. A distinct **third-process** probe must be refused while that lock is held, without writing or modifying canonical files.
5. The parent forcibly terminates the second recovery process. A new **fourth-process** reader must independently acquire a fresh lock, classify the same checkpoint, leave all five canonical metadata images byte-identical, and preserve the journal.
6. Invalid reservation tokens and an unsupported `replay` mode must be refused before any metadata is accessed or changed.

The four mandatory Windows checkpoint cases are `after_prepared`, `after_registry_replace`, `after_descriptor_replace`, and `after_descriptor_flush`. The last represents returned flush requests, not a power-loss durability proof.

## Fail-closed control

The dedicated test worker accepts only a direct OS-temporary child bearing the exact 3G59 nonce reservation, a syntactically valid 128-bit hexadecimal token, an existing scratch transaction journal and native lock, and an explicit `hold`, `probe` or `inspect` mode. All live write operations remain confined to the synthetic ready-marker file; transaction metadata inspection is read-only. Invalid reservations and unexpected lock states are rejected. The Windows qualification runner requires all four process-fence cases to pass without skips.

## Not qualified

Cross-machine or cloud-synchronization locking, adversarial filesystem tampering during path resolution, power-loss persistence, Windows directory durability, two-document atomic commit, safe retry/replay, journal retirement, or installed-wheel production admission. Production-write barriers and Notes activation remain unchanged and blocked.
