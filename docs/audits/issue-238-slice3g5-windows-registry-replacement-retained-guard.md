# Core #238 Slice 3G5 — Windows native registry-stage replacement guard

**Baseline:** `6c0b17517293f314f338249bc392fe5b30cf0b53` (qualified 3G4)

## Scope

Internal **Windows-only, mutation-aware retained observation scope** for one future
stage-to-`registry.json` replacement. This is **not** a write service, CAS
reservation or authority, journal admission, durable commit, recovery writer,
record store, public Notes API, or production-supported binding feature.

The earlier immutable `retained_registry_guard` is intentionally **excluded**:
its contract requires that the named live registry file ID and timestamp
remain unchanged, which a legitimate stage replacement cannot satisfy.

## Preconditions and retained native identity

1. Require Windows and canonical non-`INITIALIZE` transaction intent, existing
   qualified root requests, and the exact ordered pair of existing local locks.
2. Hold the transactions journal directory and the workspace descriptor using
   their independent retained native guards. Neither is expected to change.
3. Open and retain *separately* the protected parent-directory handle, existing
   `registry.json` handle, and transaction-specific stage handle. Existing
   `_windows_open` requests `FILE_SHARE_READ|WRITE|DELETE`, which permits a
   cooperating rename while retaining object identity; this does not exclude
   hostile same-OS-user or cloud writers.
4. Verify fixed local backing, current path/DACL protections, unique distinct
   old/stage file IDs, no reparse/directory/delete-pending file, one link, and
   parent volume agreement. Require exactly one pending journal and one named
   matching stage; refuse any other stage-like namespace entry.
5. Verify symmetric native journal, registry, descriptor and stage byte images
   before yielding to the caller: exact proposed canonical journal, exact
   before-images and exact staged registry after-image, without reacquiring
   ordered locks.
6. After the caller exits normally, verify owner identity, exact stage removal,
   no competing entries, qualified empty stage inventory, unchanged journal
   and descriptor, and live registry bytes exactly matching the after-image.
7. Independently compare retained source/stage/parent FILE_ID identities; ensure
   `registry.json` now resolves to the *original stage's* FILE_ID, the old
   registry handle still identifies the prior object, the stage path is absent,
   and the directory remains the same protected native object.

No payload is written by this module. The context manager returns no handle,
path, transaction token or mutation capability. An exception during the caller
body is propagated and preserves all evidence without rollback or cleanup.

## Deliberate limitations

- This scope can observe a **lock-honoring local** expected replacement, not
  prevent all same-user interference or form a distributed filesystem CAS.
- There is no provided `ReplaceFileW`, `MoveFileExW`, `os.replace`, registry
  write, directory fsync, journal retirement, descriptor replacement, recovery
  replay or first-binding creation in this slice.
- The file-ID check is supplemental evidence, not stable logical workspace
  identity or proof of durable persistence. Native write-through/flush ordering,
  crash recovery and the precise transaction commit point remain unqualified.
- **Linux and macOS are unsupported** by this Windows-only scope. Native Windows
  synthetic qualification does not imply live filesystem mutation testing.
- Existing implementation capabilities remain **only**
  `terminal.header.v1` and `terminal.notes_command.v1`. No Notes records or
  UI/CLI/portability capability is activated.

## Verification and next slice

26 synthetic tests passed in an isolated harness before packaging. The guarded
3G5 runner requires exact baseline/remote/blob pins, three additive files,
Ruff-checked and AST-invariant formatting, focused pytest, strict mypy and a
full Core pytest integration run before conditional commit/push. Real Windows
qualification remains pending until the user's runner completes.

The subsequent implementation must define the native replacement **writer**
and its flush/crash/recovery protocol under these retained checks. The guard
alone is not sufficient to authorize it. A separate Linux-native guard must be
qualified rather than assuming Windows handle semantics carry over.
