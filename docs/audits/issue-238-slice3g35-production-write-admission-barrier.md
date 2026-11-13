# Core #238 — Slice 3G35: Production-write admission barrier

**Starting baseline:** qualified 3G34, commit `4baa5953944ef74319683d092848e102b1d369fa` on `238-establish-private-teacher-workspace-storage`.

**Scope:** one additional private production-write admission **barrier**, regression tests, and this security audit. The barrier is *pure* with respect to filesystem state. It does not turn on production private metadata mutation, binding, Notes records, portability, journal retirement or crash-recovery replay.

## Why this boundary is needed

- **3G32:** canonical prepared write intent can be described in an immutable, non-executable value. The value contains hashes, not authenticated, current native file evidence.
- **3G33:** a protected read-only native review owns its guard only during review. Its result is stale after release; it is not a write permit.
- **3G34:** one canonical native `os.replace` is exercised with internally generated, disposable two-root scratch files. This cannot establish safe production owner/DACL/backing custody or directory-entry durability.

A production writer cannot promote any of these successes into write authority. This slice freezes and tests that refusal at a separate, explicit private Core boundary.

## Implemented contract

`review_private_production_write_barrier(step, expected_revision, proposed)` accepts only an exact `PrivateScratchWriterStep`, positive *non-bool* integer revision, and exact `PrivateTransactionIntent`. Only `STAGE_TO_REGISTRY` is in scope; initialization, descriptor completion and journal retirement are refused. The existing 3G32 decoder handles canonical metadata validation and revision matching, and the new boundary maps its refusal categories to sanitized states.

Even if 3G32 returns a fully matching typed description, the result is **`PRODUCTION_BLOCKED`**, not ready. The returned frozen value contains only its state, a static message and a nine-element tuple of still-unqualified **production** requirements. It contains no raw root, owner SID, byte image, native handle, callback, guard, permit, path or transaction identifier. The module does not accept previous native/scratch findings or caller attestations that the requirements are met.

The requirements are a checklist for implementation and qualification **inside a future operation-owned writer**; they are not all evidence that low-level mechanisms are missing from Core. Prior standalone probes/reviews do not qualify them as an atomic production write protocol.

| Required production evidence | Current status in 3G35 |
|---|---|
| Effective process owner **and private-root ACL/backing** | Not qualified in a production writer |
| Workspace descriptor ownership/binding and path identity | Not qualified in a production writer |
| Native retained custody of four two-root parent directories | Synthetic 3G34 only; production integration unqualified |
| Exclusive operation-owned lock/guard spanning validation, replace and postcheck | Prior read-only and scratch exercises only |
| Canonical intent independently rechecked *inside* the mutation guard | Prior protected review is read-only |
| Exact registry/journal/stage images, identities and revision | Prior protected review is read-only |
| Native target-handle sharing, replacement and exact postimage | Synthetic Windows/3G34 only |
| Directory-entry durability and actual crash/restart qualification | Not proven; file sync alone insufficient |
| Consistent recovery, descriptor convergence, journal retirement protocol | Not production-implemented or qualified |

## No implicit escalation

1. A successful 3G32 description, 3G33 observation, 3G34 native scratch operation, or forged caller object is never sufficient to enable a production write.
2. No public or private operation accepting production directories or native handles is exposed by this slice.
3. All errors are returned through static status strings; no teacher or student information is printed or logged.
4. Unknown future operation and metadata states fail closed without accepting an implicit fallback.
5. A later production writer must own its guard for validation, mutation and postcondition checks, including failure of guard release. No earlier review supplies its authorization.

## Qualification and follow-on

The isolated dependency-stub test suite covers strict inputs, every operation refusal, every 3G32 refusal mapping, malformed successful descriptions, exceptions, immutable results, no transferable capability, sanitized messages and no filesystem side effects. Native Windows qualification and Core's focused suite/Ruff/strict mypy must run through the guarded 3G35 runner before commit.

**Next implementation priority:** qualify a concrete **production operation-owned guard and owner/ACL/backing evidence** against existing Core primitives before allowing one narrowly bounded stage-to-registry mutation. Then separately qualify Windows/POSIX replacement handle behavior, directory durability and a crash/restart recovery matrix. Do **not** infer readiness from the number of passed synthetic tests or from this barrier's output.
