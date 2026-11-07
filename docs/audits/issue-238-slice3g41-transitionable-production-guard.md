# Core #238 — Slice 3G41: transitionable private journal/descriptor guard

**Qualified development baseline (3G40):** `047b8d36beb046170de8988373df179f11ed1124` on `238-establish-private-teacher-workspace-storage`; protected `main` at `a0d5e1a50580bbe025f0cad23c7e8524203a52ec` at preparation.

## Problem and bounded resolution

3G38 established four matching read-only native pre-replacement frames under the existing `retained._hold_existing_retained_descriptor_guard`. That guard nests the read-only retained-registry guard. Its **exit contract requires the original `registry.json` file identity** to remain unchanged. A legitimate future stage-to-registry replacement necessarily changes that identity. Accordingly, the old guard cannot be repurposed as a production writer guard by simply inserting `os.replace` within its scope.

3G41 introduces a **different internal, no-write composition**:

1. `journal_guard._hold_existing_retained_journal_guard`: local registry/workspace locks in mandatory order, retained journal-directory identity and protection, and native owner checks.
2. `retained._held_linux_descriptor` or `_held_windows_descriptor`: held workspace `.pds` and association-descriptor protection and native identity, without the old registry-handle release assertion.
3. `custody._held_stage` inside the same continuous guarded observation, with four native preimage frames, strict owner/native-protection and canonical transaction-image checks.
4. `window._frame_state` is reused for exact registry/stage separation, immutable expected bytes, canonical hashes and native timestamp/identity drift. All guard-release errors fail closed. A positive review is stale immediately after release.

The private `_hold_transitionable_journal_descriptor_guard` **yields only `None`**. It is not a writer-capability, `READY` status, callback/permit or file handle. Neither public nor private entry point opens a writable registry handle or invokes an OS mutation. The new result requires pending recovery evidence to remain.

## Security boundaries

- Existing private root is selected and verified through Core's native owner/protection probe, not actor/display context. Caller roots remain untrusted and never yield writable destination access.
- Only canonical **prepared** `STAGE_TO_REGISTRY` intent with matched preimage/stage/native namespace can produce the sanitized `transition_scope_observed_no_write` advisory result. Initialize, descriptor completion and journal retirement are rejected.
- Any unexpected registry/stage/journal/descriptor/parent/owner change, lock refusal, staged image drift, malformed intent or failed release stops the review. No implicit retry, repair, cleanup, association reset, or success claim.
- The new guard **does not** retain the old registry file handle by design; it is therefore **not sufficient alone** for production mutation. A future operation-owned writer needs phase-aware registry handle custody that admits only the exact old→staged-after-image native identity change and rejects every other transition; it must retain same-scope guard coverage across `os.replace`, recheck postimages, and establish durable persistence and post-crash reconciliation before any transaction may advance.
- `retained._hold_existing_retained_descriptor_guard` and all existing read-only reviewers remain unchanged. The new scope is not a weakening of those existing read-only checks.

## Verification and remaining gates

The additive test module covers invalid request types, disallowed steps, registry/stage ID drift, exact byte-image drift, missing pending namespace, native owner/protection and association mismatches, stage/guard release errors, interruption, transition guard ordering, owner changes during release, sanitized immutable outputs, and absence of filesystem mutation or authorization surface. Windows-native/full focused/Ruff/mypy qualification occurs in the guarded runner, not in this local audit.

The 3G40 full Core checkpoint was **6,864 passed / 179 skipped**. Full Core regression is not repeated in 3G41; focused regression and static gates are required. At this stage there is still **no actual production registry replacement**, no directory durability claim, no journal retirement, no Notes model/menu/CLI or released-consumer capability. Native macOS security remains unqualified.

**Next:** 3G42 should build the operation-owned **transition-aware registry handle** under this scope, initially with no mutation, then connect it to the prepared journal/stage evidence and a qualified native operation. Do not convert the 3G41 advisory finding into a writer permit.
