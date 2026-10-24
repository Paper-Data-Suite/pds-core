# Core #238 — Slice 2: Non-mutating local owner and private-root inspection

**Source baseline:** `4e5af83d62f0581a1da488489dd250e24850ea3a` (Slice 1).
**D0:** Contract/threat model remain an owner-review candidate; Slice 2 is a read-only probe, not an authorization to create private storage.

## Boundary implemented

`pds_core._teacher_private_inspection` is deliberately **private and read-only**. It obtains the current process-token SID from Windows native APIs (refusing active thread impersonation) or the effective UID on Linux/macOS; it computes a platform-local **candidate** Notes path separately from existing roaming workspace configuration and inspects existing components using `lstat` without following symbolic links. It does **not** call `ensure_workspace_root`, create a directory, initialize metadata, write a lock, record a Notes entry, or advertise new teacher-experience capabilities.

The internal `PrivateRootInspection` has an intentionally narrow conservative vocabulary: `MISSING`, `PRESENT_UNVERIFIED`, `INVALID_CONFIGURATION`, `UNSAFE_PATH`, `ACCESS_DENIED`, and `UNSUPPORTED`. No state means a qualified, writable private store. In particular, **`PRESENT_UNVERIFIED` must never be promoted to `READY`**, even when the POSIX directory is owned by the effective UID and appears to have mode `0700`.

Path selection is Windows `%LOCALAPPDATA%/Paper Data Suite/private/notes/v1`, macOS `~/Library/Application Support/Paper Data Suite/private/notes/v1`, Linux `${XDG_DATA_HOME:-~/.local/share}/paper-data-suite/private/notes/v1`. A bad/relative explicitly set XDG root does not silently fall back; absent Windows `LOCALAPPDATA` does not downgrade to roaming `APPDATA`.

No private path, SID or UID appears in ordinary result messages or dataclass representation. This is **not** an authentication object and is not exported to producers. Windows junction/reparse and native ACL qualification, POSIX ACL/mount and handle-level TOCTOU checks, creation permissions and atomic locking remain Slice 3–6 obligations; this probe intentionally refuses to assert any of those guarantees.

## Tests and conservative exclusions

`tests/test_teacher_private_inspection.py` exercises synthetic principals; unavailable Windows token evidence; platform path selection and invalid environment settings; missing/non-mutating roots; POSIX target-owner and mode refusal; symlink/dangling symlink/file-component refusal; and the exact negative Notes capability contract. Native Windows SID discovery is exercised by a genuine Windows installed test in Slice 7; a mocked Windows SID result is **not** the native D2 gate. No real teacher or student data is in these tests.

The existing generic `.pds/workspace.json` remains untouched. No sidecar or private registry is created, and no production API promises `notes.records.v1`, menu/CLI, portability, or D3/D4 adoption. The currently published Core 0.6.6 distribution is unchanged; this source candidate must not be labeled a released feature.

## Follow-up before writes

Slice 3 must close native ACL/owner, filesystem-locality and race-resistant handle validation, confirm the accepted D0 identity/threat policy, implement an explicit protected-creation protocol, schema codecs and recoverable atomic metadata transactions. Do not use the read-only candidate `Path` as a validated handle or silently repair existing permissions. Any unsupported account/filesystem configuration must fail closed.
