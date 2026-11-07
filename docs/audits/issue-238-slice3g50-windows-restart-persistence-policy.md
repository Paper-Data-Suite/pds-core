# Core #238 — Slice 3G50: Windows restart and persistence policy

## Accepted baseline

- Feature baseline: `a4713826df59109fe8f89bde84a25038f2a75bcd` (qualified Slice 3G49).
- `main` baseline: `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`.
- 3G49 native Windows scratch census: **all three journal/registry/descriptor directory flush calls returned** with `requests_returned_unqualified`. This verifies the result of the requests in the tested environment; it does **not** prove power-failure durability or apply to a different filesystem or production directory.
- Existing Core 3G47 independent native restart reader owns actual registry/journal/descriptor image, effective OS owner, workspace binding and namespace verification. This slice does not duplicate or replace that reader.
- `pds_core._teacher_private_recovery_production_write_barrier` remains **unconditionally blocking** production writes; no Notes capability is advertised or activated.

## Frozen 3G50 policy

Internal entry point: `review_windows_private_pending_recovery_policy(step, expected_revision, proposed, existing_private_root, existing_workspace_root)`.

1. Reject incorrect argument types, unsupported operations and non-Windows platforms before native work. The proposed `PrivateTransactionIntent` object is not permission to mutate.
2. Invoke 3G47 **independent native restart verification** on the actual existing private and workspace roots. It obtains its own guards and validates canonical bytes, owner/binding and protected checkpoint; never trust results from a previous attempt scope.
3. If the native checkpoint is not one of three recognized, recoverable pending states, preserve all evidence. No scratch probe may override native refusal or rescue a conflicting checkpoint.
4. Separately sample the three directory-flush requests via the already-qualified 3G49 **disposable scratch** probe. Require an exact tuple of `journal`, `registry`, `descriptor` in that order, each with `RETURNED_UNQUALIFIED`. A successful sample is only diagnostic. Wrong order, missing roles or refused requests must fail closed.
5. Return one of three **hold** states below. The returned type contains no path, identity, byte image, HANDLE/FD, callback or write capability. Every result has `automatic_retry_forbidden`, `pending_evidence_must_remain`, `journal_retirement_forbidden`, `production_writes_blocked`, `directory_durability_unqualified`, and `durable_commit_unqualified` set to `True`.

| Independently observed native state | 3G50 disposition | Required continuation |
| --- | --- | --- |
| Original registry and prepared stage remain | `PREPARED_STAGE_HOLD_NO_RETRY` | Independent recovery review; do not infer no operation was attempted or retry blindly |
| Registry after-image, descriptor pending | `REGISTRY_AFTER_DESCRIPTOR_PENDING_HOLD` | A distinct, qualified, owner-scoped descriptor-completion protocol; no implicit write |
| Both after-images, pending journal | `BOTH_AFTER_JOURNAL_PENDING_HOLD` | Retain journal; persistence and retirement are still unqualified |
| Inconsistent/rejected native checkpoint | `NATIVE_RESTART_UNQUALIFIED_PRESERVE` or `CONTRADICTORY_EVIDENCE_PRESERVE` | Refuse; do not attempt recovery writes |
| Missing/failed/nonmatching scratch flush evidence | `DIRECTORY_PROBE_UNQUALIFIED_PRESERVE` | Refuse certification; native checkpoint remains pending |
| Exception or interruption | `IO_ERROR_PRESERVE` / `INTERRUPTED_PRESERVE` | Preserve artifacts; no automatic retry |

## Why returned directory flushes are not a transaction certificate

Microsoft's public `FlushFileBuffers` contract describes a flush of an open file handle. The documented `MOVEFILE_WRITE_THROUGH` guarantee specifically calls out a copy-and-delete move; it does not establish the stronger atomic, crash-durable **two-directory, two-document** same-volume namespace transaction required here. Its directory-handle documentation does not certify that a successful directory flush is sufficient for all NTFS power-loss cases.

- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers
- https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw
- https://learn.microsoft.com/en-us/windows/win32/fileio/obtaining-a-handle-to-a-directory

The recovery contract therefore distinguishes **a returned request**, **a read-consistent native checkpoint**, **an authorized mutation**, and **durable commit**. None implies the next. Conservative refusal does not claim arbitrary storage is corrupt; it means Core lacks evidence sufficient to authorize continuing an interrupted transaction automatically.

## Implementation and validation scope

Exactly three additive files: this audit, one private Core module, and its tests. No changes to public API, `workspace.py`, `.pds/workspace.json`, Suite contracts, producer modules, Notes records, journal storage or private on-disk files. Test inputs are synthetic. The only filesystem mutation from the called dependencies is the separately contained scratch probe's temporary directory and probe files; the actual private root is opened **read-only** by Core's existing native restart reader.

Windows source qualification: new tests; 3G49 native directory probe remains in the focused Core suite; Ruff; strict mypy; pinned baseline checks. Full-suite qualification checkpoint remains the green 3G40 run; a complete re-run is required before the issue's final installed wheel/PR acceptance. Linux remains out of this Windows-specific policy; native macOS is unqualified, as specified in the issue.

## Critical next integration work

3G50 **does not** solve crash-durable namespace persistence on Windows, and it does not introduce a production writer. The next implementation must define an operation-owned production recovery state machine where the journal is both safely established before any mutation and retained until independent restart qualification. It must handle interrupted descriptor completion, file/binding/owner revalidation, and explicit journal-retirement authority. If the required physical namespace guarantee cannot be established on a supported Windows filesystem, the owner must explicitly accept a weaker, accurately documented *recoverable-or-refuse* policy or leave production writes blocked. Neither 3G49 returned flushes nor 3G50 hold states justify bypassing this decision.
