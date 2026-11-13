# Core #238 — Slice 3G54: canonical FORK_COPY cross-scope protected handoff

**Branch:** `238-establish-private-teacher-workspace-storage`
**Required baseline:** `146ed1cc04fe62eaaead98097ec4e0b32d888b92` (qualified 3G53).
**Required remote main:** `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`.
**Qualification:** three additive files; guarded Windows runner; no production write enablement.

## Integration boundary

3G52 established a genuine canonical synthetic `FORK_COPY` intent with two changing documents and an independent restart classification. 3G53 retained four scratch native parents through that sequence. Neither test could be transferred into an owner-bound production filesystem writer. Earlier 3G45 already observes protected prepared native evidence *inside* the one-shot stage/registry pair. 3G9 reacquires a separate protected native reconciliation guard, and 3G35 holds the production writer barrier shut.

3G54 adds one **strictly read-only** assembly of these existing, unrelated contracts:

1. Require an exact `PrivateScratchWriterStep.STAGE_TO_REGISTRY`, exact `PrivateTransactionIntent`, canonical JSON bytes/round-trip and a genuine `PrivateBindingOperation.FORK_COPY` with both document images changed.
2. Demand an exact expected *before* registry revision. Reject all other operations (including `INITIALIZE` and `REBIND_MOVE`) without touching native custody.
3. Observe `PrivateProductionWriteBarrierState.PRODUCTION_BLOCKED` and its complete immutable `barrier._REQUIRED` taxonomy.
4. Invoke `review_sealed_native_pre_attempt_boundary` (3G45) using Core's real OS identity, workspace binding, ordered locks, protected journal/descriptor, native registry/stage pair and four canonical frames. Require its exact blocked outcome and unchanged requirements.
5. Once that native scope has been **released**, reacquire independent guarded native recovery with `reconcile_native_private_pending_registry_after_interruption` (3G9). Only the exact prepared stage/before-image permits reporting `PREPARED_FORK_REOBSERVED_BLOCKED`. If registry or both documents have advanced, report a distinct *preserve* state; do not retry or infer a completion.
6. Reevaluate the production writer barrier after the fresh recovery state. Failure or drift refuses the positive advisory observation.

**CRITICAL:** The 3G45 and 3G9 scopes are **separate**. Their observations cannot prove a single continuous production mutation window or exclude uncooperative same-user changes in the interval. All outcomes retain the fixed `production_writes_blocked`, `durability_unqualified`, `journal_retirement_forbidden`, `no_automatic_retry`, and `separate_native_scopes_not_atomic` restrictions. The returned object contains no trusted owner, caller path, raw bytes, open native handle, callback, or write permit.

## Threat and refusal matrix

- Invalid types, noncanonical intent, non-`FORK_COPY` operation, wrong before-revision: fail **before** entering native scope.
- Incomplete/changed 3G35 barrier requirements: fail closed without advancing.
- Incorrect, foreign or changed 3G45 result: refuse, preserving the pending transaction.
- Independent 3G9 review shows registry after-image: preserve for separately qualified descriptor recovery; never retry registry replace.
- Independent 3G9 review shows both after-images: preserve pending journal and deny retirement.
- Any ambiguous 3G9 result, namespace change, owner change, denial or interruption: preserve.
- Final 3G35 state or requirement drift: refuse after independent reinspection.
- No developer test result or synthetic 3G53 review can be supplied as a capability to this API; there is no 3G53 result argument.

## Qualification and release gates

The Windows runner pins **265 existing #238 Git blobs** and exactly three additive files, runs the 3G54 regressions, 3G53 native synthetic Windows smoke test, **106 focused Core tests**, Ruff lint/format and strict mypy. It commits/pushes only on a clean, fully qualified checkout. The full Core checkpoint after 3G40 is still deferred; it is required before final PR/release acceptance.

This slice establishes an enforceable bridge between canonical FORK_COPY semantics and actual protected preattempt/restart *readers*, not a production transaction. **Remaining:** one continuously held operation-owned native guard capable of a qualified write and recovery-safe two-document protocol; initial binding protocol and conflict resolution; crash-directory persistence policy; journal retirement authority; cross-platform native proof, installed wheel D2 and complete CI. No Notes record service/menu/CLI, no production writer, no private-data import or migration.
