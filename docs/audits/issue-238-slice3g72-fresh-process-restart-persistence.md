# Core #238 — Slice 3G72: installed-wheel fresh-process restart and persistence-request evidence

## Exact baseline and scope

- Exact base: `fd3fe8f11aa63320644ac3eb03b3263872dba578` (3G71 Repair 1), draft PR #247. Run 43128213041 passed **15/15**, including native installed two-document synthetic checkpoints on Ubuntu and Windows.
- Add `scripts/verify_issue238_installed_separate_process_restart.py`, `tests/test_teacher_private_installed_fresh_process_restart_3g72.py`, this audit and an additional step/artifact in the existing native installed-wheel CI job. Existing Core production files, installed gates, Notes capability, and release are unchanged.
- The new test harness imports the **already qualified 3G71 source test harness** for its exclusively owned synthetic files and calls genuine internal installed-Core helpers from a fresh wheel. It neither changes 3G71's semantics nor passes its result as a permission to write private data.

## Operations and checkpoints

- Three distinct disposable, canonical `FORK_COPY` cases: both stages prepared, registry-after/descriptor-before, and both metadata after-images with journal pending. For each case, 3G71 performs native one-shot replacement and independently reopens the actual images and retained file identities.
- After releasing native handles, request `fsync`/`FlushFileBuffers` on the scratch metadata files and separate parent-directory flush requests using Core's already existing 3G48 module. Linux parent-directory refusal is a gate failure; Windows directory-flush refusal is **reported as unsupported, not silently upgraded to a pass or durability claim**.
- Invoke a separate `python -I` **interpreter** from the installed wheel environment to independently verify exact canonical journal bytes, expected descriptor and registry images, complete allowed namespaces, link-free directory entries, distinct native file identities and the still-blocked production admission. The interpreter opens no output report and performs no replay, retry, stage mutation or retirement.
- All files are generated in a new `TemporaryDirectory` from hardcoded synthetic metadata. The read-only process accepts only that disposable scratch subtree. It cannot open caller-supplied teacher paths or produce a production access token. The parent validates the child's exact fixed success label and refuses any contradiction.
- Regression tests deliberately corrupt the journal and create an unexpected entry in scratch, requiring refusal **without repairing or deleting evidence**.

## Security and interpretation

- The three checkpoints represent **fresh-interpreter observation, not a reboot, crash, or power-loss test**. The writer process is still alive when the child starts; per-file/parent flush requests do not establish multi-file atomicity or power-loss durability.
- Even if all CI passes, *production storage writes, binding decisions, automatic replay, journal retirement, READY handles, and Notes remain prohibited*. A future operation-owned production controller must serialize and verify every actual transition continuously, make interruption phases recoverable, satisfy native owner/DACL checks, and explicitly resolve unsupported filesystem durability before any production enablement.

## Qualification gate

- Exact baseline SHA, branch, Git remote, clean index/worktree, CI blob and new paths checked before mutation. Source archive members and hashes, CI edit anchor, Python AST and safety markers validated in memory.
- Focused pytest including all earlier native diagnostics, Ruff whole tree, strict mypy Linux and Win32, isolated wheel provenance, existing installed no-write, one-file and two-document checks, and new three-case separate-process verification are required before guarded commit/push.
- PR CI must independently pass both Windows and Linux installed-wheel jobs; no fake pass, skip, or fallback is permitted. On failure preserve the worktree and issue evidence without automatic reset.
