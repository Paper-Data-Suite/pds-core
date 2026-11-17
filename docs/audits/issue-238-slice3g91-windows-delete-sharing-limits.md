# Core #238 — Slice 3G91: Windows native delete-sharing, scratch only

## Purpose and trust boundary

3G89 and 3G90 established that Linux handle-relative rename and `renameat2`
filename flags do not provide a kernel compare-and-swap on previously checked
file content. 3G91 independently qualifies one *Windows-specific* file-handle
sharing property: opening a real existing file using `CreateFileW` with
`FILE_READ_ATTRIBUTES` and `FILE_SHARE_READ | FILE_SHARE_WRITE`, **without**
`FILE_SHARE_DELETE`, blocks a competing process's ordinary `os.replace` when
that process needs delete/rename access to the held file. The held handle's
share flags remain effective until `CloseHandle`. See Microsoft's official
`CreateFileW` documentation (Win32 share mode, `FILE_SHARE_DELETE`).

The diagnostic owns all file names and constant payloads inside a fresh random
scratch directory. Its only public input is a fixed scenario enum. It does not
accept caller paths, credentials, handles, transactions, buffers or callbacks.
The existing cooperative lock and a retained native parent DIRECTORY handle
span the entire synthetic experiment.

## Independent native Windows qualification

For both `live_handle_deny_delete` and `stage_handle_deny_delete`:

1. Create fixed synthetic live registry, stage and pending journal in scratch.
2. Retain a `CreateFileW` handle to the selected entry **excluding** delete
   sharing. A separate interpreter ignores the cooperative `.registry.lock`
   and attempts a single `os.replace(stage, live)`.
3. Require the independent interpreter to report a Windows access/sharing
   refusal, and verify that both original entry images and the pending journal
   remain unchanged.
4. Close only the deny-delete file handle; retain the cooperative lock and
   parent handle. Retry the **same** child operation. Require the replacement to
   succeed and verify exact stage-after contents and the untouched journal.

The post-close success is critical: it rules out an apparent protection result
caused by unrelated permissions, bad paths, or a permanently failing call.
All child outputs and review fields are fixed sanitized labels; no paths,
owner identities, OS error messages or teacher data escape.

## Nonclaims and refusal boundary

- This qualifies a **specific Windows share-mode behavior against ordinary
  path-based replacement**, not a kernel content-CAS or an unqualified security
  guarantee against all APIs, privileges, network filesystems or same-owner
  malicious code. Hostile processes may replace or modify other files, may
  have opened handles before the guard, or use other mechanisms.
- The diagnostic itself is **not a handle-relative Windows replacement**.
  Windows source/destination path stability, final atomic conditional update,
  multi-document transaction, owner ACL, real journal recovery and crash
  durability remain unqualified.
- Linux explicitly refuses the Windows-only protocol without creating scratch.
  Unsupported contexts, unexpected Windows file-sharing results, drifted
  requirement taxonomy, subprocess errors and malformed scenarios fail closed.
- No real private-root or workspace file is accessed, production write enabled,
  journal retired, automatic replay started or Notes record activated.
  All nine production-operation requirements remain unqualified.

## Qualification and next engineering gate

The new focused tests check Windows source and destination handle scenarios,
Linux explicit refusal, invalid inputs and unchanged negative capability set.
The twenty-third isolated installed-wheel gate repeats native Windows cases,
Linux refusals and the immutable no-authority evidence, while preserving all
22 predecessor gates. The guarded runner requires exact branch, committed
baseline, CI blob, clean tree, unique destination paths and scoped five-file
change before qualification and conditional commit/push. No reset/stash/cleanup
on failure.

Next: investigate a Windows native handle-directed replacement protocol and
crash-recoverable journaling, explicitly distinguishing **cooperating processes**
from arbitrary mutation by code with the same OS-account privileges. Do not
reclassify a successful native scratch experiment as production authorization.

References: Microsoft's Win32 CreateFileW documentation:
https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
and moving/replacing files documentation:
https://learn.microsoft.com/en-us/windows/win32/fileio/moving-and-replacing-files


