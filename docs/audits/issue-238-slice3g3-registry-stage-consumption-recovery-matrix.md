# Core #238 — Slice 3G3: Registry-stage consumption crash-window matrix

**Base:** 3G2 `7ccb4e5548e55a025e8623138ff5d3228ddc378b`.

## Purpose and new coverage

The qualified 3G2 exclusive prepared-pair checkpoint requires an exact pending journal and an exact matching stage. It cannot describe the expected post-rename condition of a future replacement of `registry.json`: the staged after-image may have been **consumed** (the stage pathname is absent), while `registry.json` has after-image bytes, without yet having changed the workspace descriptor or retired the journal. Silently treating this absence as an empty workspace or as a corruption to repair destructively would be unsafe.

This slice introduces a *pure, non-authorizing* classifier that distinguishes stage-present from stage-absent outcomes across the existing canonical journal and exact-before/after registry/descriptor image matrix. Its inputs are **supplied bytes**, not proofs of protected native reads. An absent stage is represented as `None`; that value is not evidence that the filesystem truly lacked the entry. The existing 3E3 crash classifier remains the single authority for exact journal + metadata image classification. No new JSON schema, Notes capability, public storage service or filesystem write is introduced.

## Finite interruption states

| Registry image | Workspace descriptor image | Stage image | Outcome | Required later behavior |
| --- | --- | --- | --- | --- |
| Before | Before | Exact after | Prepared, review required | Verify journal durability, native owner/locks/targets, exact-before CAS; no permission conveyed |
| Before | Before | Missing | Refused | Preserve evidence; stage missing while before-state remains |
| After | Before | Missing | Registry after / descriptor pending | Review recovery; **do not** reset or claim committed |
| After | Before | Exact after | Registry after / stage remains | Review unexpected retention of stage; never delete automatically |
| Before | After | Exact after | Descriptor after / registry pending | Review out-of-order interruption, not ordinary success |
| Before | After | Missing | Refused | Preserve evidence; no stage for required registry transition |
| After | After | Missing | After-images, retirement review | Require independent durability, provenance and journal retirement protocol |
| After | After | Exact after | After-images / stage remains | Preserve extra stage pending review |
| Any | Any | Foreign/corrupt stage | Refused | Preserve evidence; no repair or overwrite |
| Foreign/corrupt metadata or journal | Any | Any | Refused | Preserve evidence; no new association |

For **REBIND_MOVE** the descriptor before/after image is intentionally identical; therefore only the registry distinguishes before from after. The classifier must not invent a descriptor-only interruption.

## Security constraints and follow-on work

- Every state is read-only/advisory. There are no write handles, cleanup, CAS reservations, durable-admission statuses, or automatic recovery instructions.
- Future native readers must independently prove protected journal presence, stage *presence or verified absence*, namespace exclusivity, effective OS owner, canonical exact bytes, handles, local backing, OS permissions and retained ordered locks **at the time of decision**. Supplied bytes are not authorization.
- The next native mutation implementation must not reuse the 3D7/3E0 *immutable* retained registry and descriptor guards as a write permit. Their successful exits explicitly reject changed registry identity; a mutation-aware scope is required.
- Linux: verify dirfd-based identity, before-image, hard-link count, nofollow, ACL/local backing and directory-fsync ordering for stage-to-registry replacement; separately attest failure windows and recovery.
- Windows: verify token SID, DACL, fixed local backing, file sharing/delete access, `ReplaceFileW`/equivalent crash semantics and post-operation handle identity. Do not assume atomic rename implies stable power-loss durability.
- Do not authorize initialization, a half-applied FORK_COPY descriptor, stale revision, journal retirement, first binding, or private Notes writes. No non-cooperating same-owner writer or cloud-sync guarantee is claimed.

## Qualification scope

Add exactly the private classifier, synthetic regression tests and this audit. Use a pinned clean 3G2 Git baseline, focused pytest, Ruff, strict mypy and a full Core pytest checkpoint before conditional commit/push. Existing installed-wheel preflight (SHA-256 `b465238315182882fd48c8c9531ccfe926843375a3b1f4e31d30cd11f5a8cb32`) passed in the prior checkpoint but **does not** qualify native metadata writes, end-to-end crash recovery, or Windows/Linux/macOS D2. Tests use synthetic identifiers only.
