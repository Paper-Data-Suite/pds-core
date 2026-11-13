# Core #238 — Slice 3G6: Windows guarded stage-to-registry replacement attempt

**Baseline:** qualified 3G5 `b4c7884aa40a27f08da5596e1314db1b665bfdc0`.

## Exact scope

Introduce one **internal** Win32 native stage-to-registry replacement helper, inside the existing 3G5 mutation-aware retained guard. The new helper calls `SetFileInformationByHandle(stage, FileRenameInfoEx, FILE_RENAME_REPLACE_IF_EXISTS | FILE_RENAME_POSIX_SEMANTICS)` **once** using a DELETE-enabled handle opened under the guard with no fallback to cross-volume copy, no retries, no explicit deletion of remaining evidence, no compensating mutation and no indirect Notes activation. The helper returns sanitized advisory status only.

The existing 3G5 scope is solely responsible for holding native parent, old-target and stage identities and checking owner, local private backing, DACL, pending journal, exact before/stage/descriptor images, protected stage inventory, then exact after-image and expected identity transition. Source and target paths are constructed only from its validated intent and qualified existing private root. No caller-supplied arbitrary output filename is accepted by the public entry point.

A native rename failure, guard failure after the call, user interruption or unexpected resulting identity **cannot** be converted to a completed binding. The pending journal and anything remaining on disk are preserved for separate recovery inspection. Even a normal guard exit returns `REPLACED_RECOVERY_REQUIRED`, **not** committed, bound, durable, synchronized, or safe to expose.

## Native security limits and explicit missing qualifications

`FileRenameInfoEx` is required because legacy `MoveFileExW` can refuse replacing an open destination even when its handles share delete access. An unsupported kernel/filesystem must fail closed: never release the 3G5 evidence handles to force a rename, retry, or fall back to copy/delete. This slice does **not** establish a crash-durable parent directory entry, power-loss survivability, portable atomic multi-file transaction, independent journal admission, exact expected-revision CAS against hostile same-OS-user writers, or crash-safe descriptor completion. In particular, the old live registry is replaced **before** descriptor change, so the previously recorded pending journal is mandatory recovery evidence. No journal retirement or temporary cleanup occurs.

Successful internal testing does **not** authorize integrating this helper into a teacher-facing command: explicit teacher confirmation, native custody/authority and an end-to-end transaction coordinator with crash recovery remain unimplemented. The absence of a returned commit token is deliberate. Linux/macOS are refused, not silently emulated. The Windows native scratch test uses temporary synthetic files only, independent of the teacher-private root, and tests `FileRenameInfoEx` with both original and staged files held open. The test must not be skipped on supported native Windows. Synthetic unit tests do not qualify power-loss semantics.

## Qualification gates

- Exact baseline Git feature/main and pinned baseline blob verification before any files are applied.
- Exactly three additive files: internal low-level helper, synthetic+Windows scratch native regression tests, this audit.
- 3G6 tests, focused Core #238 pytest selection, Ruff lint+format, strict mypy, full Core pytest integration checkpoint.
- Conditional commit and push only after all gates; failures preserve checkout and evidence, never reset or stash.
- The installed-wheel, Linux/macOS, native power-loss, and production teacher-decision integration gates remain independent and unqualified.

No `notes.records.v1`, `notes.menu.v1`, `notes.cli.v1`, or `notes.portability.v1` capabilities are advertised.

## Windows native scratch finding and corrective protocol

The original 3G6 Windows test proved that `MoveFileExW` is not a suitable writer inside the 3G5 retained-handle scope: the real scratch test returned failure with open old-target and stage handles. That was a **real native test failure**, not a pytest or formatting issue. This revision uses the Win10+ `FileRenameInfoEx` class with POSIX replacement semantics. It opens a *separate* DELETE-capable stage handle with `FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE`, holds the existing 3G5 evidence handles, builds an explicit UTF-16 `FILE_RENAME_INFO` buffer, and makes one native call. No fallback, retries, handle release to bypass a refusal, journal retirement, or destructive cleanup. An unsupported filesystem/OS returns a recovery-required status. No write-through/power-loss durability claim is made.

Official Win32 reference: https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info ; comparable supported implementation: Git for Windows `compat/mingw.c` uses `FileRenameInfoEx` with `FILE_RENAME_FLAG_POSIX_SEMANTICS`.
