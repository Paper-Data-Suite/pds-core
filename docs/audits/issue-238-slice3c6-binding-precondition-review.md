# Core #238 — Slice 3C6: Pure proposed-binding precondition review

**Pinned baseline:** `bbe2a2ea596010f9df89b473e19bccbeac60ca58` (Slice 3C5).
**Authority:** D0 approved decisions and `docs/teacher_private_storage_contract_v1.md`.
**Scope:** One new internal pure evaluation module; tests; this audit. No production files changed.

## Purpose and data flow

Slice 3C5 separately reads private registry and workspace descriptor twice while the existing private coordination lock is held. The resulting paired observation is deliberately non-atomic across local private storage and a potentially synced workspace. Slice 3C6 adds `review_binding_preconditions(proposed, observed, workspace_root, owner_observation)` to compare that observation to a validated proposed transaction's **before**-state. The inputs are ordinary data supplied by a caller: this function performs **no** filesystem or OS API calls, acquires no locks, and does not independently authenticate the owner or ensure metadata currentness.

The evaluator revalidates the canonical proposed transaction envelope and its nested descriptor/registry bytes, then checks these bounded conditions:

- Only `OBSERVED_UNQUALIFIED` paired observations are considered for existing-descriptor transitions. Every other observation result fails closed.
- The alleged effective-OS owner kind and value must match the owner in the before/after private registry. This is a comparison, **not** a fresh token SID/effective-UID observation.
- The registry revision, exact SHA-256 before-digest and binding count must agree with the earlier paired registry observation.
- The descriptor UUID and exact before-digest must agree with the earlier paired descriptor observation.
- The proposed new binding's accepted workspace root must match the exact requested absolute workspace root, without case/alias normalization or symlink resolution. A rebind's prior accepted root must be different from that destination.
- An `INITIALIZE` proposal returns `MISSING_STATE_REVIEW_REQUIRED`: the existing paired snapshot does not provide a complete proof that absent metadata can be created without replacing an existing association.

A successful comparison is **`MATCHED_REVIEW_REQUIRED`**, not READY, APPROVED, CAS-SAFE, or authorization to persist. This does not infer the private Notes collection associated with the UUID. The result exposes no private path, owner principal, registry contents, transaction token or writable handle.

## Refusal categories

`INVALID_REQUEST` rejects wrong input classes or an unsafe/relative workspace request. `INTENT_REFUSED` rejects noncanonical or invalid proposed metadata. `OBSERVATION_UNQUALIFIED` rejects missing/inconsistent/unsafe observation states. `OWNER_MISMATCH`, `REGISTRY_STALE`, `DESCRIPTOR_STALE`, and `WORKSPACE_MISMATCH` preserve the relevant separate failure modes without disclosing metadata values. `MISSING_STATE_REVIEW_REQUIRED` applies to initialization, even if the paired observation reports a missing descriptor.

## Critical limitations and later gates

This pure evaluator **does not establish a durable cross-tree snapshot** and cannot detect edits occurring after the preceding paired observation. Supplied `owner_observation` may itself be stale or fabricated; no caller may treat it as current native proof. Neither a matching UUID nor a matching SHA-256 authenticates a teacher identity. Cloud sync, volume remounts, Windows reparse points, file replacement, root aliases and concurrent non-cooperating processes still require native handle-based requalification. A real writer must acquire and hold the final agreed lock set, independently reopen and verify both documents and current token identity, enforce exact CAS revisions and content, ensure reviewed move/copy/initialization intent, durably persist a protected journal, then use guarded atomic replacement and conservative recovery before acknowledging any binding.

No `notes.records.v1`, public Notes API, tenant switch, repair service or automatic migration is introduced.

## Verification

`tests/test_teacher_private_binding_preconditions.py` covers fork-copy and move proposals; exact before-digests, revision, binding count and UUID; owner-kind and value mismatch; exact destination; invalid inputs; every non-success paired-observation classification; missing initialization; and noncanonical raw-registry proposals. The isolated local suite passes **24 tests**. Native Windows full regression, Ruff and strict mypy are mandatory on the user checkout and are **not** claimed from the local execution.
