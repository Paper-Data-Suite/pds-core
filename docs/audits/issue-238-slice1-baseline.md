# Core #238 — Slice 1 baseline, authority and D0 disposition

**Issue:** [#238](https://github.com/Paper-Data-Suite/pds-core/issues/238) (parent [#235](https://github.com/Paper-Data-Suite/pds-core/issues/235))
**Proposed branch:** `238-establish-private-teacher-workspace-storage`
**GitHub branch baseline inspected:** `a0d5e1a50580bbe025f0cad23c7e8524203a52ec` (identical to `main` when this Slice 1 payload was prepared)
**Package identity at baseline:** `pds-core` 0.6.6; Python `>=3.11`; `setuptools.build_meta`; no runtime dependencies
**Status:** D0 *review candidate* and source-only regression. No private-storage implementation, qualified OS isolation, D2 installed acceptance or published Notes capability is claimed.

## Evidence sources and ownership

| Authority | Inspected source | Baseline observation / consequence |
| --- | --- | --- |
| Accepted Core contract | `docs/teacher_experience_contract_v1.md`, §§2.1, 4.1, 4.5 and 5 | Context paths are hints, not owner credentials; private Notes are workspace-associated, OS-user-protected, and outside the ordinary workspace. |
| Conformance | `docs/teacher_experience_conformance_v1.md`, P01–P03, P05, P08–P09, UX-10/12 | Actor spoof, principal isolation, move/copy ambiguity and backup disclosures are required; this slice is only D0/D1 negative proof. |
| ADR | `docs/decisions/0005-adopt-versioned-teacher-experience-public-interfaces.md` | Core owns shared primitives and private Notes custody; producers and Suite cannot infer authorization from display/actor metadata. |
| Suite specification | `pds-paper-data-suite/docs/design/teacher-experience-design-specification.md`, branch `49-evergreen-launch-and-supported-composition-upgrades`, §§8.3–8.5, decisions D-02/D-03 | Local OS-user storage and private Notes scope are accepted product intent, not implementation. Reverify branch before independent Suite work. |
| Workspace implementation | `pds_core/workspace.py` | `resolve_workspace_root`/`inspect_workspace_root` do not create a workspace. `ensure_workspace_root(create=True)` creates shared folders and **rewrites** a generic `.pds/workspace.json` with `created_by=pds-core`, `workspace_version=1`. This marker has no unique workspace ID. |
| Workspace tests | `tests/test_workspace.py` | Covers explicit/environment/saved/default roots, no-write inspection, marker creation, canonical baseline directories, and `create=False`. |
| Established Core teacher capability | `pds_core/teacher_experience.py`, from #237 | Exactly `terminal.header.v1` and `terminal.notes_command.v1` are implemented in the merged source. None proves Notes records or storage. |
| Packaging and historical compatibility | `pyproject.toml`, `README.md`, `docs/roster_workspace_contract.md` | `core` and `pds-core` already exist; current per-user **config** uses `%APPDATA%` or XDG config, which is distinct from the proposed local **private data** root. |

Git blobs pinned for the guarded source application: `pds_core/workspace.py` `30808e54713294fe79f0626d0715fa39a18fd8cf`; `pds_core/teacher_experience.py` `6c4c4e34c7806f4c1d77940b6db82325d9628704`; `pyproject.toml` `746500907824445ebba8b39bee048de7fc19e2cc`; `docs/teacher_experience_contract_v1.md` `011fd8b4f1accaf326bc6b28c76d0708dfba0509`; `tests/test_workspace.py` `b2c3ef11577545bc088d64420e694953634947de`.

## Slice 1 scope and deliberately absent behavior

This slice adds the proposed Core private-storage contract, threat model and negative source-level regressions. It **does not add a production private-storage module**, create directories, modify workspace metadata, alter CLI routing, add record CRUD, change the v1 capability set, or claim native Windows/macOS/Linux permission testing. The generic `.pds/workspace.json` marker remains untouched. The design calls for an *additional* non-secret `.pds/teacher-private-association.json` sidecar, written **only** after an explicit reviewed operation in a later slice.

A working directory in a district OneDrive/cloud-synced workspace is **not** an acceptable default place for private Notes content. A copy/sync of the non-secret sidecar alone is insufficient to make the private collection appear on another OS account or device.

## Frozen-candidate decisions requiring owner D0 approval before Slice 2/3

1. **Identity:** one opaque random UUIDv4 association ID, independent of workspace path, in a non-secret sidecar; existing `.pds/workspace.json` is never promoted or rewritten for this purpose.
2. **Owner:** effective process-token SID on Windows or effective UID on POSIX, plus native effective ACL/permission verification; self-declared teacher or actor labels have no authentication value.
3. **Location:** platform user-local application data, separately protected; private registry keeps owner/association/location binding and an explicit monotonically increasing revision.
4. **Binding lifecycle:** `UNBOUND`, `READY`, `REVIEW_REQUIRED`, `CONFLICT`, `RECOVERY_REQUIRED`, `UNSUPPORTED_PROTECTION`, `ACCESS_DENIED`, `CORRUPT_METADATA`, `STALE_STATE`. No unreviewed move/fork or implicit reset-to-empty.
5. **Read vs. write:** inspection remains non-mutating, including missing roots and unqualified security. Explicit prepare/plan and confirmed commit are separate operations; every durable commit validates security and freshness under locks.
6. **Duplication:** reopen at a verified existing binding is read-only; moved/renamed root needs intentional rebind if its continuity cannot be established; copied root must fork to a new ID without inheriting records; restore/second-device binding requires explicit review.
7. **Failure:** never treat a corrupt descriptor or lost registry as a new empty collection; retain unknown future schema versions; if filesystem security cannot be established, refuse rather than claim OS isolation.
8. **Privacy:** no note bodies, student IDs, creator display names or producer payloads in sidecar/registry or routine diagnostics; normal workspace backup does not include local Notes content.

The proposed exact schemas, public/private service seam and transaction protocol are in [`../teacher_private_storage_contract_v1.md`](../teacher_private_storage_contract_v1.md); the threat analysis and support matrix are in [`../security/teacher-private-storage-threat-model.md`](../security/teacher-private-storage-threat-model.md).

## Slice 1 executable evidence and gates

`tests/test_teacher_private_storage_slice1.py` checks the retained generic marker, no sidecar initialization by existing workspace APIs, and the exact #237-only capability set. Run the focused tests and the full pytest/Ruff/strict-mypy gates on the branch before committing. These are **D1 negative regressions, not D1 proof of future storage protections**.

| Gate | Slice 1 disposition |
| --- | --- |
| D0 identity/protection/transaction choice | Proposed for explicit owner review; not automatically approved by writing this document |
| D1 existing Core workspace and terminal behavior | Guarded source tests and full suite to run on the actual branch |
| D1 OS-owner security, concurrency, move/fork implementation | Not implemented; Slices 2–6 |
| D2 isolated installed wheel and native ACL/UID probes | Not performed; Slice 7 |
| D3 producer handoff | Not implemented; downstream adopters |
| D4 Suite and physical classroom/ARM64 | Not implemented; downstream qualification |

## Release and migration boundary

The source branch is not a published update to `pds-core` 0.6.6. Future #239 code must obtain a qualified, current Core-controlled storage scope, never construct one from a raw path, a sidecar UUID, a module name or an actor label. **No private Note record or migration is created by #238 Slice 1.** #243 owns explicit export/import/transfer; silent reliance on whole-workspace backup would be inaccurate.
