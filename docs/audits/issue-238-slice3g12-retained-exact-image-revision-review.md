# Core #238 — Slice 3G12: Retained exact-image and expected-revision recovery review

## Baseline and limits

Baseline feature commit: `213b8007fe03cf24275bc50602477ba1eac92dd1` (3G11). This slice is internal, read-only and additive: one implementation, one test module, and this audit. No public teacher-private Notes service, binding, CAS reservation, journal retirement, recovery writer, or durability guarantee.

## Narrow capability

`review_retained_private_recovery_exact_revision()` accepts one canonical non-initializing transaction intent, a typed recovery **review** step, an exact expected registry revision, and existing qualified private/workspace roots. It rejects invalid requests before acquiring any native guard. It derives expected before/after revisions and exact images from the validated transaction intent. It requires the after-revision to be exactly the before-revision plus one.

Inside **one retained native descriptor/journal/registry scope**, the review repeats native journal, registry, descriptor and (for a stage-present proposal) stage byte-image reads twice, checking pre-/post-read namespace, inventory, and effective OS owner continuity. It requires exact byte equality with the transaction intent, matching pending-journal bytes, and the caller's exact expected registry revision. The result contains only a sanitized enumeration and message; it never exposes owner or byte images.

Three positive states are **review required**, not permission to act:

1. Staged pending journal, matching registry/descriptor before-images, matching registry stage after-image, and expected before revision.
2. Stage absent, registry after-image, descriptor before-image, and expected after revision (descriptor completion review).
3. Stage absent, registry and descriptor after-images, and expected after revision (journal retirement *review* only).

Every other state refuses or preserves evidence: revision mismatch, missing/corrupt/conflicting native image, changed images across reads, changing stage namespace/inventory/owner, invalid request, unsupported platform, native guard failure, interruption, and I/O failure. A failed native guard postcondition overrides a provisional match.

## Security restrictions and residual risk

- No write, callback, deletion, stage consumption, journal retirement, lease or reusable action token.
- Native image helpers are invoked **inside the existing guard**, not via nested lock-acquiring public readers.
- Native readers independently qualify protected local backing, ownership and file identity. Namespace census still cannot defeat a hostile same-OS-user writer that ignores locks; it does not claim a distributed or durable CAS.
- Two exact read passes prove only observed equality during one local review, never crash/power-loss persistence, atomic pairing of registry and descriptor, or a durable journal commit.
- Untrusted workspace hints, sync/cloud paths, unsupported filesystems and first-bind initialization retain separate fail-closed protocols.
- No teacher-private student data, private paths or owner IDs are included in exceptions or returned status. No Notes records, commands, menu or service are enabled.

## Qualification

Source ZIP: exact 3-file additive scope, SHA-256 manifest, Python AST and off-checkout Ruff preflight. Isolated synthetic test harness: 59 passing cases; platform-native and full Core qualification delegated to guarded Windows runner. Runner verifies the exact feature/main heads, inherited 3G11 blob pins and clean checkout, formats AST-equivalently, runs new tests, 64-file focused Core suite, Ruff and strict mypy, and conditionally commits/pushes only on success. Full Core integration checkpoint is periodic, last passed in Slice 3G10 (4,696 passed, 174 skipped).
