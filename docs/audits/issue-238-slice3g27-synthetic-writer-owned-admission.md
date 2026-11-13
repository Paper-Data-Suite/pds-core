# Core #238 Slice 3G27 — Synthetic writer-owned admission sequence

## Change

Add one non-public scratch-only coordinator for a single **stage-to-registry** operation. Its only input is an exact step enum and a cooperative interruption enum. Neither a production path, byte payload, transaction/witness, callback, HANDLE, nor a write token can enter. The operation is *not* exposed as an authorized production API.

Within one internally allocated, disposable temporary directory, it:

1. creates four fixed non-sensitive images (registry, stage, descriptor, pending journal);
2. acquires one native scratch advisory lock and captures exact native file and parent identities;
3. reads the registry through the existing **restrictive Win32 reader** (or an ordinary read-only Linux file) and completely closes it;
4. revalidates namespace, bytes, stage and other file IDs, lock identity and parent identity in **three successive frames** under the same scratch lock;
5. attempts **one** native `os.replace` from stage to registry, without fallback, cleanup or retry;
6. verifies the expected new registry ID equals the previous stage ID, that the old registry ID is gone, and descriptor/journal/lock/parent identities are unchanged;
7. requests a file-only fsync, then rechecks the postimage and required operation sequence before releasing the scratch lock.

Initialization, descriptor completion and journal retirement are refused before filesystem access. Failures, partial outcomes and interrupted phases never become completion evidence. Tests exercise native scratch operations, exact ordering, postimage tampering, identity drift, refusal and cleanup.

## Explicit limits

This is **not** a production mutation writer. It does not use production retained descriptor/journal/registry guards; it does not provide a filesystem CAS, true cross-machine exclusion, cloud currentness, ACL/owner validation of teacher data, durable parent-directory replacement, replay/restart authority or a Notes record service. The fixture lock coordinates only participants honoring that scratch lock. A process crash or power loss is not simulated by cooperative exceptions. File-only sync does not establish namespace persistence.

The existence of this module cannot be used to enable teacher-private changes or retire a journal. A future implementation must integrate genuine guarded native production preconditions and a qualified persistence/recovery protocol in **one** writer-owned operation. Do not delete or shortcut earlier infrastructure to accomplish that.

## Qualification

Run dedicated tests, focused Core #238 regression suite, Ruff and strict mypy against the exact qualified 3G26 branch. No need for a full Core suite every slice; the last periodic full checkpoint passed at 3G24 (5,749 passed, 176 skipped).
