# Core #238 — Slice 3F0: Windows write-through on exclusive journal creation

**Base:** `109a9f825310c6798d709c84abea929790f9e36e`.

This limited change requests `FILE_FLAG_WRITE_THROUGH` (0x80000000) for the Windows
**journal-intent candidate** created by the existing protected DACL / `CREATE_NEW`
primitive. Unrelated protected registry/workspace lock creation keeps its exact
former default `FILE_ATTRIBUTE_NORMAL` (0x80). The intended journal-specific
creation flags are 0x80000080; the original exclusive-create sharing, DACL,
owner checks, fixed-local backing, `WriteFile`, `FlushFileBuffers`, and failure
preservation remain unchanged. Linux behavior remains unchanged.

Microsoft's `CreateFile` documentation states that write-through requests cause
NTFS to flush metadata changes associated with a request. `FlushFileBuffers`
flushes the file handle's buffered data but is not a documented substitute for
POSIX parent-directory `fsync` in a multi-file transaction. These descriptions
are **not** proof of complete Windows namespace/power-loss durability, and this
slice does not claim that an intent candidate is durably admitted.

- There is no public storage or Notes service.
- No registry or workspace descriptor may be written by this change.
- Any failed candidate remains untouched for explicit recovery review.
- A candidate state continues to be `CREATED_UNQUALIFIED`, never `READY`.
- The 3E9 retained guard, before-byte checks, journal census and post-read
  comparison remain required.
- Native Windows CI qualification must confirm the flag is supported on its
  fixed local test volume; this source change alone cannot establish that
  hardware and filesystem flush semantics survive real power loss.

**Acceptance evidence:** regression tests prove write-through is opt-in,
legacy calls retain default flags, an invalid principal is refused,
and the journal creation path explicitly requests the flag. Existing
native journal-creation tests and the entire Core pytest suite must remain
passing. Future work must address namespace-durability evidence, metadata
write targets, exact-before CAS, crash recovery and installed wheel acceptance.

**References:** Microsoft Learn, CreateFileW / file buffering / write-through,
`https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew`;
Microsoft Learn, FlushFileBuffers,
`https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers`.
