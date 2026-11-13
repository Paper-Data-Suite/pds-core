# Core #238 — Slice 3D2: combined no-write journal pre-admission review

**Pinned source baseline:** `b09a9e256db98fde7705db2c55bc93148270669d` (completed Slice 3D1).
**Authority:** Owner-approved D0 policy under issue #238; `docs/teacher_private_storage_contract_v1.md` section 5.
**Status:** Internal advisory-only D1 guard composition; no journal creation, binding transaction, or Notes activation.

## Concrete gap addressed

Slice 3D0 rechecks the proposed registry/descriptor before-state under two local coordination locks, but does not observe pending intent journals. Slice 3D1 checks the protected journal directory under ordered locks, but is a separate operation; combining their **results after release** would introduce an uncontrolled interval. Slice 3D2 adds `pds_core._teacher_private_journal_admission_review.review_private_journal_admission_preconditions`, which performs both reviews within **one continuously held local registry-first/workspace-second lock set**.

The function accepts a canonical internal proposal, a previously qualified paired observation, the exact local-private-root candidate and an acceptable workspace root. It refuses malformed requests, unknown platforms and INITIALIZE before opening any lock. Initial binding still needs an independently qualified absence/review protocol; this slice does not infer an empty private collection.

## Ordered read-only sequence

1. Acquire the existing owner-private registry lock, then the existing workspace `.pds` coordination lock via Slice 3C9. Sample the effective native OS principal.
2. Scan the existing `transactions` directory through Slice 3D1's native guarded scanner; **any present entry, missing directory or uncertain protection aborts**. Never read the journal bodies, filenames into output or mutate them.
3. Perform registry/descriptor/descriptor/registry observations, through the established individual native readers, with both locks still held.
4. Scan the same transactions directory again, and resample the effective principal. A pending, altered or unqualified outcome aborts; a changed principal aborts.
5. Classify current metadata as a consistent pair, compare it with the earlier exact digests/revisions, and re-evaluate the proposed before-state and owner/path constraints using Slice 3C6.
6. Only after all checks pass, return `RECHECKED_JOURNAL_FREE_REVIEW_REQUIRED`. All locks are released in reverse order by the context manager. No success state is called READY, authorized, admitted, or committed.

State outputs are bounded, path-free, identifier-free and body-free. Refusals distinguish pending recovery, unsafe or missing journal directory, changed journal observations, stale/uncertain metadata, owner drift, invalid proposals and unavailable coordination. No new public import, mutation entry point, Notes feature token, menu or record interface is exposed.

## Security boundary: deliberately **not** admission

The two locks coordinate only cooperating **local processes**. A OneDrive/remote writer is not synchronized by them. The journal scans open/close directory handles independently; intervening same-user code, path replacement and ABA changes are not excluded even by two matching empty observations. A digest is not a durable CAS token. The current reader surface does not retain the complete native parent/file handle chain across the whole operation and does not validate registry membership as an authoritative binding. The caller's proposed intent is metadata, not evidence of teacher confirmation.

Therefore this function MUST NOT be called by a writer as sufficient permission to create an intent, replace a registry or sidecar, import Notes or claim recovery completeness. A future writer requires reviewed teacher authorization, safe held native handle continuity, verified existing registry member/accepted root (or explicit true-absence proof), exact-before revision/byte CAS, durable intent/journal placement and interrupted-commit reconciliation. The private registry remains local-user-only; syncing sidecars confer no owner privileges. Native Windows/Linux installed-wheel proof remains a separate D2 gate.

## Qualification plan

Additive files: the internal reviewer, its focused synthetic regressions and this audit. Tests assert one guard across both census calls and metadata reads; pending-before/pending-after rejection; mismatched metadata/previous observations; owner drift and lock refusal; initialization and unsupported-platform refusal; preservation of negative Notes capabilities and sanitized outputs. Runner verifies exact branch/origin/HEAD, pinned prior files, untouched worktree, three-file scope, source hashes and Git hygiene; it executes focused pytest, Ruff, strict mypy and complete pytest before conditional commit/push. Failure leaves working files intact for exact-state repair. No release or feature activation follows from this source slice.
