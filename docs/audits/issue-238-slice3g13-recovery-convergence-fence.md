# Core #238 — Slice 3G13: Independent Recovery Convergence Fence

**Scope:** New private/internal `_teacher_private_recovery_convergence_fence.py`; never exposed by the public teacher-experience API.

## Problem and new behavior

3G11 reports protected checkpoint classification, and 3G12 independently verifies exact native journal/registry/descriptor/stage images and expected registry revisions. A consumer must not infer a writable recovery step from either retrospective advisory finding alone, or assume that independent lock scopes form an atomic reservation. This slice performs both reviews, in order, twice, and refuses unqualified types, disagreement and inconsistent observations. It does not perform a write, replay, cleanup, persistence claim, or journal retirement.

The function validates the canonical intent, explicit operation and expected revision before any native review. It requires the 3G11 result `MATCHING_RETAINED_REVIEW_REQUIRED` **and** the matching operation-specific 3G12 exact-image result in each round. It returns an immutable, sanitized no-write status for prepared restart, descriptor-pending or journal-pending evidence. Every negative case preserves the pending artifacts.

## Security boundaries

- Each underlying call acquires **its own** complete retained journal/registry/descriptor guard. There is **no continuously held lock** across the four calls. This review must never be reinterpreted as CAS, a lease, a durable commit or authority to modify metadata.
- Double reviews cannot rule out ABA, hostile same-OS-user writes, shared-login collisions, power loss, or cross-device synchronization races.
- Exact bytes, owner identifiers, paths and the canonical journal are not returned, logged or included in messages or repr.
- Refuse initialization, invalid intents/revisions, unsupported platforms, malformed results, missing or changing images, interrupted reviews and any exception from a native reader.
- The existing Windows scratch native test remains isolated in a child interpreter, with **no change** to the production single-attempt rename helper.
- No `notes.records.v1`, `notes.menu.v1`, `notes.cli.v1` or `notes.portability.v1` capabilities. No Notes CRUD, journal deletion or workspace-binding activation.

## Qualification

Regression tests cover the three matching advisory states; request/intent/revision validation; unsupported OS; malformed returned evidence; independent disagreement, transient divergence, interruptions, and no private material exposure. The Windows guarded runner additionally checks exact committed 3G12 and `main` heads, blob pins, clean checkout, file hashes, Ruff preflight, focused pytest, Ruff lint/format, strict mypy and conditional exact-scope commit/push.

## Still required before mutation

A write protocol must own a *single continuously held* protected scope across its own preconditions, action, postcondition, and persistence barriers. Durable journal admission, conditional descriptor update, storage synchronization, fault-injected recovery, journal retirement protocol and D2–D4 integration all remain unqualified. **Do not promote this retrospective convergence review into an authorization API.**
