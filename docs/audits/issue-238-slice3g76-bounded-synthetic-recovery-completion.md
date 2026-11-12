# Core #238 — Slice 3G76: bounded synthetic recovery after hard process death

**Expected baseline:** `1541e3268db09033438b5cb2e4682a2b4bbac1af`, draft PR #247.

## Decision

3G75 qualified a killed writer and read-only restart observation. Advance from *observation* to a fixed, **scratch-only** recovery completion drill that determines the missing steps from independently verified canonical pending-journal state. The recovered operation may run one or two native same-directory replacements of module-created fake metadata, under continuously held cooperative lock and native parent/file custody. This is **not production replay**. It does not accept arbitrary user transactions, principal assertions, metadata, callback writers, or a caller-chosen phase; it never exposes handles or a positive permit.

## Native operation and restart boundaries

1. Build genuine canonical fixed synthetic `FORK_COPY` metadata and a pending journal in a fresh TemporaryDirectory; use 3G75's independently exited writer to leave prepared, registry-after/descriptor-before, or both-after checkpoints. 3G74's native-held restart checker verifies the state after the first process has died.
2. Launch a new isolated-wheel interpreter **without a recovery phase hint**. After reacquiring the cooperative lock, infer and independently re-infer the exact canonical images; retain native directory and available file handles for the full operation. Refuse conflicting journal, link, namespace, image or identity observations before any replacement.
3. Apply only the missing transition: prepared requires registry+descriptor once each; registry-only requires descriptor once; both-after requires zero writes. At each step use the previously qualified Windows native helper or Linux `os.replace`, require exact after-image and file-ID transfer, keep the original journal, flush the new file and attempt native parent flush. An unsupported Windows parent-directory flush is recorded as unqualified, not silently promoted to durability.
4. Release the recovery process's handles/lock. An **independent third interpreter** reacquires full custody and must classify `both_after_journal_pending_hold` in all cases. Nothing removes the journal; no committed or READY binding is returned.
5. For four separate post-death corruptions (journal bytes, namespace, descriptor bytes, staged bytes), recovery must refuse with **zero native steps**, retaining exact pre-refusal file images. Test injected native refusal at step one and after the first successful step; no fallback, reset, or automatic retry is permitted.

## Scope and verification

Add only a new scratch-only verifier, focused tests, this audit, and one new CI step/evidence artifact. Retain all seven earlier installed-wheel tests and full validation matrix. Guard exact branch/HEAD/remote/worktree/CI blob, archive member paths and SHA-256; qualify with focused pytest, Ruff, strict mypy Linux and Windows, isolated candidate wheel and eight installed native gates; only after local success commit/push. Require independent post-push CI on Windows and Ubuntu.

## Limitations

A synthetic canonical fixture cannot authorize mutation in an actual OS-private store. Advisory locks do not exclude noncooperating writers. Windows may refuse directory flush; successful requests on either OS do not prove power-loss survival. Native per-file replace is not two-document atomicity. A crash after a rename may have applied it; this harness never silently retries a failed step. The pending journal remains indefinitely in the drill; **production binding, automatic replay, journal retirement, transaction commit, Notes records/menu/CLI, and READY private-store handles remain disabled**.
