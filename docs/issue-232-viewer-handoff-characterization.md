# Core #232 — Windows viewer handoff characterization (Slice 1)

## Context

A Concord teacher verified an immutable assembly PDF and its SHA-256 against
its manifest. Launching the canonical 296-character path failed in the default
Windows browser/PDF viewer. Launching the same bytes using a 218-character
`subst` alias succeeded. The original PDF and manifest were left unchanged.

`pds_core.local_open.open_local_path()` currently resolves the source, verifies
existence and type, and passes the resolved path to `os.startfile()` on Windows.
A successful ShellExecute request is **not** confirmation that the external
viewer can read or display the document.

Core #226 and Concord #124 previously bounded *writer-created* components but
did not qualify the full launch-to-viewer path for previously stored and newly
created evidence. The fix must preserve existing canonical paths and caller
authorization/integrity checks.

## First design question: can a user-local directory junction provide the alias?

Before introducing privacy-bearing copied PDFs or permanent drive mappings,
characterize an **ephemeral NTFS junction to the document's parent directory**.
This preserves original bytes, relative HTML dependencies, and the directory
contents without duplicating evidence. The junction must not grant new
permissions; its owner, ACL, lifecycle, stale state, and reparse restrictions
require dedicated security review before production adoption.

On the **actual Windows classroom computer**, with a known PDF path already
stored in `$pdf` (or another verified target):

```powershell
& .\scripts\qualify_issue232_windows_viewer_alias.ps1 -TargetPath $pdf
```

The script:

1. Verifies the source exists and is a file/directory.
2. Creates one randomized junction under the user's local AppData (not OneDrive).
3. Compares SHA-256 of the file and its junction alias before launch.
4. Opens the **alias string** via `Invoke-Item`, without `Path.resolve()` before
   the shell handoff.
5. Requires **human observation** of document accessibility; a successful
   PowerShell return alone is insufficient.
6. Verifies authoritative file bytes are unchanged and removes only the
   junction (never the target), once the viewer is closed.

Prints only lengths, results, and hash equality, not private source paths.
If interrupted while viewer launch is unresolved, it conservatively leaves the
alias in place and prints safe recovery instructions; it must not delete a
junction that a live viewer may still need. No arbitrary copy of student work.

### Qualification gates

- [ ] Real verified 296-character PDF under OneDrive opens from junction alias.
- [ ] Real viewer is checked manually, not inferred from `Invoke-Item` return.
- [ ] Source SHA-256 remains unchanged before and after.
- [ ] HTML with relative assets continues to resolve under a junction alias.
- [ ] Deep folder opens correctly in Explorer.
- [ ] Junction creation works without elevation, admin policy changes, or
      Developer Mode, and under both x64 and ARM64 Windows.
- [ ] Secure local per-user alias root, no traversal, no reparse-target swap,
      deterministic cleanup/recovery, safe concurrent viewers.
- [ ] Core API compatibility and truthful request-vs-rendering outcome.
- [ ] Isolated-wheel and genuine Windows-viewer acceptance against Core v0.6.6.

If the junction method fails real application qualification, evaluate a
short-path local staging contract with **explicit** privacy, cryptographic
identity, HTML dependency, lifetime, and crash-recovery rules. No final handoff
strategy is selected until physical tests pass.

## Core v0.6.6 release sequence

Design/qualification probe → narrow implementation + focused tests →
installed-wheel Windows physical acceptance → Core v0.6.6 version/release
gates → published wheel/hash/tag verification → downstream consumer releases.

Do not run the entire suite for a dirty worktree and immediately repeat it from
a clean tree without an intervening change. Preserve old Core release evidence.
