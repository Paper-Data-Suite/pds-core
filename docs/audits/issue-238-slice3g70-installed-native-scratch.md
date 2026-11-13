# Core #238 — Slice 3G70: installed wheel positive native SCRATCH replacement qualification

## Decision and exact baseline

- Baseline: `c5e485f9784cca2a32db3432be2c0e9b2a7ba45a` (3G69), draft PR #247.
- 3G69 CI run `43121244513`: **15/15 jobs passed**, including previously failing Windows Python 3.12/3.13 exact target-content and file-ID assertions. This qualifies one low-level native rename primitive, **not** production transaction durability or workspace binding.
- **Next gate:** exercise actual native scratch replacement from a **freshly installed candidate wheel** on both Windows and Linux while establishing that canonical production binding writes are still denied. This is an executable D2-positive *synthetic* prerequisite, not a promotion of earlier read-only review results into execution capability.

## Change scope

1. `scripts/verify_issue238_installed_scratch_transition.py` — strict `python -I` isolated wheel probe. Requires installed distribution under its venv's site-packages, exact candidate version and supplied wheel, a disposable scratch directory outside the source checkout, and a canonical positive-intent `PRODUCTION_BLOCKED` check both before and after the synthetic operation. Windows uses the exact installed internal `FileRenameInfoEx` helper with separately retained original/stage handles, checks target byte image, absent stage name, and all native file IDs; Linux runs one `os.replace` with retained original/stage descriptors and equivalent inode and byte checks. One attempt; no retry, fallback or production directory access. Emits sanitized deterministic result and the candidate wheel SHA-256, not paths, identities, raw bytes, or owner values.
2. `tests/test_teacher_private_installed_scratch_transition_3g70.py` — asserts one native call per branch, refusal/no-retry behavior and preservation of the old and staged images under injected POSIX failure, no public authorization path or Notes capability.
3. `.github/workflows/ci.yml` — add a distinct strict step to the **existing** `issue238-installed-native-boundary` Windows/Ubuntu matrix, after the already passing no-write gate. Upload separate sanitized scratch evidence. A refused native rename, altered identity, stale installed package or changes to the barrier fail CI. Keep both existing no-write tests and source-level validation unchanged.

## Qualification and explicit limits

- Exact clean branch, HEAD, remote and CI workflow blob; no unlisted file changes, resets, stashes or destructive cleanup. Local focused pytest, full-tree Ruff, strict mypy on Linux+Windows, isolated candidate wheel, both no-write and positive scratch probes. Guarded commit/push only upon complete qualification.
- Actual native CI on Windows and Ubuntu is required. The positive scratch result **must not** be interpreted as production authorization, durable rename across power loss, a two-document atomic transaction, successful descriptor update, replay, journal retirement, a READY handle, or Notes records access.
- Native macOS and unsupported remote/cloud volumes remain unqualified. Final #238 D0/D1/D2 checklists and security review remain open. Do not merge draft PR #247 based only on green CI.
