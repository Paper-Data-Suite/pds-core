# Core #238 — Slice 3G83: existing two-root native operation-scope review

**Baseline:** `28b5848008447f8596c6b97bc41a9c89a20fb7b2`, draft PR #247. **Candidate version:** `0.6.6` (no release).

## Decision

3G82 joined independent read-only precondition observations; it did **not** retain a common operation scope. Core already has an existing ordered private-registry/workspace lock and a retained native descriptor/registry/journal guard used by synthetic and recovery precondition reviews. 3G83 connects those existing internal guards to an explicitly non-authorizing, read-only two-root assessment. It neither invents a new lock protocol nor exposes a handle or permission token.

The caller may supply **only** an existing workspace-root candidate. Core obtains the exact user-local private root and the effective OS identity itself. It rejects a missing/unsafe root, missing lock or descriptor, native identity drift, absent/unsafe private DACL, and changed descriptor observations. No path, SID/UID, descriptor ID or bytes, native handle, callback, or authority leaves the function. A positive scoped observation is `guarded_observed_production_blocked`, *not* ready, writer admission or ownership binding.

## Operation sequence (read only)

1. Verify all nine production requirements match the unchanged barrier taxonomy before native probing.
2. Verify the 3G82 non-authorizing precondition review and derive the private root and current OS owner from Core's own inspection.
3. Enter existing `_hold_existing_retained_descriptor_guard`, which nests the ordered **existing** private registry/workspace locks with native retained registry, journal and descriptor handles. No missing lock is created or repaired.
4. **Inside the held scope** verify owner/private root again, perform retained native private-root custody, inspect the existing descriptor twice, and recheck owner/root before releasing the guard. Refuse all missing, mismatched, changed or malformed observations.
5. Exit the guard, release handles/locks, and return only sanitized state and two non-sensitive enum labels. Do not pass a held handle or a stale post-release approval to a writer.

## Acceptance

Tests cover a positive-looking guarded fixture that is still blocked, actual in-scope call ordering, root/owner drift, descriptor drift, native custody refusal, missing private root, guard refusal and requirement drift. No production file or private root is created by tests. The installed wheel verifier rejects an invalid workspace without touching the actual current user's private root, checks all nine blockers, and ensures no scratch writes or private information in the report.

Both Linux and Windows CI must retain all fourteen previous installed-wheel gates and add a fifteenth non-authorizing native boundary gate, with strict platform mypy, Ruff and focused pytest.

## Explicit limitations

A cooperating local lock does not exclude a malicious or noncooperating writer. A sync provider may modify the workspace independently. Read-only checking cannot establish an atomic registry/descriptor CAS, crash/power-loss directory durability, journal retirement, native sharing/exclusive semantics, replay, production binding or Notes records. All nine production requirements **remain unqualified**. No production write authority is introduced by 3G83.

## Next

3G84 should qualify exact owner/registry/descriptor/journal association and canonical intent *inside* the current retained native scope, including negative preimage and drift cases, still without granting mutation authority.

## Slice 3G83 Repair 1 — strict mypy event-mock correction

The stopped local run passed 176 focused tests (11 skipped) and Ruff; strict Linux mypy rejected the test-only expression `history.append("native") or state` because list.append returns None. The mock now appends the event in a typed function and returns the same retained-root enum explicitly. The two-root production scope, verifier, CI workflow, and all fifteen installed-wheel gates remain unchanged. No production write authority is introduced.
