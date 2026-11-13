# Core #238 — Slice 3G31: Two-root native prepared-stage replacement

**Scope:** synthetic-only operation, unchanged production implementation, no Notes activation.

## Purpose

Extend the 3G29 writer-owned parent custody exercise from a single scratch
folder to the recovery layout's two conceptual roots. The internally generated
`TemporaryDirectory` contains separate `private/` and `workspace/` directory
hierarchies, with `private/transactions/pending-transaction.json`,
`private/registry.json`, a staged registry image,
`workspace/.pds/teacher-private-association.json`, and a scratch lock.
The exact fixture bytes are fixed in the existing synthetic writer module.
The caller cannot supply roots, bytes, a journal, a handle, a callback, or a
transaction capability.

## Operation-owned sequence

1. Validate an exact stage-to-registry enum; reject initialize, descriptor
   completion, journal retirement and invalid requests before any filesystem IO.
2. Create only internal disposable synthetic roots and fixed images.
3. Acquire a local scratch lock; retain native directory FD/HANDLE custody of
   **all four** parent directories with 3G29's internal native helper.
4. Under that same scope, verify exact per-directory names, regular one-link
   files, bytes, native file identities, four distinct parent identities,
   and pending-journal/descriptor immutability.
5. Open the registry with the 3G24 restrictive Windows read-only sharing mask
   (`FILE_SHARE_READ`, not delete sharing), verify its native identity and
   exact bytes, **close it**, then revalidate admission three times.
6. Attempt exactly one native `os.replace(stage, registry)` under the same
   scratch lock and retained parent handles. No retry or alternate mutation.
7. Verify registry identity equals the former staged file's identity, the old
   registry is not the new file, the staged pathname disappears, and the
   pending journal, descriptor, lockfile and all parent IDs remain stable.
8. Request target-file sync and recheck the postimage; close all handles.
   Keep the pending journal; do not retire or erase it.

## Refusal and interruption

- Exact input types and operation selection are checked before scratch IO.
- Distinct sanitized states identify namespace drift, unsafe parent or file
  identity, image drift, restrictive-reader conflict, admission drift, native
  replacement refusal, postimage conflict, lock refusal and IO refusal.
- Interruption injection exists at nine named boundaries, including after
  replacement, sync and handle release. No interrupted state is success.
- ExitStack ensures four parent FD/HANDLEs close on every return/exception;
  the scratch lock is released on all paths. No source or operation capability
  escapes via the result.

## Qualification

- Isolated Linux surrogate run: 73 passed, one Win32-only native rehearsal
  skipped. The Windows runner reruns the Win32 case using the true committed
  `CreateFileW` parent opener, not an emulated handle.
- Full focused Core #238 tests, Ruff and strict mypy must pass on Windows
  before the runner can commit/push three new files. The full repository
  pytest checkpoint was green at 3G30: 6,191 passed, 176 skipped; it is not
  repeated automatically at this slice.

## Explicit non-claims

This exercise does **not** use the real native owner/SID and ACL custody
protocol, fixed local backing verification, protected production roots,
canonical teacher transaction intents, production journal writers, or a
production registry replacement. The scratch lock is advisory and not a
compare-and-swap primitive against hostile or noncooperating actors. A target
file sync is not proof of durable directory entry, crash consistency or
power-loss durability, and process interruption injection is not a real crash.
No output is transferable authorization to write protected data. Actual
production mutation, journal retirement, initialization, descriptor completion,
and Notes activation remain explicitly prohibited.

## Follow-on acceptance target

3G32 should introduce a bounded, typed, *inert* protected write-intent
interface compatible with the owner-held 3G30 guard and with the two-root
3G31 fixture, without executing on caller-provided production paths. Before
opening a production writer, demonstrate operation-owned native owner and ACL
checks, no ambiguous namespace windows, exact pre/post-image verification,
and a qualified durable recovery/retirement protocol.

### Windows locked-byte compatibility (3G31 repair)

The scratch lock manager writes a fixed one-byte sentinel before acquiring a native
byte-range lock. Under Win32 `msvcrt.locking`, a **second file descriptor** cannot
read that locked byte. The original evidence census attempted such a read,
causing a Windows `PermissionError` that the guard mapped to `GUARD_REFUSED`.
The corrected census retains the native lock and checks the lockfile with `lstat`
(regular file, one hard link, exactly one byte), and compares its native file
identity throughout the operation. Registry, staged registry, journal, and
workspace descriptor are still checked against their exact original bytes.

The correction does not turn a filesystem advisory lock into hostile-writer
exclusion, production ownership validation, a commit permit, or durability. A
new regression test rejects an attempted reread of the locked byte, and separate
tests require exact lockfile shape and fail-closed pre-replacement behavior.
