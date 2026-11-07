# Core #238 — Slice 3G45: sealed native pre-attempt boundary

**Feature baseline:** `724e36bc9585474666326ef1b8819f1719bed7c4` (qualified 3G44).
**Main baseline:** `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`.
**Safety claim:** Read-only validation of the actual prepared production transaction under one live one-shot native retained-handle scope; **no write permission**.

## Concrete integration

The 3G43 integrated admission reader previously used the 3G42 immutable native registry/stage review scope. Slice 3G44 introduced the distinct, single-use transition-aware handle lifetime required by an eventual replacement. Slice 3G45 binds those components: one protected ordered-lock/journal/descriptor scope contains one 3G44 one-shot native pair; four full canonical image frames and their native pre/post checks are performed before that pair and the outer guard release.

Admission must revalidate the original canonical intent, revision, effective local OS principal, exact workspace association binding, private-root protection, original registry and staged after-image identities, pending namespace, native parent continuity, registry/journal/descriptor/stage bytes, and expected recovery checkpoint. A final **in-scope** production write-barrier call must still return `PRODUCTION_BLOCKED` with the canonical, unchanged required-evidence list. The one-shot marker must remain unset throughout. Neither the marker nor any native handle is returned from the function.

## Failure and interruption semantics

- Invalid operation, revision, codec, owner, binding or path is refused before or during custody. No fallback to inferred identity or empty storage.
- Namespace, stage, registry, descriptor, parent, canonical-description or byte-image drift is refused. Pending journal and stage are left for recovery review.
- The stage is never renamed; there is no `os.replace`, unlink, write, fsync, journal retirement, replay, migration or Notes functionality in this source module.
- Guard release and one-shot native-handle failures override an otherwise positive observation. A positive post-return review is **expired**, not a capability for a later native operation.
- Interrupted or ambiguous cases are non-retryable without fresh guarded restart analysis. The original production write barrier still has no positive state and is not modified by this slice.

## Qualification evidence and outstanding gates

Local isolated dependency-stub regression: **45 passed** (not native filesystem qualification). Tests exercise four-frame/nine-check held ordering, exact namespace and preflight refusal, bad revisions, identity/image drift, guard-release failure, final barrier change, marker non-disclosure and absence of production calls.

The guarded Windows qualification runner checks the exact 3G44 commit, feature/main remote state, 238 inherited Git blob IDs, three additive files, Ruff formatting/lint, 97-file focused issue suite and strict mypy. Only upon all-green qualification may it commit and push. Full-Core checkpoint last passed at 3G40 (6,864 passed, 179 skipped) and is intentionally deferred for this incremental slice.

**Still unqualified:** production-native replacement execution with interrupt-safe classification, registry+descriptor durable commit ordering across native Windows/Linux, journal retirement, restart recovery, installed-wheel security proof, cross-platform proof (including unqualified macOS), CI acceptance and downstream #239 handoff. No `notes.records.v1` or other Notes capability is advertised. This is not production storage authorization.
