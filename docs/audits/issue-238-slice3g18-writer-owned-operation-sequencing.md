# Core #238 — Slice 3G18: Writer-owned operation sequencing contract

**Status:** Source candidate for native Windows qualification; does not grant recovery mutation authority.

## Scope

Add a strict, pure, fail-closed classifier for the *reported* phases of a future operation-owned native recovery writer. Its inputs are a proposed canonical transaction intent, an operation kind, an expected registry revision, a bounded phase trace, a reported interruption outcome and caller-provided before/after byte images. It is explicitly **not a writer**, guard acquisition, journal manager, persistence protocol or public Notes capability.

The phase order is:

1. `GUARD_ACQUIRED`
2. `PREIMAGE_REVALIDATED`
3. `OPERATION_INVOKED`
4. `OPERATION_RETURNED`
5. `POSTIMAGE_REVALIDATED`
6. `PERSISTENCE_REQUESTED`
7. `GUARD_RELEASED`

A trace must start with guard acquisition, contain only unique, canonical enum members, and obey these dependencies. A no-operation read-only trace may release its guard after preimage review. An attempted operation cannot report orderly guard release without a postimage review. Repeated phases, backward ordering, missing invocation/return or postimage and persistence checks in the wrong position fail closed. This is an **ordering contract for a future coordinator**, not a claim that the events actually occurred.

## Exact images, revisions, and interruption

The implementation calls the already-qualified pure 3G17 interruption triage, which in turn uses 3G15's exact-image/revision postcondition classifier. It refuses mismatched intent images, revisions and incomplete/partial transitions; an operation reported as not started cannot contain a mutation phase or changed postimage. A reported return without a postimage review is incomplete. A reported return with an exact postimage remains **review required**, with native guard continuity, actual mutation, CAS and durability unproved. A reported persistence request produces **persistence unqualified**, not a durable-commit state. Unknown/interrupted operation status always preserves the evidence. Journal retirement remains categorically unqualified.

## Threat boundary and non-goals

- Phase reports and before/after images originate from untrusted callers; they cannot authenticate a local OS user or attest to a held kernel lock, native file identity, filesystem durability or actual write.
- There are no paths, handles, callbacks, mutable authority objects, write tokens, file reads, file creation, mutation, cleanup, journal retirement or Notes service exports.
- Reported `GUARD_RELEASED` is never an authorization for a new operation or a cross-process CAS reservation.
- Malicious same-user writers, cloud-synced workspace changes, distributed storage, power loss, ACL and reparse-point handling remain native-coordinator concerns.
- 3G18 does not turn 3G14/3G16 read-only observations into a writer. Before any production write, a separate guarded native coordinator must revalidate actual file identities, owner, journal and expected revision *inside the same writer-owned scope*, execute at most one qualified operation, verify exact postconditions under that scope, and prove the required persistence/retirement properties independently.

## Regression selection and acceptance

`tests/test_teacher_private_recovery_writer_sequence.py` contains 101 synthetic cases: two positive exact-image operation kinds, precheck and reported persistence outcomes, out-of-order and repeated traces, malformed argument types, expected revision mismatch, initialization refusal, unknown/interrupted phases, changed and partial images, no-progress outcomes, retirement refusal, deliberately raised exceptions, malformed classifier results, immutable sanitized outputs and absent Notes capability advertisement.

Windows qualification runner checks the exact 3G17 branch head, main and feature remote heads, inherited blob IDs and clean checkout; it runs the 3G18 tests, focused #238 suite, Ruff and strict mypy, and commits/pushes only if all pass. The next periodic complete Core integration run follows the clean 3G16 full run of 5,154 tests.

**Conclusion:** This slice establishes explicit nonauthorizing operation-order and interruption invariants. It neither implements nor authorizes a recovery writer.
