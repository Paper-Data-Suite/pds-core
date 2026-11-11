# Core #238 — Slice 3G66: Windows native replacement diagnostic, no pass suppression

## Evidence and exact scope

- Baseline: `e11d2a393bf7b84dd318ebe920014f2875f59c5e` (3G65). PR #247, CI run 42944980661.
- 3G65 CI: 13/15 jobs green; Windows Python 3.12 and 3.13 each fail precisely `test_windows_native_scratch_replacement_preserves_handle_ids`; Windows Python 3.11/3.14 and every Ubuntu matrix pass.
- Earlier CI reported an unqualified real `FileRenameInfoEx` stage-to-registry replacement. On Windows 3.13 the syscall reported success but reopening the target name returned unexpected synthetic contents. On Windows 3.12 failure was at the adjacent native assertion; full differentiation is still missing.

## Change

Modify ONLY `tests/test_teacher_private_windows_registry_replace_attempt.py` by retaining the native child process and **all** pre-existing assertions while adding a bounded read-only postcondition observation after the single scratch rename attempt. The scratch directory contains only two synthetic, purpose-created files. On any failure, include fixed labels for:

- syscall success vs refusal;
- named target data after/before/missing/unreadable/unexpected;
- source directory entry present/absent;
- retained original/stage identity stable/changed;
- reopened target identity stage/old/other/unavailable/unverified.

The diagnostic never prints paths, real teacher contents, SID/UID, identifiers, or raw image bytes. It does not rewrite the target, try another rename mode, change production implementation, change CI skips, or make a failed security postcondition pass. All existing strong assertions are retained after the observation.

## Qualification

Guard exact baseline/remote HEAD/worktree/one blob, one unique source anchor, and two-file change scope. Run focused test on local Windows, Ruff, strict mypy and Git whitespace hygiene; commit and push only after passing the local gate. The GitHub PR workflow will independently re-run the native matrix. Red CI is expected on the affected runners until the issue is fixed, and is useful to classify it; do **not** merge or mark issue complete.

## Bounds

Production write barrier, private storage authorization, replay, retirement, Notes and release remain disabled. Native rename/durability behavior remains unqualified. A successful local native test does not qualify other Windows filesystem or Python versions.
