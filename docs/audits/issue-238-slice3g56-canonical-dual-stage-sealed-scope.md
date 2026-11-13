# Core #238 — Slice 3G56: Canonical dual-stage sealed native observation

## Authority and baseline

- Feature branch: `238-establish-private-teacher-workspace-storage`.
- Exact prerequisite feature HEAD: `75baf59736b2f10f82d2c7e123f8a0cf80bbd3c2` (qualified 3G55).
- Exact observed `main`: `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`.
- 3G54 checks the canonical protected pre-attempt/recovery *across separate native scopes*; those observations cannot be combined into write authority.
- 3G55 adds a native, read-only, transaction-specific workspace descriptor after-stage check, but does not combine its checks with the one-shot registry/stage native identity guard.

## Scope and disposition

This slice creates one internal-only, read-only native **dual-stage observation**. The existing transitionable journal/descriptor guard remains held while the existing one-shot registry/stage identity window and all three frame observations are performed. Each frame:

1. Rechecks the process owner, workspace binding, canonical transaction serialization, and unmarked one-shot registry/stage identity.
2. Checks the existing protected registry, journal, descriptor, and registry stage images and parent/file identity stamps against the first protected frame.
3. Verifies the pending prepared recovery classification.
4. Opens the *transaction-specific* workspace descriptor after-stage via 3G55's no-follow native reader and checks its exact canonical bytes and identity against the first observation.

The final production write barrier is rechecked **before** both native guards exit. No callback, mark-attempt operation, replacement, stage preparation, rename, deletion, retry, journal retirement, or Notes capability is implemented. No paths or native handles escape the guard. A matching observation is stale after release. Reopen-based stage comparisons cannot prove that no transient swap occurred between observations, especially on synced filesystems, and confer no security capability.

## Refusal matrix

Invalid input, non-`FORK_COPY` intent, revision mismatch, unsafe root, native owner/binding drift, failed guards, changed canonical bytes, attempted one-shot marker, registry/stage identity drift, conflicting journal/registry/descriptor frame, changed recovery checkpoint, missing/unsafe/changed descriptor stage or descriptor bytes, interruptions, and I/O failures all produce sanitized preserve-and-hold outcomes. Every return preserves pending evidence and explicitly forbids production mutation, replay and retirement.

## Security limitations and remaining work

- The existing production-write barrier remains explicitly blocked.
- This is an **observation**, not a complete operation-owned writer. It does not prepare or persist the descriptor stage, establish cross-device/cloud coordination, execute two native replacements, or guarantee atomicity or crash durability.
- Windows parent-flush requests remain `returned_unqualified`; there is no journal-retirement or Notes activation proof.
- Subsequent work must own the **whole** journal, both staged after-images, native protections, intent currentness, replacement transitions, postimages, independent recovery, and durability within a qualified transaction protocol. A no-write observation alone does not complete #238.
- No real student, teacher, or Notes data is used in test fixtures.

## Qualification gates

The guarded Windows runner checks exact branch/remote HEAD, 271 immutable inherited Git blob pins, and a clean tree; adds only the source, test and this audit; runs targeted adversarial tests, a native Windows fail-closed smoke test, a 108-file focused Core suite, Ruff and strict mypy. Commit/push is forbidden until all gates pass. The full-repository checkpoint remains deferred after the completed 3G40 full pass. Installed wheel/native production durability evidence remains unqualified.
