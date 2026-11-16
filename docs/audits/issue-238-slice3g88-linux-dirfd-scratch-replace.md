# Core #238 — Slice 3G88: Linux handle-relative scratch replacement

## Scope and resolved boundary

3G87 retained a native parent directory during a disposable registry replacement,
but called `os.replace` using pathnames. 3G88 proves that on **native Linux** the
same non-authorizing scratch transition can use `os.replace` with **both**
`src_dir_fd` and `dst_dir_fd` tied to a single retained directory FD. It never
accepts a workspace path, private-root path, intent, write callback, handles,
file content, or actor-provided credentials. The implementation owns one
random disposable directory and fixed synthetic bytes and names.

The same existing cooperative lock is held for the entire scratch transition.
The Linux rehearsal uses `O_NOFOLLOW` plus directory-relative reads and validates
UID, restrictive modes, no hardlinks, exact bytes, file identity and stable parent
identity. Pre-replacement entry replacement with *identical content* must be
refused on file-identity drift. Renaming/relinking the parent name must also
refuse before replacing anything. Successful positive replacement verifies the
stage became the live image and the synthetic journal remains pending. Linux
file- and parent-fsync calls are diagnostic persistence requests, **not** proof
of power-loss recovery.

## Critical restrictions

- Windows **explicitly refuses** this Linux-native protocol before creating
  scratch. A Windows equivalent requires its own reviewed handle-relative
  replacement API; no fallback to a path-based `os.replace` is implied.
- Native Linux parent custody and dirfd-relative `os.replace` narrow pathname
  substitution exposure, but are **not** an atomic content compare-and-swap or
  defense against an uncooperative process with the same OS-user permissions.
  In particular a preflight-to-replace TOCTOU interval remains.
- Scratch-only evidence does not qualify effective production OS-owner ACL,
  live descriptor binding, registry/journal/stage reconciliation, interrupted
  operation recovery, multi-file atomicity, directory crash durability,
  or journal retirement. Nine production blockers remain intact.
- No first binding, teacher Notes service, automatic replay, or portability
  functionality is enabled. The terminal capability set is unchanged.

## Qualification

Tests cover normal Linux dirfd-relative replacement; registry and stage inode
drift despite unchanged bytes; parent relink; untrusted scenario types; and
unchanged negative capabilities. The isolated installed-wheel gate checks Linux
native scenarios and Windows fail-closed denial, with a sanitized report.
The runner retains 3G87's nineteen installed gates and adds one twentieth,
verifying exact committed SHA, CI Git blob, worktree and clean index before
patching, then tests, Ruff, dual-platform strict mypy, all twenty wheel gates,
scoped commit and conditional push. Do not reset/stash/auto-restore on failure.

## Next engineering gate

Review the noncooperator TOCTOU remaining between preimage check and Linux
replace, and develop native Windows handle-relative scratch semantics. Do not
promote a scratch result into a production write permit.


## Slice 3G88 Repair 1 — strict cross-platform mypy of POSIX-only flags

The original Windows local qualification stopped **before wheel gates, commit, or push**
after 82 focused tests (5 skipped), Ruff lint/format and Linux-targeted strict mypy
passed. Windows-targeted strict mypy rejected two `os.O_NOFOLLOW` attribute
references in Linux helper functions; Windows OS type stubs omit the flag.
The two helper lookups now use `getattr(os, "O_NOFOLLOW")`. This returns the
identical OS constant on Linux and does not invent a zero-valued fallback.
The diagnostic already refuses non-Linux platforms and checks availability of
both `O_NOFOLLOW` and `O_DIRECTORY` before calling either helper. The third
direct `os.O_NOFOLLOW` use within that guarded Linux-only function remains
untouched. No runtime behavior, scenario, source fixture, CI gate, or writer
authority changes.

The guarded repair verifies the exact uncommitted five-file 3G88 worktree
against the original source archive and CI edit, changes only the module and
this append-only audit, and reruns original 3G88 qualification including all
twenty native installed-wheel gates, Ruff, strict Linux/Windows mypy and
conditional exact-scope commit/push. The nine production blockers remain
unqualified; production binding, automatic replay, journal retirement, and
Notes activation remain disabled.
