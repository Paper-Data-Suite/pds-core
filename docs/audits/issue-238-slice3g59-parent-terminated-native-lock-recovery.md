# Core #238 Slice 3G59 — Parent-terminated native transaction-lock recovery

## Baseline and change scope

- Feature branch: `238-establish-private-teacher-workspace-storage`.
- Exact 3G58 qualified baseline: `81487e0402ca711ba2a9bd9f924cbea5a425ce0a`.
- Exact base `main`: `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`.
- Add only `tests/_core238_3g59_parent_kill_worker.py`, `tests/test_teacher_private_recovery_parent_termination.py`, and this audit. No `pds_core` source changes.

## New native evidence

3G58 terminated its own child with `os._exit`. This test forcibly terminates a *different* child process from the parent at four canonical two-document mutation boundaries. The child must first announce an exact nonce-marked checkpoint **while the 3G57 scratch transaction lock, four native parent handles, and staged-file identities are still held**. A contender then attempts to obtain the same existing OS lock and must be refused. The parent calls `Popen.kill()` (Windows `TerminateProcess`, POSIX `SIGKILL`); only afterward does a new lock scope and new directory-handle scope inspect the retained on-disk journal/registry/descriptor and stages.

Selected boundaries: after preparation; after registry replacement; after descriptor replacement; after descriptor flush request. Expected checkpoints are, respectively, prepared, registry-after/descriptor-pending, both-after/journal-pending, and both-after/journal-pending. The journal must remain byte-for-byte canonical and present. Observation must never change metadata. Additional adversarial cases corrupt only a disposable pending journal *after* the worker dies and require a conflict/preserve decision rather than replay or reset. Invalid nonce, token, or phase must be rejected before any transaction filesystem changes.

## Custody, security and interpretation

All byte-producing operations occur in a direct, high-entropy, marker-verified system temporary subdirectory using the existing 3G57 fixed canonical *synthetic* `FORK_COPY` transaction. The child accepts only a restricted phase enum and has no production root, user-selected serializer, public writer callback or Notes entry point. The parent owns all scratch setup and cleanup. Runner is additive, Git-pinned, source-hashed, fail-closed, and commits/pushes only after native Windows tests, focused Core regressions, Ruff and strict mypy pass.

**A process being terminated is not a power outage.** Successful recovery proves neither Windows parent directory namespace durability nor a two-document atomic commit, ACL continuity across an actual cloud-backed workspace, safe automatic replay, journal retirement, or any production mutation capability. No process-exit finding is a write token. Preserve the Core production barrier and all pending journal evidence. Do not claim #238 D2 installed-wheel or Notes activation.

## Next acceptance boundary

Integrate bounded crash/restart outcomes with continuously held **protected operation-owned** native ownership, workspace-binding, and dual-stage custody. Resolve the write/recovery state machine and persistence guarantees before enabling private metadata mutation in production.
