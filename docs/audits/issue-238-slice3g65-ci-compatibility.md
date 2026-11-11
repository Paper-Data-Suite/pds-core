# Core #238 — Slice 3G65: Python 3.11/3.12 fixture and cross-platform mypy compatibility

## Evidence and scope

- Base: `3a419342eac72d2fbd63f849121c620aadbfdaeb` (qualified 3G64).
- GitHub PR #247, run 42940854390: 7 failed / 15 jobs. All installed native **no-write** gates passed on Windows and Ubuntu.
- Python 3.11/3.12 validation failed 130 tests in eight legacy synthetic test files; the fixtures use `object.__new__(PrivateTransactionIntent)` with absent fields and then compare `decoded == proposed` where both are the *same* deliberately forged mock object. Self-equality is not a safe substitute for complete fixture fields on older Python dataclass implementations.
- Ubuntu Python 3.13/3.14 mypy 2.4.1 reported 22 `attr-defined` errors in 16 source files on Windows-only `ctypes.WinDLL`, `ctypes.get_last_error`, and `msvcrt.open_osfhandle` references.

## Applied bounded repair

1. Complete only the synthetic intent fields absent from the eight identified fixtures. No production validation is weakened and malformed-object negative tests outside those fixtures are left intact. Existing explicit fixture fields continue to override these synthetic defaults.
2. In 16 modules, replace only the 22 direct platform-specific lookups with equivalent `getattr` access, casting Windows last-error and C-runtime file-descriptor returns to `int`. Windows attribute access remains runtime-only, and unsupported-OS refusal gates are unchanged. No change to security checks, file paths, writes, locks, journal handling, or supported capabilities.
3. Exact file blob SHAs, remote/branch/HEAD, allowed worktree, exact token counts, focused regression and both mypy platform targets are guarded before commit/push. The source archive is a canonical, inspectable transformation manifest and audit, not a wheel or release.

## Explicit remaining native failure

The Windows-only `test_windows_native_scratch_replacement_preserves_handle_ids` still fails on Python 3.12 and 3.13 at its real registry postimage assertion (not on Windows 3.14). This slice deliberately does **not** suppress that test or modify the implementation. It needs independent native scratch diagnostics and a subsequent guarded repair. Full CI is **not** claimed green from this slice.

## Boundaries

No production private binding/writer, replay, journal retirement, Notes service, READY handle, release, or normal workspace backup of Notes is enabled. D2 positive write durability remains unqualified.
