# Core #238 — Slice 3G78: repeat-recovery idempotence, synthetic only

## Baseline and purpose

- Base `3a476068c694d5b096bee6e71c92621ae817ed3a` (3G77 Repair 1); draft PR #247. GitHub Actions run `43152745219`: 15/15 passed, Windows and Ubuntu.
- 3G76 showed one bounded recovery after process death; 3G77 showed another forced process interruption inside recovery followed by independent completion.
- **3G78 decision:** An explicit second or third synthetic recovery of a *fully applied, journal-pending* transaction must be a verifiable **native no-op**; no additional replacement, identity change, content change, or journal removal may occur. This is not a production replay permission.

## Implementation

- Add installed-wheel verification script `scripts/verify_issue238_installed_recovery_idempotence.py`, focused tests, this audit, and an additive CI step/artifact within the existing installed-native matrix. No production module is modified.
- For each of the three post-death checkpoints, build exclusive canonical scratch, terminate the initial writer, explicitly recover with 3G76, and independently review the full after-image + pending journal. Re-enter recovery from **two more isolated installed interpreters**. Require exactly zero steps, exact native file identities, a stable entire-file snapshot, the untouched canonical pending journal, and fresh guarded review after each iteration.
- Under a native cooperative lock held by one process, a competing child recovery must fail closed before mutation. After lock release, one explicitly authorized *synthetic test* recovery may complete, and its second invocation must make zero changes.
- Mutate each of four fully applied synthetic checkpoints (journal bytes, unexpected namespace, descriptor bytes, registry bytes) and attempt synthetic recovery twice. Every call must classify `conflict_preserve`, perform zero replacements, and preserve the exact poisoned evidence.
- Evidence is bounded to checkpoint names, step counts, conflict categories, boolean safeguards, installed wheel digest and platform. Never serialize private paths, content, native file identifiers, or owner data.

## Qualification

Require exact branch, base HEAD, origin, remote HEAD, clean worktree and original CI Git blob. Apply exactly four files. AST-preserving Ruff format, relevant pytest, Ruff check, strict mypy both Linux and win32, isolated candidate wheel, nine prior installed-wheel gates and new 3G78 verifier. All gates pass before conditional commit/push; PR CI on both platforms must pass independently.

## Explicit limits

These operations occur only in fresh disposable synthetic directories. Native lock is cooperative; a passing zero-write check does not establish ACL custody or exclusion of hostile writers. Normal process execution does not qualify sudden power loss, kernel crash, or multiple-file atomicity. The journal remains pending even when both metadata after-images are applied. **No production mutation, automatic replay, retry, journal retirement, transaction commit, READY private binding, or Notes access is authorized.**

## Slice 3G78 Repair 1 — dynamic import lock class identity

- The initial Windows focused run stopped after 12 tests passed, with one test failure in `test_concurrent_owner_lock_refuses_and_releases`. Native `msvcrt.locking` correctly raised `PermissionError` and the guarded operation converted that refusal to `_LockBusy`.
- Repeated dynamic imports instantiate separate `ModuleType` objects and therefore distinct `_LockBusy` Python class objects; the test compared exception identity against a different import instance.
- Replace ONLY the test's direct `pytest.raises(guard._LockBusy)` assertion. Require the caught exception to be named `_LockBusy`, originate from the `core238_3g74_` isolated loader namespace, and retain a `BlockingIOError` or `PermissionError` as its cause. Preserve the file snapshot and after-release recovery assertions.
- The installed verifier, operation lock, production write barrier and CI workflow are NOT changed. Rerun the original 3G78 focused pytest, Ruff, Linux/Windows strict mypy, and all 10 installed-wheel gates before conditional commit/push.
- No production writes, automatic replay, journal retirement or Notes access are enabled.
