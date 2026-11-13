# Core #238 — Slice 3B9: guarded first creation of the private registry lock file

**Baseline:** `33d9c132c47d05446d60993fa860b783fdc7f87f` (Slice 3B8).
**D0 authority:** Explicit owner-approved architecture recorded on issue #238 (2026-10-25) and `issue-238-slice3b7-approved-d0-and-linux-provision.md`.
**Boundary:** Exact one-file protected creation, *not* a writable Notes store, association initialization, metadata commit, or D2 installed release qualification.

## Why this is the next durable primitive

Slice 3B6 can hold an exclusive cross-process lock only after its file exists. Slices 3B7/3B8 can create an empty protected child directory on Linux/Windows but cannot initialize the coordination file. Slice 3B9 adds `pds_core._teacher_private_lock_file_provision.create_private_registry_lock_file` to explicitly create **only** `<verified-v1-root>/.registry.lock`, containing **exactly one zero byte**, so the existing lock primitive has a nonempty first byte to lock. It does not create the root, registry JSON, journal, descriptor, collection directories, or any Notes entry.

The operation accepts only the exact current platform candidate private root. It neither calls the existing workspace initializer nor interprets a caller-provided principal. A renamed path, arbitrary parent, alternate or network location, unsupported platform or unknown native owner fails closed. No path, owner SID/UID, file descriptor/handle or authorization credential appears in its result. `CREATED_RESTRICTIVE_UNQUALIFIED` is **not** `READY`: a later guarded service must revalidate owner, ACL, locality, locks and state under held handles.

## Linux implementation

Reuses Slice 3B7's native no-follow, effective-UID-owned, mode `0700`, ACL and local-filesystem parent checks with the final directory descriptor held. Calls `openat` via Python `os.open` with `O_EXCL|O_CREAT|O_NOFOLLOW`, specifying `0600` **at creation**, then writes one fixed byte, flushes, and compares `fstat` and no-follow `stat` file identity. Requires one link, `0600`, matching UID/device, no extended access ACL, and accepted native `statfs` backing. It never overwrites or truncates a preexisting entry, including a symlink. Any failure after the file was created reports `CREATION_UNVERIFIED` and preserves the partial file for review; no dangerous automatic removal or chmod occurs. If an unusually restrictive process umask changes the result to mode `000`, the file remains in place, flagged for review.

## Windows implementation

Requires the Slice 3B8 exact private-root syntax, current process-token SID, fixed NTFS/ReFS backing and the earlier native DACL/reparse refusal preflight. Calls `CreateFileW(CREATE_NEW)` with an inheritance-protected, owner/SYSTEM/Administrators-only DACL **at creation**; no permissive default-ACL window. It writes the fixed byte using `WriteFile`, flushes with `FlushFileBuffers` and verifies file attributes, opened-handle owner/DACL, and unchanged qualified parent/backing. It does not repair ACLs, open unknown files for overwriting, or return a live native file handle. An unverified postcondition leaves the created file untouched and reports `CREATION_UNVERIFIED`. An existing file returns `ALREADY_EXISTS` without treating its contents as trustworthy.

**Security limitations:** Parent validation is not yet one indivisible held-handle transaction with file creation on Windows. Filesystem locality allowlists are necessary filters, not proof against same-user malware, privileged administrators, cloud backup or all mount/alias attacks. This slice does not qualify a complete CAS/journal transaction or authorize private data writes. Native macOS remains unsupported.

## Source and installed qualification

`tests/test_teacher_private_lock_file_provision.py` covers exact fixed filename/byte, invalid/alternative roots, zero Notes capability, Linux native owner/mode/backing/umask/exclusive creation, no symlink overwrite, and creation followed by the previously implemented lock. Windows-safe synthetic SDDL tests run cross-platform. A **genuine Windows native test** creates private fixture directories under a temporary test root using the guarded prior primitive, binds `LOCALAPPDATA` only within the test, provisions the lock file, acquires/releases its lock and verifies refusal to overwrite. Native Linux functional tests must run under a non-root OS account on a known local filesystem; test-only locality mocking remains D1 and does **not** establish D2 local backing. Windows source tests are likewise not isolated installed-wheel qualification.

The guarded runner verifies exact remote/HEAD, allowed worktree scope and payload hashes, then executes focused regressions, full pytest, Ruff, strict mypy and staged Git checks before a conditional commit/push. CI native/installed evidence and comprehensive transaction security remain later slices; no published `pds-core` release is changed here.

## Remaining work

Protected `registry.json`/journal creation and writes; qualified descriptor and registry two-tree lock ordering; revision CAS; atomic replacements and durable intent journaling; interrupted transaction recovery; explicit teacher binding/move/fork review (#238 Slices 4–5); adversarial/native D1–D2 tests and installed-wheel proof (#238 Slices 6–7). Notes records (#239), user menus/CLI (#240), and portability (#243) remain excluded. Teacher capability tokens remain exactly `terminal.header.v1` and `terminal.notes_command.v1`.
