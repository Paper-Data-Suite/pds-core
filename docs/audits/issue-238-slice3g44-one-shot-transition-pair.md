# Core #238 — Slice 3G44: one-shot native transition-pair custody

## Baseline and qualification

- Feature baseline: `d4a15edb32cd45da0e5a5bff625c05a151b9c975` (qualified 3G43).
- At preparation, `main` remains `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`.
- Core #238 is a private teacher storage and workspace-association boundary, **not** Notes CRUD, public Notes readiness, or backup/portability.
- 3G40 full Windows regression checkpoint: 6,864 passed, 179 skipped. Focused Core suite, Ruff and strict mypy are qualification gates for this slice.
- No protected production file is modified or created by this slice.

## Reason for this separate scope

The existing 3G42 `_held_registry_stage_pair` intentionally demands that the old registry and prepared stage remain at their original names when exiting. The 3G43 admission review correctly uses that immutable scope and returns only a snapshot after release. However, a real operation that installs the staged registry needs **different exit semantics**, since the stage's original file identity is supposed to replace the old registry entry. Using the 3G42 immutable context around a production `os.replace` would deliberately refuse even the intended result.

3G44 introduces `_held_one_shot_transition_pair` as a separate, **internal** native custody scope. It retains the protected old registry, prepared stage, and parent native handles with Windows `FILE_SHARE_DELETE` semantics or Linux `O_NOFOLLOW`/native FDs. The held old/staged file IDs remain distinct. On entering, the stage must still be prepared and the target unchanged. The private `_AttemptWindow.mark_attempt()` accepts exactly one *intent to attempt*, and only after a fresh native PREPARED check. It does not execute a syscall. On scope release, unmarked windows require the PREPARED state. Marked windows require the exact original stage file ID installed at `registry.json` with the old retained handle stable. A marked attempt with the original PREPARED entry still in place is rejected and must preserve pending evidence; it is not safe to replay. All other identities or native protection failures are refused. Stage missing while old registry remains is a refusal. The window is invalidated on exit and cannot be replayed.

The pre-attempt PREPARED and post-attempt installed states deliberately **do not establish transaction success**. An attempted operation that still appears PREPARED is refused, not declared safe to retry. The installed native identity is not proof of the correct canonical byte image, descriptor completion, directory durability, or safe journal retirement.

## Security and interface boundaries

- Private helper only: no path, native handle, write callback, approval flag, or mutation token is returned from a public Core API.
- Never call `os.replace`, `MoveFileExW`, `ReplaceFileW`, unlink, rename, truncate, create, flush or retire journals. No private-store mutation in the new module.
- The wrapper is NOT a standalone admission gate. Its future caller must nest it *inside* 3G41 ordered coordination and descriptor/journal custody, validate 3G43 canonical owner/binding/currentness, revalidate exact images immediately before the one permitted attempt, and check exact native and byte postimages **within** the still-held scope.
- On exceptions or incomplete outcomes the parent transaction must preserve journal and stage evidence and require restart recovery; it cannot replay the attempted operation based on this scope's return value.
- Windows delete-sharing behavior remains a native Windows qualification requirement. Linux uid/mode/ACL/local backing checks are reproduced from the 3G42 retained-handle boundary. macOS is unqualified and refused.
- The 3G35 production write barrier remains unchanged, and no Notes, Tasks, or general binding write capabilities are exposed.

## Test matrix

Unit tests cover unmarked/marked terminal outcomes across all native identity states, inability to mark a second attempt, refusal to mark a non-PREPARED native observation, post-exit invalidation even on failure, redacted exceptions/representation, type-unsafe sizes, unsupported OS, and the inner scope's guard lifetime. Independent local isolated tests use dependency stubs; native Windows and strict mypy must be verified by the guarded Windows runner.

## Still required before any production replacement

A caller must own complete canonical transaction and revision CAS checks, exclusive two-root coordination, protected native parent and file handles, exact prepared journal/stage/descriptor/registry images, one-shot native operation, postimage and sharing verification on both OSes, properly ordered file and directory durability, crash recovery for all interruption windows, explicit journal retirement, installed wheel qualification and supported native-platform evidence. The current slice does **not** authorize, execute or persist a production transition.