## Slice 3G91 Repair 1 — direct native DELETE-access sharing qualification

Windows source tests stopped before type checking, wheel installation, commit or
push: the `stage_handle_deny_delete` case returned a sanitized
`native_sharing_refused` result. The original probe inferred Windows sharing
behavior from the outcome of `os.replace`, conflating CreateFileW sharing rules
with the different preconditions and possible failures of MoveFileExW.

The repair narrows that claim instead of accepting an unqualified rename error.
While a synthetic handle excludes `FILE_SHARE_DELETE`, a fresh interpreter now
uses CreateFileW to request *DELETE* access to exactly that same scratch file.
Only `ERROR_SHARING_VIOLATION` (32) is accepted as an actual sharing denial;
access denied, unexpected success, or another error are refused. After the
parent releases its handle, another interpreter must obtain the same native
DELETE access successfully, close it, and then perform the synthetic registry
replacement. Exact before/after images and the untouched pending journal are
still checked. Both live-target and staged-source cases use this same precise
native contract. Two independent child processes per scenario are retained.

This is intentionally a narrower qualification: it proves that an open handle
without FILE_SHARE_DELETE prevents another ordinary opener from acquiring
DELETE access; it does **not** prove that all `os.replace` paths have the same
error behavior, that a shared lock excludes a same-owner attacker, or that
Windows grants atomic conditional replacement. Original tests, installed-wheel
schema/checker, CI workflow, and all twenty-three native gates are unchanged.
The temporary root, caller input boundary and nine production blockers remain
unchanged. Production binding, replay, journal retirement and Notes stay denied.


## Slice 3G91 Repair 2 — use FILE_READ_DATA to enforce delete sharing

Repair 1 again stopped at native Windows pytest before wheel/type checks or
commit/push. A narrowly instrumented native diagnostic obtained the cooperative
lock, a held parent-directory handle and the watched-file handle for **both**
registry and stage scenarios, but a separate interpreter requesting `DELETE`
access was unexpectedly granted while the watched handle was still open.
The Windows API sharing rule therefore did **not** produce the intended conflict.

Root cause: the watched parent handle requested only `FILE_READ_ATTRIBUTES`
(`0x00000080`). Windows filesystem sharing conflict accounting excludes attribute-
only opens and instead counts rights such as `FILE_READ_DATA`, `FILE_WRITE_DATA`,
`FILE_EXECUTE` or `DELETE`. Microsoft MS-FSA 2.1.5.1.2.1 / 2.1.5.1.2.2 describes
this distinction; `CreateFileW` documents that attribute requests are not
subject to the normal read/write/delete sharing flags. The native diagnostic
therefore exposed a probe bug rather than an OS sharing violation.

This repair changes precisely the watched-file `CreateFileW` desired-access
argument from `0x80` (`FILE_READ_ATTRIBUTES`) to `0x0001` (`FILE_READ_DATA`).
Its original `FILE_SHARE_READ | FILE_SHARE_WRITE` (`0x3`) flags remain unchanged,
so `FILE_SHARE_DELETE` is still excluded. The child continues to request native
`DELETE` access and only accepts Win32 `ERROR_SHARING_VIOLATION` (32); it must
succeed after the watcher closes and then perform the synthetic replacement.
Tests, independent installed-wheel checker, all twenty-three CI gates and
other source code are unchanged. The exact five-file stopped Repair 1 worktree
is preserved and guarded by AST, source-comment and audit comparisons.

This remains a disposable Windows sharing experiment. It does not establish
atomic content CAS, resistance to arbitrary same-owner code, durability,
recoverable multi-document transactions, production write admission, binding,
automatic replay, journal retirement or Notes availability. All nine production
operation requirements remain unqualified.

References:
- https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-fsa/82b364ce-6d7b-422f-8d88-4db32eea809a
- https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-fsa/8c0e3f4f-0729-49f4-a14d-7f7add593819
