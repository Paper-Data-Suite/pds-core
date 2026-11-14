# Core #238 — Slice 3G80: retained native private-root custody

**Baseline:** `34e3329ed16b468948048acab079777dd5ee20f9`, draft PR #247. 3G79 CI `43360716545` passed 15/15 Windows/Linux jobs. **This slice does not remove any of the nine production write barriers.**

## Decision and exact scope

3G79 enumerated nine production-write blockers. The immediate production security requirement is to verify **effective OS owner, private-root permissions and native directory identity continuity while native handles are held**, not rely on separately released preflight snapshots. Add exactly five files: private Core module, tests, installed-wheel verifier, this audit and an additive existing CI matrix gate. The private Core module is not a producer API.

## Real native custody boundary (read-only)

- The parameterless `review_existing_private_root_native_custody()` obtains Core's prospective private root and native effective principal, not a caller-supplied path or claimed teacher identity. If missing or unsafe it returns a bounded non-authorizing status and creates nothing.
- Linux: open and retain `/` and every existing descendant directory via `O_NOFOLLOW | O_DIRECTORY`; verify `fstat`/`stat(dir_fd, follow_symlinks=False)` identities before and after inspection. Refuse untrusted writable ancestry; enforce process effective UID, exact `0700`, and no unqualified access ACL on `private/notes/v1` while directory descriptors remain open. Refuse unsupported/ambiguous filesystem support. All descriptors close inside the function.
- Windows: open every ancestry directory using non-following native `CreateFileW` handles, check native file IDs, directory/reparse attributes, and the restrictive owner/SYSTEM/Administrators DACL on the protected subtree, then reopen the names and recheck DACLs and identities while retaining the original handles. Any unavailable native ABI/security information refuses. All handles close inside the function.
- Current process token SID/effective UID is verified again before reporting. Native locality, noncooperating-writer exclusion, exclusive operation lock, final transaction custody, crash persistence, and cross-document commit are **still not qualified**. Native read sharing/handle retention is not exclusive write authority.
- Only an enum and permanently false write/replay/retirement flags leave the review: no path, OS principal, metadata bytes, file IDs, FD/HANDLE, lock, credential or mutation capability. No Notes files, private roots, journals or workspace descriptors are created.

## Qualification and interpretation

Installed-wheel gate invokes the real parameterless Core review and checks that the existing 3G79 readiness review still names all nine blockers and the canonical production barrier returns `production_blocked`. This check may pass with `missing` or a refusal state on CI runners; it is a regression gate ensuring bounded behavior, **not evidence that a protected private root was present there**. Native positive Linux directory-handle behavior is additionally tested with an explicitly restricted disposable tree; platform-specific refusal and missing cases are tested. Windows private-root fixture qualification and protected production startup are still future work.

Retain all eleven existing installed-wheel gates. Qualification must run focused pytest, Ruff, strict mypy for both targets, isolated wheel build with the new Core module, all prior gates and this new gate. Guard exact branch, remote SHA, clean tree, original CI blob, five changed paths; auto-commit/push only after green, then require GitHub CI on Windows and Linux.

## Required follow-up

1. Test a genuinely protected Windows private-root fixture with verified owner SID/DACL, and independently verify local backing and protected creation under retained custody. Avoid using an unrestricted CI temporary directory as a positive ACL proof.
2. Integrate owner/ACL and workspace descriptor custody in an operation-owned guard with exact journal/stage CAS and native locking, then qualify directory persistence and recovery under actual protected roots.
3. Keep production binding, automatic replay, journal retirement, and Notes activation disabled until remaining requirements are demonstrably qualified. Do **not** interpret successful scratch transactions as a durable or atomic two-document production commit.

## Slice 3G80 Repair 1 — internal imported-name mypy contract

The stopped Windows qualification passed 140 focused tests and Ruff, but strict mypy reported `attr-defined` in the new test. The test accessed `custody.inspection`, which is a private imported module name rather than an explicit export. The test already imports `inspection` directly. This repair changes only that test expression to `inspection._effective_owner(sys.platform)`; the native custody module, installed verifier, and CI workflow remain byte-for-byte unchanged. Ruff reformats the repaired test without changing its AST. Full focused pytest, Ruff, strict mypy for both target platforms, and all twelve installed-wheel gates are requalified before any guarded commit/push.

The result remains non-authorizing; production binding, replay, journal retirement, and Notes activation remain disabled.

## Slice 3G80 Repair 2 — platform-safe Linux test owner

The stopped Repair 1 qualification passed 140 focused tests and Ruff and passed strict Linux mypy, but strict Windows mypy reported `Module has no attribute "geteuid"` in the Linux-only test. The pytest platform skip does not alter static mypy analysis. Remove the unused `os` import; derive the deliberately different synthetic UID from the already qualified `inspection._effective_owner("linux")` observation. This test-only change preserves the same Linux owner-mismatch assertion and creates no files. The native custody module, installed verifier, and CI workflow remain unchanged. All original 3G80 qualification gates, both mypy target platforms, and the installed-wheel checks must pass before commit/push.

No production binding, replay, commit, journal retirement, or Notes activation is authorized.
