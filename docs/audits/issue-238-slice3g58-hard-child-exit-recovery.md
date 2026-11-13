# Core #238 Slice 3G58 — hard child-process exit / fresh restart recovery rehearsal

## Accepted baseline and isolated scope

- Branch: `238-establish-private-teacher-workspace-storage`.
- Baseline: `ab2bf7c0082888299b3a555429c8d51ebfbed870` (qualified 3G57).
- This slice adds **test infrastructure only**, not a production module or public API.
- The child worker lives exclusively at `tests/_core238_3g58_child_worker.py`; it is not installed as a command.
- Only a nonce-marked direct child of the operating system temporary directory can be used. The original 3G57 scratch operation takes no arbitrary user storage paths; the child replaces its *test-only* temporary-directory allocator.
- No teacher, student, workspace, Notes, or other production data are used.

## New acceptance evidence

For eight ordered interruption boundaries, launch a **separate child Python process** with native retained directory and stage handles. Abruptly end that process through `os._exit(93)`, bypassing all Python cleanup and release hooks. The parent uses new OS locks and four newly retained directory handles to reopen the on-disk journal, both metadata files, and remaining stages.

| Exit boundary | Expected fresh checkpoint |
| --- | --- |
| prepared, before any attempt marker | prepared journal + both stages |
| registry attempt marked, before replace | prepared journal + both stages |
| after registry replacement | registry after, descriptor before, pending journal |
| after registry flush request | registry after, descriptor before, pending journal |
| descriptor attempt marked, before replace | registry after, descriptor before, pending journal |
| after descriptor replacement | both after-images with journal pending |
| after descriptor flush request | both after-images with journal pending |
| operation handles released | both after-images with journal pending |

All states require exact canonical intent and after-image bytes. The restart reader does not mutate any document, replay a stage, delete a stage, or retire a journal. The test also refuses invalid scratch roots, missing or mismatched nonce reservations, and unsupported boundaries. On platforms with native permission/flush restrictions, the known scratch preflight is reported as **unqualified/skipped** rather than pretending to prove a positive result.

## Limits and next actions

- Abrupt termination proves only process-death and OS-handle-release behavior for synthetic, disposable storage. **It does not simulate power loss or prove ordered durable directory entries on Windows.** A flush request returned by the filesystem is not a durable-commit certificate.
- The parent intentionally checks one native checkpoint per fresh scope. No automatic retry, repair, journal retirement, or Notes service is authorized by matching bytes.
- No production writer is added; existing protected owner verification, ACL custody, binding rules, and permanent production write barrier are untouched.
- Subsequent work must qualify **operation-owned production mutation, recoverable interrupted commits, and power-loss durability** before any teacher-private workspace write is enabled.

## Qualification

Native Windows hard-exit matrix, the 110-file focused Core #238 regression suite, Ruff and strict mypy must pass under the guarded runner. The earlier complete Core checkpoint (3G40: 6,864 passed / 179 skipped) does not substitute for the eventual final full suite, wheel qualification, CI, or OS security acceptance.
