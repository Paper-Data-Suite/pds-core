# Core #238 — Slice 3G74: operation-held installed native recovery custody

## Baseline and gate

- Baseline: `6a6f6956848b9cd21b7766ad44b485a6ccdd97db` (3G73), draft PR #247.
- 3G73 CI run `43139544951` completed 15/15, including Windows/Linux installed read-only recovery triage.
- Decision: the next missing qualification is **operation-owned** custody of the native identity evidence throughout a single decision, not a caller-supplied or previously released review token.

## Bounded implementation

Add one installed-wheel verification script, its focused regression tests, this audit and one new step/artifact in the existing #238 Windows/Linux installed-native CI job. Preserve the already-qualified five preceding installed-wheel gates and production write barrier.

The new script constructs only fresh canonical synthetic private registry, association descriptor, journal and stages using 3G71's fixture. An independently launched Python interpreter obtains a nonblocking cooperative scratch lock in a separate scratch-only lockfile, retains native directory and file handles over two independent **no-hint** 3G73 read-only classifications, and requires identical native IDs before and after the decision. Any changed native ID, name, image, namespace or classification is `conflict_preserve`. It tests three legitimate pending-journal checkpoints, three deliberate evidence corruptions, and the refusal/release of a contended cooperative lock.

The lock is **advisory and synthetic**. It is not a security boundary against a noncooperating process, does not qualify lockfile ownership/ACLs for a production storage root, and is not a production operation permit. Rechecking the handles cannot prove an intervening instantaneous rename was impossible. Filesystem flush requests and fresh interpreter reopens cannot establish power-loss durability.

The pending journal **must not be removed**. No replay, retry, descriptor/registry modification by the new verifier, native production writer, Notes capability or release behavior is activated. The checkpoint classifications are observations only.

## Qualification and bounds

Guard exact branch, remote SHA, clean tree, original CI blob, absent new paths and four-file scope. Run focused pytest, Ruff and strict mypy on Linux and Windows, then build and install an exact candidate wheel in a fresh venv outside the checkout and execute the prior five gates plus the new operation-held native test. Commit/push only after all local checks pass. Verify native Windows and Linux independently through draft PR #247 CI.

Keep Core #238 open. Remaining critical work includes verified production owner/path admission, operation-owned two-root commit and recovery protocol, directory-entry durability qualification, interrupted transaction convergence, and safe journal retirement. No passing synthetic gate may be substituted for those requirements.

## Slice 3G74 Repair 1 — two strictly typed dynamic return values

- Original 3G74 local qualification: 85 focused tests passed (2 skipped) and Ruff passed; strict mypy stopped with two `no-any-return` findings before a commit was attempted. The reported dynamic returns are the guarded triage result in `scripts/verify_issue238_installed_guarded_recovery_custody.py` and the injected triage result in `tests/test_teacher_private_installed_guarded_recovery_3g74.py`.
- The imported 3G73 helper is dynamically loaded as `ModuleType`, so mypy sees its return as `Any`. Use precisely one `cast(str, ...)` at each typed return and import `cast` from `typing`. No native procedure, lock, checkpoint, image, authorization, or error-handling path changes.
- Preserve the exact uncommitted 3G74 four-file scope, repeat focused tests, Ruff, both strict mypy targets, installed-wheel no-write, one-file, two-document, fresh-process, inferred-triage and operation-held custody gates. The repair commits/pushes only on a complete pass.
- Recovery replay, journal retirement, production mutation and Notes activation remain prohibited. No synthesis of security authority from a successful synthetic checkpoint.
