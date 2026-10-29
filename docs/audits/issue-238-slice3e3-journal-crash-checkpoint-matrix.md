# Core #238 — Slice 3E3: canonical journal crash-checkpoint matrix

**Baseline:** `59949b1edc372a376a69a90088829fd181509726` on branch `238-establish-private-teacher-workspace-storage`. `main` baseline: `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`.

## Objective and scope

Add a **pure, internal, non-authorizing** classifier pairing one canonical transaction intent/journal image with the exact before/after registry and workspace descriptor images from Slice 3E2. It performs **no filesystem I/O**, creates no journal or metadata, holds no locks, and does not enable a binding or Notes service. The supplied journal image is an *alleged* observation, not proof that a real file exists, has restrictive protection, or has reached durable storage. The classifier does not perform authenticated authorization or human approval.

## Candidate sequence for a later, independently qualified writer

1. Obtain explicit teacher-reviewed operation and validate the canonical `PrivateTransactionIntent`, effective owner and workspace binding under both ordered locks and all relevant native path/file guards; require an empty, qualified pending-journal census and exact-before CAS of both documents. **No write yet.**
2. Create the uniquely named protected journal intent using exclusive file creation, exact canonical bytes, verified owner/protection/identity, flush journal contents, and flush its containing directory (with explicitly evaluated Windows durability semantics). The journal must be durably admitted **before either metadata write**. The existing isolated provisioning helper does not by itself prove the entire sequence.
3. For operations that actually change the workspace descriptor, perform a protected, no-clobber or guarded replacement with independently justified overwrite authority, bounded exact-before checks, and durable flushes. `REBIND_MOVE` may leave descriptor bytes unchanged; this must not be reported as a descriptor write.
4. Apply the private registry revision only after revalidating the exact-before state, effective owner and guards and proving protected write-target continuity. Use durable, crash-recoverable replacement; do not bypass existing file-sharing limits with an unsafe `FILE_SHARE_WRITE` change.
5. Reinspect both files under qualified coordination, validate after-state and the still-present journal, and record a separate reviewed recovery/finalization decision. Journal retirement must itself be atomic/durable and never inferred from an after-image alone.

**This is a proposed ordering contract, not an implemented transaction engine.** Retained observational read handles may conflict with actual writers, particularly on Windows. Release/reopen/recheck or alternate native handle strategies must be resolved in a later slice without exposing a race or weakening DACL/reparse checks. Cloud-synced workspace changes are not serialized across machines by local file locks.

## Pure checkpoint matrix

| Alleged exact journal bytes | Observed metadata images | Classification | Automatic action |
| --- | --- | --- | --- |
| None | Both match before | No-journal before, review required | None |
| Canonical intent bytes | Both match before | Journal before, review required | None |
| Canonical intent bytes | Descriptor after, registry before | Descriptor-only, review required | None |
| Canonical intent bytes | Registry after, descriptor before | Registry-only, review required | None |
| Canonical intent bytes | Both match after | Journal after, completion review required | None |
| None | One document matches after, the other before | Unjournaled partial, refused | None |
| None | Both match after | Unjournaled after, refused | None |
| Unexpected, truncated, mismatching or noncanonical journal | Any | Journal image refused / observation unqualified | None |
| Any | Foreign, oversized or otherwise unqualified metadata image | Foreign metadata refused / observation unqualified | None |
| Any | Invalid or modified `PrivateTransactionIntent` | Intent refused | None |

`REBIND_MOVE` legally has identical before/after descriptor bytes; its registry image determines the before/after content distinction. An absent descriptor or registry is represented by `None` **only as supplied evidence**; `b""` is never silently promoted to absence. Observed canonical bytes are still not proof of a durable journal or protected read.

## Fail-closed and privacy contract

- No returned status indicates `ready`, `authorized`, committed, recovered or safe-to-write; results contain only a sanitized enum and static message, not UUIDs, paths, bytes, owner SID/UID, file IDs, or handles.
- Validation re-encodes and decodes the proposed intent; journal content must match those exact canonical bytes, not merely hashes, a transaction ID, semantic equivalence, or a parsed foreign record.
- No cleanup, rollback, replay, journal retirement, disk reads, or writes are possible through this classifier.
- Reconciliation in a later native writer needs a specific validated journal entry, actual protected current-file reads, atomicity/durability evidence, and explicit authorization. A stale or ambiguous journal blocks a new transaction.
- No `notes.records.v1`, `notes.cli.v1`, `notes.menu.v1`, or Notes data access is introduced.

## Qualification and limits

Isolated dependency-substitute harness: 52 tests passed, including all operation/checkpoint combinations, tampered journal bytes and invalid image refusals. This is **not** native Windows, real filesystem durability, installed-wheel or release qualification. The guarded Windows runner must independently execute focused pytest, Ruff, strict mypy, full Core pytest and Git hygiene before conditional commit/push. Native macOS support remains unqualified. No changes to existing module interfaces, `workspace.py`, or the generic `.pds/workspace.json` marker.

**D2, writer and recovery gates remain open.** This slice alone must not be used to conclude Core #238 is fully delivered.
