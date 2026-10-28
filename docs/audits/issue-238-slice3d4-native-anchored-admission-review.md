# Core #238 — Slice 3D4: combined native-anchor admission review

**Pinned baseline:** `7edd683a2c2d5a8a0c97597fafd6a3809f862533` (completed Slice 3D3).
**Authority:** approved D0 design, `docs/teacher_private_storage_contract_v1.md` §5.
**Status:** Internal, read-only, strictly non-authorizing observation.

## Additive integration

`_teacher_private_native_admission_review.review_native_anchored_private_journal_preconditions` combines three previously separate advisory primitives in a **single local lock scope**: ordered registry-then-workspace coordination (3C9), a double pending-journal census and paired metadata review (3D2), and two native identity observations of the transaction directory (3D3).

After input/operation/prior checks, the operation acquires both pre-existing locks. It obtains the native effective OS owner, checks the journal-directory native identity, scans transaction-directory entries, reads the private registry and workspace descriptor twice, rescans entries, repeats the native directory-identity check, and rechecks owner identity. Only then does it compare the prior observation and the proposed transaction's exact-before metadata preconditions. Refusal categories are bounded and do not expose SID, UID, paths, UUIDs, hashes or metadata content. Any observed pending entry blocks advancement and requires independent recovery review. Neither notes nor association documents are created or altered.

The strongest result, `RECHECKED_NATIVE_ANCHOR_REVIEW_REQUIRED`, states only that *the separate local observations agreed in this lock scope*. Unlike a writer, this helper returns no native handle or write authority. It **never creates a journal, admits a transaction, commits a descriptor/registry, or publishes a READY private scope**. Initialize remains explicitly refused pending a separate missing-state protocol. There is no public dispatch or capability activation.

## Deliberate security limits

The 3D3 native probe closes its handles on return. Two successful probes therefore **do not prove one continuous inode/FileId identity across the entire review**; this helper makes no such claim. The POSIX/Linux directory-fd walk and Windows FileIdInfo/DACL checks only establish bounded native observations. The double census is not atomic against an uncooperative same-user process. Nor can a lock file in a cloud-synchronized workspace coordinate remote devices, including OneDrive. The result is not a CAS reservation or a security token. Do not use this result as a precondition bypass for any future journal or registry writer.

Actual transaction admission requires retained verified native handles across the entire operation; revalidated OS effective owner and local filesystem protection; exact owner-registry member and descriptor before-bytes/revisions; collision and root-identity checks; reviewed teacher intent and confirmation; durable protected journal creation with flush and independently checked pending state; guarded CAS of both documents with crash-consistent recovery; and explicit post-commit qualification. Every one of those conditions must be independently enforced by the future writer. No Notes records, `notes.records.v1`, `notes.menu.v1`, `notes.cli.v1`, or portability capability are introduced by #238.

## Regression evidence / boundaries

Synthetic regressions cover first/last native anchor failures, first/last pending journal scans, paired metadata drift, stale prior evidence, precondition mismatch, OS-owner changes, local lock refusal, initialization refusal, unsupported/invalid requests, sanitized outcomes, and the exact ordered sequence with reverse lock release. This is **source-level** evidence only. Full Core pytest, Ruff, strict mypy and native Windows qualification must pass in the guarded runner before commit; installed-wheel and multi-device behavior are not qualified by this slice.
