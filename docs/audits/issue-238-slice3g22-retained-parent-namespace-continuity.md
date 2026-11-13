# Core #238 — Slice 3G22: Retained parent-directory continuity

**Status:** guarded native Windows qualification candidate. No production writer.

## Boundary

A new private module performs three consecutive **read-only** recovery observations under **one existing** retained descriptor/journal/registry guard. The observation adds parent-directory path identities for the private root, pending-journal `transactions` directory, workspace root, and workspace `.pds` directory to the 3G21 exact-file identity and canonical byte-image review. The module reports only sanitized enums and fixed text. It accepts no callback, external file handle, writer token, optional mutation operation or transaction enactment capability.

Three observed frames delimit **observation boundaries**, not a writer operation. A stable result is advisory only. No production file changes are performed, journal retirement cannot occur, and Notes remains disabled.

## Guard sequence

1. Validate a canonical proposed transaction intent, non-initialization operation, expected revision, existing requested roots, and exact proposed step before entering a native guard.
2. Hold one `retained._hold_existing_retained_descriptor_guard` scope; acquire the owner's current native identity and exact pending journal/stage namespace.
3. In each of three rounds: requalify native namespace and owner; census the four parent directory pathname identities; take the 3G21 native file-ID census; classify the native pending checkpoint; read the exact native journal, registry, descriptor and optional stage bytes; then requalify native namespace and owner. No nested lock acquisitions.
4. Check round-to-round parent identities, file identities and bytes, exact checkpoint and revision, and sizes. A difference refuses the observation; no success token exists.
5. Before releasing the guard, recheck native namespace, owner and all four parent identities. Guard-release failure supersedes advisory success.

## Native custody limitations

The `Path.lstat` parent census is intentionally **supplementary** to the existing retained native directory and file handles. On Windows, CRT `os.open` cannot be assumed to open directories; the previously qualified retained guards own the platform HANDLE and ACL checks. On Linux, the retained guard owns descriptor and parent-FD checks. Two pathname reads cannot alone prevent hostile same-user races, reparse-point attacks, path substitution between operations, cloud/sync interference or noncooperating processes. The native guard remains the stronger independent requirement, and 3G22 returns no file IDs, bytes, handle references or paths.

An observed stable parent path is not proof of future path stability, continuous handle ownership across a real rename, parent-directory persistence, power-loss durability, journal absence custody, distributed CAS or a committed metadata binding. The stage-to-registry write, descriptor write, journal retirement, initial binding and Notes capability activation are all out of scope. The `REVIEW_JOURNAL_RETIREMENT` proposed step is treated exclusively as an **observation** of a pending journal; it is never a retirement action.

## Regression and qualification

The new isolated test module exercises all three checkpoints; three observation rounds and a final parent check; four parent-identity drift positions; byte-identical file replacement; byte changes with unchanged IDs; namespace, owner, checkpoint, size, interruption, access and retained-guard release refusal; sanitized result contracts; real temporary parent path and symlink/ordinary-file checks. Tests use only fixture data, never teacher-private metadata.

The guarded Windows runner must validate exact feature/main remote heads, the 3G21 commit, 169 inherited Git blob IDs, clean checkout, the SHA-256 source archive manifest and exact three additive files. After applying candidates, run 3G22 tests, 74-file Core #238 focused regression selection, Ruff check/format and strict mypy. Defer full Core pytest following the green 3G19 integration checkpoint (5,415 passed, 174 skipped). Auto commit/push only on all-green gates. Failure leaves exact candidate files in place; no reset, stash or cleanup.

## Next needed

3G23 should test the limits of a *prospective* writer-owned native mutation window and the differences between open-handle custody, pathname qualification and target replacement. It must still refuse production mutation until fully qualified durable commit, directory persistence, recovery replay and cross-tree CAS are designed and verified independently.
