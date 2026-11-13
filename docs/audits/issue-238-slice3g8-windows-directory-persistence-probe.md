# Core #238 — Slice 3G8: Windows registry directory-entry persistence probe

**Qualified baseline:** Core #238 3G7 `c4ca1c47046af43b2ba35d6da76da3017a005c85` (full Windows suite: 4,587 passed; 174 skipped; strict mypy and Ruff passed).

## Narrow change

Add one internal, opt-in Windows **parent-directory `FlushFileBuffers` probe**, following the earlier 3G6 native registry `FileRenameInfoEx` attempt and 3G7 registry-file flush checkpoint. This checks an additional native behavior but does **not** establish power-loss or directory-entry persistence. Some Windows filesystems refuse directory handles for `FlushFileBuffers` (or do not provide a documented persistence guarantee for the registry rename even if the syscall succeeds). That is a **recovery-required** result, not permission to drop the journal, downgrade the protection, or replace the API with a less safe fallback.

The entry point accepts only a canonical existing, non-`INITIALIZE` transaction intent and previously validated native private/workspace root requests. Existing ordered locks and the protected journal/registry/descriptor handles remain retained throughout: read exact pending transaction and absent-stage namespace, native registry and descriptor after-image observation, probe native protected private-root directory handle, then recheck owner, namespace, native image state, stage absence and retained-guard postconditions. The probe uses `CreateFileW` with `OPEN_EXISTING`, `FILE_FLAG_BACKUP_SEMANTICS`, `FILE_FLAG_OPEN_REPARSE_POINT`, narrow rights, `FILE_SHARE_READ|WRITE|DELETE`, `FlushFileBuffers` at most once, native FileIdInfo and restrictive DACL checks. It never creates a directory, mutates registry or descriptor bytes, deletes a stage, or retires a journal.

## Crash/interruption decision table

| Observation window | Classification / required action |
| --- | --- |
| Before stage-to-registry replacement; stage still present | Refuse; 3G2 pair checkpoint and recovery review remain owners |
| Stage missing; registry still before-state | Refuse; stage absent is NOT evidence that replacement happened |
| Stage absent; descriptor-only after-state | Refuse; conflicting partial transition needs recovery review |
| Stage absent; registry after-image and descriptor before-image, exact journal | Directory probe permitted; whatever syscall result, descriptor completion and durability remain unqualified |
| Stage absent; both after-images, exact journal | Directory probe permitted; whatever syscall result, journal retirement and durability remain unqualified |
| Parent directory open, DACL, FileIdInfo, local volume or flush refused | `DIRECTORY_FLUSH_UNAVAILABLE_RECOVERY_REQUIRED`; preserve all evidence |
| Parent directory FlushFileBuffers returns success and identity remains stable | `DIRECTORY_FLUSH_OBSERVED_DURABILITY_UNQUALIFIED`; **not** a durability/commit token |
| Journal/registry/descriptor drift, stage appears, owner changes, native guard postcondition refuses | Fail closed; no positive result may escape |
| Process or power loss before/during/after any native probe | Next open MUST independently reclassify disk and journal state; never infer progress from prior return value |
| Network/cloud/mounted/removable backing; unsupported Windows API or ACL | Refuse, no unsafe fallback or auto-repair |

A Windows directory flush is not a **portable, independently validated** durability barrier for `FileRenameInfoEx`; tests against synthetic scratch files cannot reproduce power cuts, storage-controller caches, OneDrive sync, or hostile same-user interference. This slice cannot claim an atomic two-file registry+descriptor transaction or durable revision CAS.

## Test and qualification gates

The tests cover non-Windows refusal, invalid inputs, both permitted after-images, exact namespace / journal and stage evidence, refused before/partial states, owner/namespace/metadata/guard drift, native directory open/write access restrictions, FileIdInfo and DACL verification, single syscall attempt with cleanup, and no elevated Notes capabilities. One Windows-native scratch test opens a temporary disposable directory and attempts `FlushFileBuffers` with the production rights/flags; **either supported success or a native refusal is acceptable** as long as the directory identity and scratch bytes remain unchanged. No teacher-private data is used in the scratch test.

Required full Windows qualification: test module, 60-file focused #238 suite, `ruff check .`, `ruff format --check` on new files, strict `mypy .`, full `pytest -q`; verify exact baseline Git tree and remote refs before application, stage only three additive 3G8 files, commit/push only if every gate passes. The existing public teacher capability set remains `terminal.header.v1`, `terminal.notes_command.v1`; no Notes records/menu/CLI/portability or private backup are enabled.

**Next protocol boundary:** a reviewable, platform-specific crash recovery controller for registry/descriptor reconciliation, with independent durability evidence. No journal retirement or successful binding may be implemented simply because 3G7 and 3G8 returned positive advisory statuses.
