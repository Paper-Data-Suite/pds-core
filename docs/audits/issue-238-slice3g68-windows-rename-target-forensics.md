# Core #238 — Slice 3G68: typed Windows rename target forensics

**Baseline:** `b76d5caecb44d0ac301d05c9e29a012ee89c310e` (3G67), draft PR #247.

## Evidence motivating this bounded probe

On real GitHub-hosted Windows Python 3.12 and 3.13 (run 43110357229), the original `FileRenameInfoEx` call reported TRUE and removed the stage name, but target `registry.json` continued to name the old file. An unexpected entry under the synthetic scratch parent contained the staged after-image. The native layout was offset=20, sizeof=24, WCHAR=2. Absolute-path-with-NUL control returned target-unreadable; parent-relative control refused. All 13 other CI jobs passed.

## Exactly scoped change

Modify ONLY the existing native scratch test to (1) report a bounded, non-reversible shape comparison between the unexpected synthetic **basename** and the intended fixed basename, and (2) run ONE independently created, synthetic `MoveFileExW(REPLACE_EXISTING)` control with both existing target/source handles open for deletion sharing. This is *not* a production fallback or a retry of the original failed mutation. Controls check actual bytes, native file identity, and retained handles before reporting `correct`. No raw paths, contents, SIDs, usernames, handles, or private records are emitted. No new artificial test passes are introduced.

Original `FileRenameInfoEx` native test and its full postcondition remain STRICT and continue to fail if the real production helper misnames the target. Production code, CI workflow, release, public writer, replay, journal retirement, and Notes are unchanged.

## Qualification

Exact clean branch/HEAD/remote/blob guards; one test and one audit path only. Local focused pytest, Ruff, and mypy for both Linux and Windows. Commit/push only on success; the PR CI must independently test Windows Python 3.12/3.13 to determine the next production correction. A red run with explanatory diagnostic is an acceptable diagnostic outcome, never a merge gate pass.
