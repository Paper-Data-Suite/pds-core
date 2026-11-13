# Core #238 — Slice 3E2: pure exact-byte transaction recovery images

**Baseline:** `4b54ce53ea0f067730d523825cbc734dc6861d8c`, branch `238-establish-private-teacher-workspace-storage`.

**Implementation:** `pds_core/_teacher_private_exact_image_recovery.py`.

## Purpose and boundaries

Core already has versioned `PrivateTransactionIntent` carrying the exact before/after bytes of registry and workspace descriptor, and the transaction witness has SHA-256-based interruption classifications. Slices 3D5–3E1 established a read-only composite review under retained native journal, registry and workspace descriptor guards. No existing reviewer writes or authorizes a binding.

3E2 defines a **pure, exact-byte** recovery-image classification that a future guarded transaction/recovery service may use after it has reliably read both documents or independently proved absence. This narrows a semantic gap between hash-only evidence and the actual two-document images that must be recovered.

The classifier accepts only a validated, canonical transaction intent and caller-supplied `bytes | None` for each current document. It never accesses the filesystem. `None` models *independently proven absence*; it does not perform or certify that proof. Empty bytes are **not** absence. The helper refuses oversize, non-plain-byte and unrelated images, and revalidates the intent by round-trip serialization/decoding rather than trusting potentially tampered frozen fields.

## Content-state table

| Current registry image | Current workspace descriptor image | Outcome |
| --- | --- | --- |
| Exact before | Exact before | `BEFORE_IMAGES_REVIEW_REQUIRED` |
| Exact after | Exact before | `REGISTRY_ONLY_REVIEW_REQUIRED` |
| Exact before | Exact after | `DESCRIPTOR_ONLY_REVIEW_REQUIRED` |
| Exact after | Exact after | `AFTER_IMAGES_REVIEW_REQUIRED` |
| Other, missing when not expected, or conflict | Either | `FOREIGN_IMAGE_REFUSED` |
| Invalid observation type or oversized input | Either | `OBSERVATION_UNQUALIFIED` |
| Invalid or tampered intent | Either | `INTENT_REFUSED` |

For `REBIND_MOVE`, the descriptor before/after images are intentionally identical. Registry content determines before/after classification; the result must **not** infer that a distinct descriptor write occurred. Initialization supports absent prior images, but absence remains an external native verification responsibility. Digest collisions (however unlikely) do not yield false exact matches because the classifier compares bytes after canonical intent validation.

**Every state is non-authorizing.** Neither a before-state, a single-file after-state, nor a both-after state permits automatic rollback, roll-forward, journal removal, setup or Notes access. Foreign state requires preservation and explicit recovery review. The helper does not choose a recovery direction or expose an executable plan.

## Regression evidence

`tests/test_teacher_private_exact_image_recovery.py` exercises all four image combinations for `INITIALIZE` and `FORK_COPY`, both stable-content states for `REBIND_MOVE`, foreign concurrent changes on both documents for all three operations, empty-vs-missing differentiation, invalid/oversized current inputs, tampered intents, frozen/sanitized results, and absence of write capabilities. A dependency-substitute isolated harness passed 32 tests; this is **not** native or Core-integration qualification. The guarded Windows runner must execute targeted pytest, repository Ruff, strict mypy, full Core pytest and stage/remote hygiene before commit/push.

## Security and future handoff

- This helper has no handle/path arguments, no lock or OS-owner verification, and never opens or creates a file; it must not be invoked as a substitute for the triple-retained review from 3E1.
- Current two-document images must later be read under all existing protections. Their content classification and any eventual CAS mutation need uninterrupted native write-target continuity, recovery-journal durability, explicit teacher action, and serialized transitions. OS-user-local coordination is not distributed/OneDrive coordination.
- Future journal protocol must define prepare/fdatasync/atomic replacement/commit-or-recovery retention and tested crash boundaries before any write activation. Never treat `AFTER_IMAGES_REVIEW_REQUIRED` as permission to delete a journal.
- No public Notes capabilities, release version, authentication surface, real Notes records, menu, or CLI are added here. `get_teacher_experience_capabilities()` remains unchanged.
- D2 native installed-wheel qualification, macOS decision and cross-process adversarial recovery tests remain outstanding on #238.
