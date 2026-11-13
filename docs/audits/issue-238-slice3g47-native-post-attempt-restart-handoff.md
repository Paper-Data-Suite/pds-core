# Core #238 — Slice 3G47: independent native post-attempt restart handoff

**Baseline:** `f850e8413521fffa43c14efdfe25b6c26b9268e7` (qualified 3G46).
**Pinned main:** `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`.
**Scope:** Three additive files; no Core public capability, Notes record or production write.

## Engineering decision

3G46 proved one native replacement under a disposable one-shot scope. That does **not** prove production durability, does not eliminate partial/interrupted operations, and supplies no post-crash admission token. An uncertain operation must be interpreted from a new native observation rather than from its previous process's in-memory attempt marker or success status. Earlier 3G4/3G9 readers already supply a protected journal/registry/descriptor/stage census and a read-only crash-state classification. Re-implementing them in a second filesystem reader would enlarge the attack surface unnecessarily.

3G47 composes those qualified readers into an explicit **non-authorizing restart disposition**, implementing `review_private_post_attempt_native_restart`. The entrypoint requires a canonical typed transaction, the exact before revision, existing qualified local roots, owner/binding preflight, and an unchanged *blocked* production write barrier. It calls the native postcrash reconciliation reader to acquire its **own fresh ordered locks and native retained guard**, without reusing a pre-attempt handle, callback or stale observation. No user-supplied native checkpoint, writer, previous-result token or retry flag is accepted.

## Outcome protocol

| Fresh native outcome | 3G47 recovery disposition | Allowed write/retry? |
| --- | --- | --- |
| Registry before and stage present | `PREPARED_STAGE_PENDING_REVIEW` | **No**; might reflect refusal, interruption, or different custody |
| Registry after, stage absent, descriptor before | `REGISTRY_AFTER_DESCRIPTOR_PENDING_REVIEW` | **No**; descriptor completion and durability not authorized |
| Registry and descriptor after, stage absent, journal pending | `BOTH_AFTER_JOURNAL_PENDING_REVIEW` | **No**; retirement and crash durability not authorized |
| Stage present in another checkpoint | `STAGE_REMAINS_OTHER_CHECKPOINT_PRESERVE` | **No** |
| Stage absent with registry before / partial descriptor | `STAGE_MISSING_BEFORE_PRESERVE` / `STAGE_MISSING_PARTIAL_PRESERVE` | **No** |
| Missing, competing, changed, malformed, unqualified, or conflicting evidence | Bounded refusal state | **No** |

Every returned state sets `replacement_may_have_occurred=True`, `pending_evidence_must_remain=True`, `automatic_retry_forbidden=True`, and `production_writes_blocked=True`. These are conservative recovery constraints, not proof that an attempt actually happened. No raw paths, SID/UID values, bytes, native IDs, handles, or token are returned or included in repr/errors.

## Boundaries and shortcomings

- This is **not** a crash-durable commit, recovery executor, automatic replay, valid binding completion, permission for journal retirement, or a new Notes capability. It cannot prove what happened during a prior process's lifetime, especially across abrupt power loss.
- The new preflight is not asserted to persist across lock release. The inherited postcrash reader independently acquires and releases its own protected native scope. An advisory result expires after that scope; it cannot authorize a future write.
- The underlying native reader's accepted filesystem security boundary excludes uncooperative same-user writers, unsupported filesystems, OS administrators, unknown Windows share policy and cloud/network serialization.
- Native Windows/installed-wheel and strict mypy qualification must run through the guarded Windows runner; locally only dependency-substituted regression tests can be executed.
- The existing production write barrier remains unchanged and continues to prohibit every private production mutation.

## Regression coverage

75 isolated stubbed tests: complete native-result mapping, conservative no-retry/evidence/blocked invariants for all 22 return states, invalid step/revision/root inputs, canonical codec failures, owner/binding refusals, forged or relaxed production barrier, native return-type and state-type conflicts, native exceptions/interruptions, sanitized immutable responses, and absent production mutation calls.

The runner validates the exact 3G46 feature commit, main ref, inherited Git blobs and clean checkout; Ruff-formats only additive Python files off-checkout and verifies AST identity; runs the direct suite, expanded focused Core #238 suite, repository Ruff and strict mypy; then commits and pushes the exact three-file scope only on success. The full Core checkpoint remains at qualified 3G40: 6,864 passed / 179 skipped.

## Next production-critical gate

Design and qualify an actual atomic **journal + registry + descriptor durability protocol**, including verified parent-directory persistence, power-loss/interruption fault matrix, evidence-preserving recovery completion, and journal retirement order. Keep private Notes activation blocked pending D2 installed-wheel and native-platform proofs. A separate read-only report must never substitute for those gates.
