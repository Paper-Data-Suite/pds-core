# Core #232 — Slice 3: viewer-alias lifecycle and Windows qualification

## Baseline

- Branch: `232-windows-viewer-safe-local-opening`
- Production package version remains `0.6.5` until Core **v0.6.6** release preparation.
- Slice 2 pilot: 25 passed, 1 skipped; Ruff and MyPy passed.
- Real user-selected Concord PDF: original path 296 chars, Core candidate returned the canonical path; default PDF viewer actually opened; canonical source bytes unchanged. **Physical PDF acceptance: PASS**.

## Hardening

1. Use `os.path.lexists()` to detect *any* occupied alias name, including a dangling link that `Path.exists()` might not detect.
2. Cleanup is auxiliary: if a stale alias changes or an error occurs while removing it, Core does not fail to open a separate authorized file. Ordinary directories are never removed as links.
3. If Windows rejects the shell launch synchronously, remove only the newly created alias, since it was not delivered to a viewer. If launch is accepted, keep the alias for asynchronously loading viewers.
4. Add a real-Windows regression for pruning a junction under a **private synthetic test root**, verifying that source content remains untouched. Do not force expiry or cleanup of any real teacher-created aliases.

## Physical lifecycle acceptance

Run on the Windows pilot computer (normal unprivileged user) from the Core repository after the Slice 3 focused gate:

```powershell
python .\scripts\qualify_issue232_windows_viewer_lifecycle.py
```

This uses only synthetic HTML, CSS and a marker file under a temporary location. Its isolated child process opens the target and exits **before** the test checks persistence. It tests:

- deep HTML with a **relative CSS asset** in the default browser;
- deep folder in Windows File Explorer;
- unique owned junction persistence beyond Core process lifetime;
- alias length within the Windows handoff budget;
- `os.path.samefile()` identity for alias vs original;
- unchanged original bytes;
- explicit removal of **only the synthetic test aliases** after the teacher closes each tab/window;
- expiry pruning of a separate disposable test junction without touching its target.

The test prompts the user to confirm **actual** viewer appearance. It does not infer a rendered document from `os.startfile()` success. The test removes its synthetic files, not canonical PDS work; if source content unexpectedly changes it fails. The teacher's earlier PDF alias is intentionally **not** deleted by the lifecycle test.

**Do not** run `Remove-Item -Recurse` on the Core viewer-alias root: its entries are directory junctions to real work. The Core implementation only removes a single validated junction with `rmdir()`.

## Open release gates — v0.6.6

- Pass the Slice 3 focused gate and real Windows lifecycle acceptance.
- Verify effective permissions on `%LOCALAPPDATA%\PaperDataSuite\viewer-aliases-v1` under the actual non-elevated teacher account. The implementation inherits the existing user-profile ACL; do not *assume* it is sufficiently restrictive if the environment has modified profile permissions.
- Exercise Windows real junctions / path identities under Python 3.11, x64 and ARM64 where available. Windows CI can cover supported Python versions; the pilot gives real viewer proof on its machine.
- Review any remaining failure, concurrent-open and cleanup lifecycle concerns. Explicitly acknowledge the finite 30-day lease assumption for *very long-lived* viewer tabs.
- Add exact version 0.6.6 wheel/sdist inspection, isolated installed-wheel smoke, changelog/release notes, and correct version metadata; preserve all published 0.6.5 documents and release identities unchanged.
- Run one authoritative clean full suite, package/installed acceptance and PR CI. Avoid a dirty full suite followed by an unchanged duplicate clean suite.
- Tag/release and independently verify Core **v0.6.6**, then coordinate changes or acceptance in Concord, ScoreForm, Quillan, and Vitrine.
