# Core #238 — Slice 3B2: read-only Windows native ACL refusal preflight

**Pinned source predecessor:** `7fb15f0c77798066f85ee65ba6655ba04ad80241` (#238 Slice 3B1).
**Design:** [private-storage v1 contract](../teacher_private_storage_contract_v1.md), [threat model](../security/teacher-private-storage-threat-model.md), and accepted teacher-experience conformance P01–P03/P05.
**Scope:** A Windows-native **refusal** layer for an already-existing prospective private directory. No protected creation, Notes records or Notes capabilities. D0 storage-activation approval remains outstanding.

## Delivery boundary

- Add `_teacher_private_windows_preflight` for read-only native Win32 handle inspection. It reads the **actual opened directory handle** with `GetFileInformationByHandleEx` and `GetSecurityInfo`. Each component is opened with `FILE_FLAG_OPEN_REPARSE_POINT` so the *opened component* can be rejected if it is a junction or other reparse point. The routine never opens a handle for writing or changes an ACL.
- For the application-local suffix, inspect the owner SID and standard access/deny ACL entries. Only the current process-token SID (from Slice 2), LOCAL SYSTEM, and Administrators are considered potentially acceptable allow trustees. Any other allow trustee, missing owner rights, deny/callback/object/unknown ACEs, unknown owner or NULL DACL causes **refusal**. This intentionally rejects some otherwise legitimate directories rather than attempt a partial effective-access computation.
- Integrate this native check from `_teacher_private_native_preflight.inspect_native_private_preflight()` **only on Windows** after Slice 2's preliminary non-mutating inspection has reported `PRESENT_UNVERIFIED`. Linux retains its existing directory-FD/no-follow/ACL path; macOS remains `UNSUPPORTED` pending native implementation.
- Return only `NativePrivatePreflightState` with sanitized messages. **`RESTRICTIVE_UNQUALIFIED` is not READY, a durable capability, nor approval to write.** Handles are closed before returning; TOCTOU, effective inherited/group rights, app-data locality, share/mount semantics, future ACL changes and concurrency are not qualified.
- No public Notes storage service, `teacher_context`, menu/CLI, `notes.records.v1` or workspace sidecar. Existing `.pds/workspace.json`, roster data and producer ownership are unchanged.

## Security limitations and D0 gate

The Windows probe is a defensive *rejection filter* rather than a complete Windows authorization or private-directory creation implementation. An ACL with only the recognized principals is **not proven safe merely by these observations**: full effective-access evaluation, path ancestor integrity, native handle lifetime, Win32 creation-time security descriptors, explicit local-backing verification and coordinated writes remain prerequisites for later slices. This slice does not authorize storage creation even with `RESTRICTIVE_UNQUALIFIED`.

The Windows API paths and result semantics must be qualified **on a genuine Windows runner**; pure Linux mocks test the classifier and call boundary, not Windows DACL correctness. A subsequent installed-artifact/native security test must record exact OS/Python/build and compare refusal semantics under controlled ACL fixtures. Native Windows ARM64, macOS and real district machine tests remain separately unqualified until executed. No claim of published `pds-core` 0.6.6 change is made.

## Executable source tests

`tests/test_teacher_private_windows_preflight.py` exercises synthetic owner/DACL examples: allow-only current owner/System/Admins remains unqualified; Everyone, Authenticated Users, Users, application packages, foreign users, Creator Owner, deny, callback/object ACEs, insufficient owner rights, mismatched owner, invalid Windows path syntax, and explicit Windows-branch dispatch. Native Windows-only tests assert that missing and existing temporary directories are only inspected, never created or authorized for private record writes. Existing `test_teacher_private_native_preflight.py` retains its non-Windows rejection and uses a mock Windows native result to test its historical synthetic platform vector.

Before commit, run focused tests (Windows classifier and prior private-storage/workspace/terminal regressions), full pytest, Ruff, strict mypy and Git scope/whitespace checks. No run is considered executed merely because this document describes it. Full GitHub PR CI and native installed-wheel qualification remain subsequent gates.
