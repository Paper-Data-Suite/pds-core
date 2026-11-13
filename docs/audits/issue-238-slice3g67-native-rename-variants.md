# Core #238 — Slice 3G67: native scratch rename-variant evidence (test only)

## Prior confirmed native evidence

CI 42957602231 on commit caeab6cdefd4c4e65f0b08cdd21159a611932d45: 13/15 pass; only Windows Python 3.12 and 3.13 fail with **the same** `rename_reported=True; target_data=before; source_name_present=False; old_handle_stable=True; stage_handle_stable=True; reopened_target_identity=old`. The syscall's positive return did not establish replacement. Win 3.11/3.14 and all Ubuntu matrix jobs passed.

## Synthetic-only variant experiment

Retain the original native replacement attempt, all its strict original assertions and the 3G66 failure classification. On original failure only, record fixed classifications of unexpected entries in this synthetic two-file scratch directory (no names/paths). Attempt two **independent scratch pairs**, each with a retained destination handle and the exact FileRenameInfoEx flags (replace + POSIX semantics):

- An absolute pathname with an explicit terminating UTF-16 NUL and fully sized buffer.
- A filename relative to an open parent-directory handle with an explicit terminating UTF-16 NUL.

Each experiment checks named target bytes, disappeared source entry, unchanged old/stage handle identities, and that a fresh target handle has the stage file's native identity. Any variant failure retains fixed state; no raw names, paths, OS principal, file IDs, contents or user data appear in logs. Any attempted success in a variant **does not change** the original test verdict. The original test remains red until the production backend has been proven correct on the failing host.

## Qualification and prohibitions

Exact 3G66 commit / remote / clean worktree / original blob guards. The patch must change only the native test and this audit, keep the normal test passing locally and run Ruff and strict mypy Linux/Win32. Commit/push only after local gates. This is an observation slice, not a production behavior change, a CAS proof, a durability claim, or authorization to write teacher-private data. Production writer, replay, journal retirement and Notes remain blocked.
