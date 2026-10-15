# Core #232 — Windows viewer-safe handoff (Slice 2 implementation candidate)

## Verified source incident

On a teacher-operated Windows 11 workstation, a Concord PDF at a 296-character
canonical OneDrive location was a real 150,672-byte file with a SHA-256 matching
its retained assembly manifest. The default Windows viewer failed to open the
canonical path. A `subst` path of 218 characters succeeded. Slice 1 physical
acceptance then created an NTFS directory junction to the same PDF's parent:

- 296-character authoritative file path -> 95-character lexical junction path;
- same source bytes verified by SHA-256;
- real default Windows PDF viewer displayed the document;
- viewer closed, then junction removed; source unchanged.

The result proves *one* short-path handoff, not every viewer or lifecycle case.

## Slice 2 changes

`pds_core.local_open.open_local_path()` continues returning the **canonical
source `Path`** and preserving short-path behavior and Linux/macOS openers.
On Windows paths longer than a **conservative 240 UTF-16 code-unit handoff
budget**, it now:

1. Resolves and verifies the canonical source first, as before.
2. Establishes a per-user alias directory under
   `%LOCALAPPDATA%/PaperDataSuite/viewer-aliases-v1` (never under OneDrive).
   The alias root must be real directories, not symlinks/reparse points.
3. Creates a unique `v_<32hex>` NTFS directory junction to the source file's
   parent, or directly to the target when opening a folder. No source bytes are
   copied or rewritten. Junction construction passes paths as child-process
   environment variables, not executable PowerShell strings.
4. Verifies the alias is a link pointing to the **same filesystem object** as
   the source using `os.path.samefile()`. Rejects unsafe/mismatched aliases.
5. Invokes Windows shell opening with the **lexical alias**, without applying
   `Path.resolve()` to the alias (that would defeat the shortening).
6. Leaves the junction available after shell launch so asynchronous viewers can
   continue loading the same file. Recent aliases are not removed immediately.
   A later long-path opening performs cautious best-effort cleanup of aliases
   older than **30 days**, removing **links only**, never following them into
   source directories or deleting ordinary user files.

Because shell APIs cannot reliably detect a subsequent browser/PDF tab load,
returning from Core means **the launch request was accepted**, not proof that
an external viewer rendered a page. Consumer success messages must be aligned
with that distinction.

## Privacy, boundaries and non-goals

- Alias names are random tokens without student names, Activity titles or
  document basenames (except the original filename for the opened file).
- Source paths remain authoritative, and Core's `open_local_path()` itself is
  **not** an authorization or manifest-verification API. Each caller must first
  enforce provenance, allowed workspace, authorization, digest and file type.
- The user-local alias root inherits the current Windows user's profile ACL.
  Aliases cannot grant access that the current OS user did not already have.
  Future qualification must verify the effective ACL and adversarial reparse
  behavior on actual Windows 11, not assume a Linux symlink mock proves it.
- The alias may expose sibling files in the same source directory to that same
  OS user; do not make aliases accessible to additional principals.
- Removing junctions must NEVER use recursive deletion / `Remove-Item -Recurse`
  or delete the original source directory. Only link removal is permitted.
- Files with extremely long **single filenames** or unusual local-AppData
  locations may not fit the 240-unit alias budget; these fail closed with a
  bounded message rather than silently invoking the failing original path.
- No registry changes, shell environment mutation, manual drive mappings,
  workspace migrations, or permanent copied student data.

## Open qualification items before v0.6.6

- **Windows physical:** installed candidate wheel opens the exact classroom
  PDF with normal code (`open_local_path`) through its default viewer, returns
  canonical path, and preserves source SHA-256.
- **HTML:** actual default browser loads HTML and relative assets from a deep
  source tree; original resource paths remain unmodified.
- **Folders:** actual Explorer opens a deep canonical directory through alias.
- **Viewer lifecycle:** verify alias remains available after the Python call,
  after the source PDS process exits, and while the viewer opens asynchronously.
- **Cleanup:** validate junction metadata and removal behavior on Windows
  Python 3.11, 3.13, x64 and ARM64 where available. Determine whether 30-day
  expiry is sufficient for long-lived browser tabs; revise the policy if not.
- **Security:** test normal non-elevated user account, deep OneDrive, root
  reparse rejection, unsafe/mismatched links, scoped user ACL, concurrent opens,
  interrupted launches, and PowerShell unavailability.
- **Release:** add exact v0.6.6 artifact checks and installed-wheel tests; bump
  `pyproject.toml` and `pds_core.__version__` only when the accepted solution is
  qualified; preserve v0.6.5 and historical release records. New wheels/tags
  must be independently verified before Concord/Quillan/ScoreForm adoption.

## Test economy

Run the issue-specific unit suite first, then Ruff and Mypy on changed modules,
then the genuine Windows physical gate. Reserve the full Core suite, clean-tree
installed-wheel/sdist qualification and cross-repository release gates for the
ready-to-release candidate. Avoid back-to-back dirty/clean full-suite repeats.
