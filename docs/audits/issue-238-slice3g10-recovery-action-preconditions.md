# Core #238 — Slice 3G10: Native recovery-action preconditions and interruption containment

**Baseline:** qualified 3G9 `c680317d997f6c15a2433e1a2037f2b7707a7969`.

## Scope and purpose

Implement a bounded, internal, **non-authorizing** recovery-action review on top of the 3G9 single-lock native post-crash reconciler. This unit does not attempt replay, descriptor mutation, native registry replacement, journal retirement, any cleanup, or Notes. Its output is a frozen sanitized advisory result, with no paths, owner IDs, journal bytes, handles or mutation tokens. It is not a recovery coordinator with production execution permissions.

The caller identifies one narrowly framed **review** step: `REVIEW_PREPARED_RESTART`, `REVIEW_DESCRIPTOR_COMPLETION`, or `REVIEW_JOURNAL_RETIREMENT`. The function obtains two sequential, separately protected 3G9 observations. Its first observation must match a known reconciled state, and its second must reproduce that exact state; a step mismatch refuses review. The only acceptable pairs for further *manual* assessment are:

| Stable native observation | Corresponding review request |
|---|---|
| Exact prepared before-images with an existing stage and pending journal | Review a prepared restart, not execute it |
| Registry after-image, stage absent, descriptor before-image, journal pending | Review descriptor completion, not write it |
| Both metadata after-images, stage absent, journal pending | Review journal retirement, not perform it |

A staged after-image with changed metadata is **always** a conflict-preservation state, never an automatic repair target. Stage unexpectedly absent in a before-state, mismatched image, extra/missing journal, unsafe stage, owner or protection refusal, platform refusal and corrupt native result all fail closed. A changed first/second checkpoint refuses; no implicit retry or loop. A `KeyboardInterrupt` returns sanitized `INTERRUPTED_PRESERVE` without writes; process `SystemExit` is allowed to propagate rather than being swallowed.

## Concurrency and durable-state limits

**Two separate 3G9 checkpoints do not hold locks continuously across the two reads.** A hostile same-user process, sync client, or system crash can change evidence between or after them, and an ABA change can evade equality of classifications. Therefore even `MATCHING_CHECKPOINT_REVIEW_REQUIRED` grants **no** permission to execute the reviewed step. A later mutation-aware coordinator MUST revalidate canonical transaction bytes, native identities, owner, namespace, exact before/after images, custody, user consent, expected revision, and crash-durability evidence inside the actual mutation scope. No memory of 3G10 can be trusted as a CAS token or durable commit record.

3G7 registry `FlushFileBuffers` and 3G8 directory flush probes did not prove rename persistence across power loss, and neither does 3G9 or 3G10. The pending journal remains mandatory; 3G10 cannot retire it. No Notes record APIs are implemented or activated, and the existing `teacher_experience` capability set remains unchanged.

## Qualification gates

- Exact 3G9 feature/main Git baseline and 133 inherited blob pins verified before modifying checkout.
- Exactly three additive files: internal review module, bounded synthetic regression tests, and this audit. No existing file rewritten.
- Ruff format and check performed against payload **off-checkout** before applying files.
- New tests verify the three exact review matches, all six action mismatches, stage conflict, native checkpoint changes, native refusal states, invalid inputs, sanitized exceptions, mid-review interruption, process termination propagation, and no Notes capabilities.
- Focused Core #238 tests, Ruff lint+format, strict mypy and full Core pytest, with automatic commit/push only after all gates pass.
- Linux/Windows native integration, installed-wheel qualification, crash/power-loss resilience, and production teacher-facing recovery are independent unqualified gates. A synthetic test suite is not a durability proof.

Any failure preserves the checkout and pending teacher data. No `git reset`, `git clean`, stash, deletion, replay, or secret-bearing diagnostic logs.
