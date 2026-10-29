# Core #238 — Slice 3E4: guarded native transaction-intent image read

## Baseline and permitted scope

- Base: `83df19b695018311c9eca65600ca0432024489a3`, branch `238-establish-private-teacher-workspace-storage`.
- Reference `main`: `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`; runner refuses drift, including any remote branch advance.
- Files: this audit, `pds_core/_teacher_private_journal_image_snapshot.py`, and `tests/test_teacher_private_journal_image_snapshot.py`, all additive.
- Accepted D0 decisions in issue #238 remain controlling: the local effective OS principal is the only local-owner authority; a synced workspace descriptor is untrusted metadata; inspection must never initialize a private store.

## Motivation

Slice 3E2 classifies supplied exact registry/descriptor bytes. Slice 3E3 additionally classifies supplied canonical journal bytes. These pure classifiers deliberately cannot establish that their inputs came from protected native filesystem objects. The prior pending-journal scanner reports an empty/pending **census only**, without any bounded content image for recovery review. An isolated create-only journal primitive exists but cannot establish a durable transaction or permit replay.

Slice 3E4 adds a read-only, bounded **single named existing journal image** reader. Its positive outcome contains canonical bytes for future *private* recovery analysis, but is still advisory and never a commit, recovery or deletion token.

## Execution contract

The new internal `inspect_existing_private_transaction_image(private_root, workspace_root, transaction_id)`:

1. Validates exact supported platform, canonical UUIDv4 transaction name, canonical private-root path and workspace-root path *before* entering the filesystem guard.
2. Acquires the existing retained transaction-directory guard, which retains the two local coordination locks and native journal directory identity through entry, read and exit checks. No recursive locks are acquired.
3. Rechecks the expected transactions-directory location and the current native OS principal. A changed owner refuses the observation.
4. Reads only `<uuidv4>.json` through a native no-follow protected file handle. It never enumerates foreign paths, follows journal symlinks, creates a missing directory/file or alters existing bytes.
5. Limits file length to the v1 canonical intent maximum, double-checks native identity/protection, and validates exact canonical journal bytes and matching transaction ID/owner using the existing strict intent parser.
6. Exits the retained native journal guard *before* returning a result. A guard failure on exit supersedes an apparently successful image read.

Returned `PrivateJournalImageReview` is a frozen structure with sanitized `state` and `message`. The image field is excluded from `repr` and populated **only** for `OBSERVED_REVIEW_REQUIRED`; it is not exposed through any public teacher-experience API.

### Native Linux requirements

- Existing verified directory opened by the protected-parent primitive, then named file opened with `O_RDONLY | O_NOFOLLOW | O_CLOEXEC` relative to the directory descriptor.
- Current effective UID matches observed owner and file UID. File must be regular, exactly mode `0600`, single-link, on the same qualified local filesystem as the directory, without a conflicting effective ACL.
- The opened file and current name must have matching native identities. Size, mode, owner, link count, `mtime_ns` and `ctime_ns` remain stable across a bounded read. The native parent and current directory path must agree with their opened identity.
- Missing files are classified as missing observations, never as permission to create a journal.

### Native Windows requirements

- Current owner is a native token SID, and the transactions directory is on a qualified fixed local volume with verified non-reparse protected ancestry.
- Open a file handle with `GENERIC_READ | READ_CONTROL`, `FILE_SHARE_READ` only, `OPEN_EXISTING`, and `FILE_FLAG_OPEN_REPARSE_POINT`. No write/delete sharing is permitted while the read handle is held.
- Verify DACL, file type, single link, bounded size, FileIdInfo, and basic modification/change information; reread the retained handle and independently reopen the named entry for identity comparison. Verify directory ancestry again.
- Existing journal bytes are never repaired, removed, overwritten or redacted. Malformed/unqualified content remains on disk for further human review.

## Refusal and threat model

- Refuse invalid IDs, unsupported OS, owner mismatch/change, unqualified directory backing/protection, unprotected file, symlink/reparse entries, missing or changed native identity, I/O failure, noncanonical/oversized intent or a journal whose owner/transaction identity mismatches the named request.
- Refuse a guard-exit error even if image parsing succeeded inside the body.
- This reader **does not** prove disk flush durability, process crash consistency, absence of other journals, atomic cross-tree metadata updates, distributed lock coordination on synced workspaces, or exclusion of a hostile same-user process. Native file IDs and mtimes are supplemental evidence, not authentication secrets.
- A returned canonical image **cannot authorize** replay, journal retirement, metadata write, CAS reservation, owner association, Notes record access or synchronization. No `notes.records.v1` or other new public capability is advertised.
- The generic `.pds/workspace.json` remains untouched. Journal metadata contains no note bodies; the result `repr` and error strings do not contain owner names, private paths, transaction IDs or payloads.

## Qualification plan

- Isolated dependency-substitute harness under a non-root Linux account: 27 passed, 1 Windows-only test skipped. The harness specifically exercises real Linux native file access with temporary synthetic paths and controlled dependency substitutes. This is not native Windows qualification.
- Windows runner gates: source archive and baseline hashes; exact three-new-file worktree; focused private-storage regression tests, Ruff lint and formatting, strict mypy, full Core pytest, and staged diff hygiene. Automatic commit/push only after every gate passes.
- Windows native journal reader test is included in `test_teacher_private_journal_image_snapshot.py` and creates an ACL-protected synthetic intent via the previous create-only primitive, then reads the same bytes with the new native path.
- D2 installed-wheel and full source/native matrix remains **outstanding**; do not report this slice as installed or released.

## Next required boundaries

Guarded whole-store recovery must securely observe the *set* of pending journals, retain all relevant metadata handles, compare exact before/after images, and enforce explicit recovery/rollback choices. Durable journal admission and metadata CAS/writes require an independently reviewed transaction protocol including flush ordering, crash-point tests, and honest Windows/Linux filesystem limitations. No live Notes record writes are allowed in #238.
