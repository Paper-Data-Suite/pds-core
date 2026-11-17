# Core #238 — Slice 3G92: Windows ReplaceFileW backup, disposable only

## Scope

The qualified 3G91 native Windows sharing probe establishes that a pre-existing
`FILE_READ_DATA` handle which excludes `FILE_SHARE_DELETE` prevents a second
ordinary opener from obtaining `DELETE` access until the first handle closes.
It does not qualify replacement or recovery. Slice 3G92 separately rehearses
Windows **`ReplaceFileW` with an explicitly named backup file** on fresh,
synthetic, same-volume scratch files. It never accepts a caller path, file,
transaction, native handle, callback, original owner identity or payload.
The only input is a fixed scenario enum.

## Procedure and checks

Within a retained native parent DIRECTORY handle and the existing cooperative
lock, the diagnostic creates fixed synthetic registry before-image, staged
after-image, pending journal and lock. The independent operation rechecks exact
bytes, then calls `ReplaceFileW` with three hardcoded scratch pathnames and
zero flags. A successful call must yield the new registry image, consume the
stage name, preserve the original registry bytes in `registry.previous`, and
leave the journal pending. The backup name is required not to exist beforehand.

Two negative cases mutate the registry or stage before the final precheck,
requiring a **refusal without any call to `ReplaceFileW`**; the synthetic journal
remains untouched. Invalid inputs and requirement-taxonomy drift refuse before
scratch setup. Native Linux returns an explicit Windows-protocol refusal.

## Critical security boundary

Microsoft documents `ReplaceFileW`'s optional backup, metadata propagation,
and partial-failure error codes 1175, 1176 and 1177. A failed call may have
modified file names or inherited metadata: never blindly retry or assume that
failure leaves the namespace unchanged. This diagnostic does not attempt an
automatic repair and does not enable production writes.

`ReplaceFileW` is **path based**, not a handle-relative content compare-and-swap
or a two-root atomic transaction. Holding the parent handle and cooperative
lock does not exclude an uncooperative process with the same account, and an
unobserved precheck-to-call race remains. A successful backup is *not* a durable
journal, nor evidence of power-loss recovery. This probe does not qualify real
OS-owner ACL, workspace binding, stage/journal reconciliation, interruption,
file-system write ordering or multi-document atomicity. All nine production
operation blockers remain unqualified. Initial binding, replay, journal
retirement and Notes records remain blocked.

## Qualification

A 24th isolated installed-wheel native gate runs all three Windows scratch
scenarios and Linux refusals. It validates candidate-wheel provenance, fixed
result enumerations, exact image state, negative capability flags, and that the
report is limited to sanitized evidence. All prior 23 installed gates remain
unchanged; strict Linux/Windows mypy, Ruff, focused pytest and guarded
conditional commit/push are required.

## Next

Investigate Windows `SetFileInformationByHandle` rename semantics and native
file/parent identity pinning, then design an interruption-aware journal protocol
which must preserve uncertain states until revalidated. Neither this diagnostic
nor any previous scratch result authorizes production replacement.

References: https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew
and https://learn.microsoft.com/en-us/windows/win32/fileio/moving-and-replacing-files


## Slice 3G92 Repair 1 — module `sys` is not an explicit export

The first Windows qualification stopped at strict mypy after 119 focused tests
passed (11 skipped) and Ruff passed. Two tests referenced `probe.sys.platform`
through an imported implementation module, which strict mypy reports as an
attribute not explicitly exported by that module. The test file already imports
`sys`. Only the two `monkeypatch.setattr` targets are changed from `probe.sys`
to `sys`; both names resolve to the same Python sys module at runtime. This is
a test-only typing fix with no changed assertions, native actions, production
code, existing CI gate or installed-wheel verifier.

The guarded repair requires the exact accepted f475e71 baseline and unchanged
five-file stopped 3G92 worktree. It authenticates original file ASTs, comment
tokens, append-only audit and exact CI insertion, then runs the original Ruff,
pytest, dual-platform strict mypy and all 24 installed-wheel gates before any
conditional commit or push. A failed qualification preserves the stopped worktree.

All nine production-operation requirements remain unqualified. Production
binding, automatic replay, journal retirement and Notes activation are blocked.
