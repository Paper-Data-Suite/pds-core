# Core #238 — Slice 3G25: Protected Windows HANDLE sharing-contract review

**Scope:** Pure, read-only, source-level compatibility review, not a native writer or a production mutation qualification.

## Purpose

3G24 qualified disposable Windows `FILE_SHARE_DELETE` replacement behavior. 3G25 compares the *existing* production-protected helper `CreateFileW` access and share masks without opening real teacher-private paths or changing any metadata. The read-only reviewer accepts exactly five bounded role/mask observations and yields only a sanitized, immutable, non-authorizing state. Tests bind its reviewed values to the committed helper code using Python AST/source inspection.

| Handle role | Existing helper | Desired access | Share mask |
| --- | --- | --- | --- |
| Journal directory retained handle | `_teacher_private_native_journal_anchor._windows_open` | `FILE_READ_ATTRIBUTES\|READ_CONTROL` (`0x20080`) | `FILE_SHARE_READ\|WRITE\|DELETE` (`0x7`) |
| Registry retained handle | Same journal-anchor helper | `0x20080` | `0x7` |
| Workspace `.pds` retained directory | `_teacher_private_descriptor_snapshot._windows_open` | `FILE_READ_ATTRIBUTES\|FILE_LIST_DIRECTORY` (`0x81`) | `0x7` |
| Descriptor retained file | Same descriptor helper | `0x81` | `0x7` |
| Separate bounded registry-image reader | `_teacher_private_registry_image_snapshot._read_windows` | `GENERIC_READ\|READ_CONTROL` (`0x80020000`) | `FILE_SHARE_READ` (`0x1`) |

**Important:** The mask `0x7` allows delete sharing. Holding these observational handles does **not** itself fence a competing native replacement or establish a write-exclusive transaction. `0x1` may prevent other opens requiring write/delete sharing *while that particular image-reader HANDLE is open*, but does not provide a durable or distributed transaction lock. Actual write authorization requires separate verified operation-owned guard, native identity continuity, expected-revision CAS, crash-recovery and persistence protocols.

## Refusal and limits

All five roles must be present exactly once. Unknown/out-of-range masks, wrong field types, missing/duplicate roles, or changed access/share masks fail closed. No input can contain a filesystem path, teacher bytes, native HANDLE, writer callback, confirmation token or owner. The reviewer never opens a file, runs `CreateFileW`, grants authority, retires pending journals or activates Notes.

The contract is derived from the current Python source and is **not** an OS-level attestation. Dynamic library calls, Windows native ACLs, reparse-point defenses, temporary file handles, antivirus interactions and the lifetime of nested read handles still require independent on-Windows qualification. Tests inspect specific helper implementation sources; a refactor that changes those sources should require deliberate requalification rather than silent assumptions. This slice does not alter the existing protected registry, journal, or descriptor helpers.

## Qualification

Runner must verify the exact 3G24 Git baseline, remote heads and inherited blob pins, clean additive scope, source integrity, the isolated contract regression tests, the full focused Core #238 test selection, Ruff and strict mypy before committing/pushing exactly three additive files. Full Core pytest may be deferred after the green 3G24 integration checkpoint (5,749 passed, 176 skipped). Failures preserve the checkout without reset, stash, cleanup or production mutation.

## Next gate

3G26: analyze the lifetime of the separate registry image reader relative to prospective writer ownership, and whether its restrictive share mask conflicts with a future guarded replacement. Keep it read-only and test-backed until the actual production recovery writer and persistence protocol are independently qualified.
