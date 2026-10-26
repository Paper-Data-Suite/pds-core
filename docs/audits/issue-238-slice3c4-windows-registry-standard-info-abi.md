# Core #238 — Slice 3C4: Windows private-registry FILE_STANDARD_INFO ABI correction

**Baseline:** `8968180bc2c404e4a38d9f4c3dd0b1d7be12b1fd` (passed Slice 3C3).
**D0 authority:** Approved Core #238 D0 security decisions.
**Scope:** Two ctypes field-type corrections in the existing internal registry-bootstrap module, one additive regression-test module. No storage activation.

## Defect and precise correction

The Windows `FILE_STANDARD_INFO` structure returned by `GetFileInformationByHandleEx(FileStandardInfo)` has `AllocationSize` and `EndOfFile` as 64-bit signed values, `NumberOfLinks` as a 32-bit DWORD, and `DeletePending`/`Directory` as **one-byte BOOLEAN** fields. The existing `_FileStandardInfo` inside `pds_core._teacher_private_registry_bootstrap` incorrectly declared its two BOOLEAN fields as `wintypes.BOOL` (four bytes on Windows). This changes the effective directory-field offset and can produce false native security refusals when qualifying `.registry.lock`. The more recent descriptor inspector already uses `ctypes.c_ubyte` after Slice 3C3.

Change only these two existing structure-field declarations from `wintypes.BOOL` to `ctypes.c_ubyte`. The rest of the logic, especially owner SID/DACL, link-count, delete-pending, directory, file-size, lock ownership and root-locality tests, remains intact. No refusal is bypassed. Correct ABI decoding is **necessary** for checks to be meaningful; passing them remains *unqualified* for Notes writes.

## Proof and test boundary

`tests/test_teacher_private_registry_standard_info_abi.py` confirms field type and relative byte offset on all hosts, checks the exact Windows offsets 20/21 and 24-byte total size on Windows, and compares the registry and descriptor definitions. A Windows-only parameterized fake native API provides the **raw 24-byte Windows memory layout**, independently of our `ctypes.Structure`, verifying regular-file acceptance and refusal of directory/deletion-pending flags. It does not create or access user data.

The guarded runner checks the pinned GitHub branch and `HEAD`, original production blob, the original AST against the bundled corrected full source after reverting only these two field declarations, and exact modified/additive path scope. It verifies the production diff corresponds to two field-type replacements before running focused regressions, Ruff, strict mypy, and full pytest. All checks must pass before the runner commits/pushes.

This is a D1 source/runtime regression, **not** proof of end-to-end Windows user-private installed behavior, cross-tree descriptor/registry atomicity, stable handle security, or Notes readiness. No `notes.records.v1` capability is added. MacOS is unchanged/unsupported. The Next Slice must address registry/descriptor coordination and revision checking, not assume a corrected ABI proves storage safety.
