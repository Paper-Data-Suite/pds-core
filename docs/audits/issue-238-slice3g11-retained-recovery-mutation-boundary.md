# Core #238 — Slice 3G11: Retained native recovery boundary

**Base:** Qualified Core #238 3G10 `45dc78ee2d10253ed7e4dbcbf8bc2656b1af00d5`.

## Decision and scope

The internal `review_retained_private_recovery_mutation_boundary` function accepts exactly one of the three **review** steps defined by Slice 3G10. It validates canonical transaction intent and rejects initialization before locking. It holds the existing 3E0 retained descriptor/journal/registry guard **once**, keeping the complete ordered-lock scope across two native 3G9 image classifications and three namespace, stage-inventory and OS-owner censuses. It uses the 3G9 inner `_classify_present` / `_classify_absent` readers, which are designed to run inside an already retained native guard; it must not invoke the public 3G9 entrypoint recursively.

The three permitted review outcomes are (1) prepared restart review for a stage-present before-image, (2) descriptor completion review where the registry after-image exists and the descriptor is before, and (3) journal retirement *review* where both after-images are present and the stage is absent. All three are **non-authorizing**. The response contains only a frozen state and fixed sanitized message, never a path, data bytes, identity, open handle, write callback, consent, revision token or ability to execute a step.

## Failure modes

The function refuses changed namespace/inventory/owner before, during or after either native classification. A between-read image change is `IMAGE_DRIFT_PRESERVE`; a consistent stage-present non-before checkpoint is `STAGED_CONFLICT_PRESERVE`; an incompatible requested step is `ACTION_MISMATCH_REFUSED`. Missing or conflicting evidence, unexpected result classes, owner/protection loss, IO errors and the guard postcondition all fail closed. `KeyboardInterrupt` returns a sanitized preservation state and `SystemExit` propagates. No fallback filesystem operations, automatic retries, repair/delete/rename, journal retirement, private writes, CLI command or public Notes capability are introduced.

## Explicit limits and future qualification

Continuous retained locking reduces windows for **cooperative, lock-honoring local processes**, compared with 3G10's separated scopes. It does **not** prevent a hostile same-user process from bypassing locks, prove that two equal classification labels imply unchanged raw bytes (ABA), or establish cross-file CAS, kernel rename persistence, power-loss durability or recovery correctness after a crash. It is not a mutation executor. Any later mutation must validate exact native bytes and identities within the actual mutation operation, respect expected-revision CAS and approval, and preserve a pending journal until independently qualified durable completion and safe retirement. Notes/Tasks remain separately owned by Core #239/#240/#243 and are not activated here.

## Verification plan

- Require the exact 3G10 feature/main remote refs and tracked file hashes before adding only the three 3G11 files.
- New deterministic tests cover continuous guard ordering, all three action matches, every alternate action, three inventory failures, three namespace/owner changes, image drift, stage conflict, refusal states, invalid inputs, guard postconditions and interrupt/exception handling.
- Run new 3G11 tests, focused issue #238 tests, Ruff and strict mypy. The full Core suite passed 4,696 tests in 3G10 and is deferred to the next periodic integration checkpoint. Qualify on native Windows; do not equate mocks with production native integration or installed-wheel acceptance.
- Commit and push only after all gates pass; never reset, clean, stash, or mutate private teacher storage.
