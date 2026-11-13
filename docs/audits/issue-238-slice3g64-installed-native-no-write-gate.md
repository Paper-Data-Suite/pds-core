# Core #238 — Slice 3G64: isolated native installed-wheel no-write gate

## Exact development scope

- Start from `8e150b1f1f89c444ee0ee9da1976277d3d4bb9e3`, the 3G63-qualified branch head.
- Add a **native Windows/Linux isolated-wheel smoke** for owner observation, absent private root inspection, unbound workspace noncreation, invalid local-root environment refusal, and the nine-requirement production barrier.
- Add dedicated CI matrix entries for `windows-latest` and `ubuntu-latest` on Python 3.11. The source test complements, but does not replace, the installed-wheel gate.
- The installer smoke runs with Python `-I` in a fresh wheel-only virtual environment *outside the source checkout*. The probe's synthetic absent private root is redirected to an existing disposable scratch directory, not to actual teacher data.
- Record only fixed states, version, OS/architecture/Python, and candidate wheel digest; **never** record SID, UID, private root, workspace paths, teacher/student data, or private record content.
- Runner checks remote/branch/HEAD/clean tree and original CI file blob; modifies only the documented workflow and additive script/test/audit files; runs focused source regression, whole-tree Ruff and strict mypy, then an isolated candidate-wheel smoke. Commit/push occurs only after all tests pass.

## Qualification distinction

Passing the smoke means **the installed development candidate correctly refuses production mutation** and that missing-path inspection and native owner discovery were exercised on the host. It does **not** qualify a writable private store, native existing-directory ACL authorization, stable workspace binding, Windows directory flush durability, two-document atomicity, replay, journal retirement, Notes records, a release artifact, or macOS security. CI evidence remains pending until the PR workflow actually executes, even after local qualification passes.

## Explicit prohibitions

Do not expose `pds_core.teacher_private_storage`, activate `notes.records.v1` / Notes menus or CLI, treat a read-only native preflight as a READY handle, or change the blocking production-write barrier. This slice makes D2 negative evidence repeatable without approving the D2 positive storage gates.
