# Core #238 Slice 3F5 — Retained journal and registry-stage checkpoint review

## Scope and authority

This slice adds `pds_core/_teacher_private_retained_stage_checkpoint_review.py` and synthetic tests. It is a private, non-authorizing, **read-only** review of one proposed non-initialization transaction. It does not implement durable journal admission, registry staging/rename, metadata CAS, binding commits, recovery replay, cleanup, Notes CRUD, or any public `READY` capability. No existing production module changes.

**Pinned source baseline:** qualified 3F4 feature HEAD `7d2811922343c3635afd3c66ab7c32ecf5270cc8`, with GitHub main `a0d5e1a50580bbe025f0cad23c7e8524203a52ec` at construction. The runner must reject drift.

## Native observation protocol

1. Validate the canonical proposed intent by bounded encode/decode and compare the round-trip. Exclude first-time initialization: that requires a distinct missing-file and creation protocol.
2. Acquire the existing triple-retained descriptor guard (local ordered locks, private registry/journal anchors, workspace descriptor anchors). No nested public functions that would reacquire locks.
3. Obtain OS owner, stage inventory, named journal, protected registry, workspace descriptor, and one named registry stage. Reject missing, unqualified, foreign-owner or improperly protected images, and require stage inventory to report pending artifacts.
4. Read the named stage, descriptor, registry and journal again, then repeat the inventory. Reject changes in any exact byte image, inventory refusals, and native-owner changes.
5. Require the observed stage's canonical exact bytes to equal the proposed registry after-image. Pass the *native-observed* journal and metadata images to the existing pure crash-checkpoint classifier. Classify the journaled before state separately from other journaled states. All outcomes require independent human/transaction recovery review.
6. Retained guard exit verification overrides a successful in-body classification. Return only bounded, sanitized states/messages, no file handle, path, raw content, principal, transaction ID or write token.

## Security limits

- The stage inventory's `STAGES_PRESENT_RECOVERY_REQUIRED` means **one or more** stages exist. It cannot prove this transaction owns the entire staging namespace or that no unrelated orphan stage is present. No transaction-wide exclusive stage census is established here.
- Repeated reads and retained local handles do not establish file-system-wide atomicity, flush/namespace durability, exclusion of hostile same-user or cloud-sync writers, or a distributed compare-and-swap protocol.
- The native readers remain observational. No automatic replay or deletion of a possibly incomplete journal or stage. No different-owner or shared-OS-login isolation claims beyond the existing native boundary.
- The resulting checkpoint state never authorizes changing `registry.json` or the workspace descriptor, even when the before-images and proposed after-image agree.
- All tests use synthetic data and mocked native reader/guard boundaries. Actual Windows, mypy and full Core gates are required by the guarded runner; passing mocks alone does not establish OS-level end-to-end security.

## Regression tests

The new tests verify the symmetric ten-step native sequence, all four journaled checkpoint classifications and classifier refusals, mismatched staged after-bytes, drift in each of four images, native-reader refusal/owner errors, stage inventory refusals before and after reads, owner drift, retained-guard entry and exit refusal, invalid/initialization requests, unsupported OS, sanitized outcomes, no file changes, and unchanged published teacher-experience capabilities.

## Later gates

Before any metadata replacement: demonstrate a complete journal durability/admission protocol; qualified exact-before registry **write-target** continuity and compare-and-swap; exclusive inventory of all journal and staging candidates; controlled namespace replacement and secure flush on supported platforms; workspace descriptor write-target rules; recoverable crash permutations between all writes; native Windows/Linux fault injection and acceptance; and a reviewed #239 service handoff. This slice is not a substitute for any of them.
