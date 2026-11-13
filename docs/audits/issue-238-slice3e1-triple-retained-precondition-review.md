# Core #238 — Slice 3E1: journal/metadata review under three retained native guards

**Status:** non-authorizing, read-only internal integration. **Baseline:** `aeb6b0a9043a6855d33b25a88b89cd4e6eba5948` (Slice 3E0). **Scope:** three additive files; no public API/capability change.

## What this changes

`_teacher_private_retained_descriptor_admission_review.review_retained_descriptor_journal_preconditions()` performs an advisory transaction precondition review inside **one** `_hold_existing_retained_descriptor_guard` scope. That guard nests the protected registry lock, workspace association lock, retained private transactions-directory handle, retained private `registry.json` handle, and retained workspace `.pds` directory and association-descriptor handles. The reviewer does **not** recursively reacquire either lock.

In this scope the reviewer observes the pending-intent census twice and reads both registry/descriptor metadata twice (in reverse order), then checks OS principal continuity, paired metadata equality to the prior observation, and the proposal's canonical preconditions. `INITIALIZE` remains outside this path: absence needs separately qualified checks. Pending journals require recovery review. Every outcome contains only a sanitized state and message, never paths, owner IDs, UUIDs, bytes, handles, file IDs, or commit authority.

The **strongest** result is `RECHECKED_RETAINED_DESCRIPTOR_REVIEW_REQUIRED`, which does not authorize any storage mutation. A guard failure during context-manager exit overrides even a formerly matching review result. The underlying guards close handles and release locks on normal and exceptional exit.

## Verified by regression tests

- Exact read order and retained guard scope; no recursive lock acquisition or filesystem creation.
- Pending journal, missing or unsafe journal and changed journal census refusals.
- Changed registry observation, stale prior observation, mismatched canonical transaction preconditions, effective-owner drift.
- Entry failures for missing descriptor, changed owner, unavailable owner, unsupported protection.
- Exit failures for path replacement, nested registry/journal guard refusal, unsafe native path and I/O; a matched precondition result must be discarded.
- `INITIALIZE`, invalid inputs and unsupported platforms do not enter the guard; no Notes or write-capability tokens.

## Security limits and remaining work

Native handles are read-only and their lifetime stops when this function returns. Same-owner in-place modifications and cross-machine synchronization are not made atomic by locks or repeated observations; a cloud-synced `.pds` path is **not** a globally serialized authority. The owner-private registry remains authoritative, not the descriptor UUID. These tests do not prove durable compare-and-swap, a write target bound to the verified handles, crash-safe journal admission, recovery replay, explicit teacher approval, or binding commit. Future writes require those independent gates and must fail closed on unknown local filesystem semantics.

No Notes records, writable handles, journal admission, binding mutation, user-facing CLI, or new `get_teacher_experience_capabilities()` values are introduced.
