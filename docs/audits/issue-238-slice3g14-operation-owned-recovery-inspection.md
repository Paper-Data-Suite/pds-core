# Core #238 — Slice 3G14: Operation-owned retained recovery inspection

## Scope and exact qualification

Baseline: `da9959154a7718360eaa70929d69cb527c7c1be3` (qualified 3G13).

This slice adds one **private, non-mutating** operation-owned recovery inspection, with a single continuous retained native descriptor/journal/registry guard. It combines the existing native checkpoint classifier (3G9/3G11) and exact-image reader (3G12) *within the same lock-honoring scope*, instead of the independently guarded cross-checks in 3G13. There are no new public APIs or Notes services.

Supported proposed review stages are (1) staged before-state / prepared restart review, (2) registry after-image with descriptor still before / descriptor completion review, and (3) registry and descriptor after-images with journal still pending / retirement review. These names do not authorize the corresponding mutation.

## Fail-closed ordering

1. Refuse unsupported OS, untrusted caller inputs, unsafe roots, malformed/counterfeit canonical intent, initialization, and incoherent revision progression. Expected revisions must be exact integers, and non-initialization changes increment exactly by one.
2. Acquire the pre-existing retained native descriptor guard **once**. No reader may reacquire it. Capture the effective OS identity, pending journal/stage namespace, and stage inventory.
3. Repeat twice under the same guard: check native stage inventory/namespace/owner, classify the checkpoint, read exact journal, registry, descriptor and optionally stage images through existing native readers, and re-check inventory/namespace/owner.
4. Refuse conflicting/reordered checkpoints, changing bytes, missing or malformed evidence, wrong stage, mismatched journal bytes, mismatched registry/descriptor/stage before/after images, or an actual registry revision that differs from the expected value.
5. Require final native namespace/owner/inventory stability and **successful guard release** before emitting a sanitized advisory state. No bytes, handles, paths or authorization tokens escape.

The native reader's protection, locality and owner preconditions are inherited and must be tested in the actual Core workspace environment. The filesystem is not altered by 3G14; the tests use only synthetic objects and disposable pytest locations.

## What this does not establish

No in-process callback is executed and no file is written, renamed, replayed, truncated, or deleted. This is **not** a compare-and-swap, write transaction, source-of-truth binding, durability proof, stage consumption, descriptor repair, pending-journal retirement, initialized association, mixed-user support, or Notes/Tasks activation. A matching result is not a reusable permit. Separate qualification of atomic postconditions, persistence, and power-failure recovery remains necessary before enabling actual mutations. Hostile same-user writers and synced roots are outside the local lock-honoring promise.

## Acceptance

- Synthetic regressions cover all three exact checkpoint states; one continuous guard; two rounds; release before advisory success; immutable sanitized results; exact byte and revision refusals; checkpoint and image drift; owner/namespace/inventory change; native guard failures, interrupts and unsupported environments.
- Runner requires exact Git/remote baseline and inherited blob pins, formats and lints off-checkout, applies only one module, one test and this audit, runs new tests plus focused Core #238 tests, Ruff and strict mypy, and commits/pushes only on complete success.
- Periodic full-Core pytest is deferred following the fully green 3G13 integration checkpoint (4,867 passed, 174 skipped).
