# Core #238 — Slice 3B5: Pure interrupted-transaction observation review

**Pinned source baseline:** `9e024143cbc16cd6a030ccf540aa0df8897fcc8b` (Slice 3B4).
**Issue:** [Core #238](https://github.com/Paper-Data-Suite/pds-core/issues/238).
**Design sources:** `docs/teacher_private_storage_contract_v1.md` §§3–5, `docs/security/teacher-private-storage-threat-model.md`, Slice 3B3 witness and Slice 3B4 strict transaction-intent envelope.
**D0:** The owner-accepted sidecar, native OS security/locking, crash protocol and write-activation decisions have **not** been established by this slice. No release or producer qualification is asserted.

## Purpose

One transaction may leave two metadata documents in different locations: a non-secret workspace association sidecar and a private per-OS-user binding registry. A missing document is **not** equivalent to an unreadable document. Neither case should be silently interpreted as an empty Notes collection. A fully observed after-state is **not** proof of durable commit or an authorized READY scope.

`pds_core._teacher_private_recovery_review` adds a private, entirely in-memory **observation vocabulary** that composes the already-validated Slice 3B4 transaction intent and the Slice 3B3 before/after SHA-256 classifier. It introduces **no file opening, persistence, lock acquisition, directories, public API, teacher Notes service, CLI, or capability token**.

An `ObservedPrivateDocument` explicitly distinguishes `ABSENT`, `PRESENT` with exact captured bytes, and `UNREADABLE`. Its body is excluded from the dataclass representation. The future guarded file reader must report `UNREADABLE` for access-denied, I/O or inconclusive reads and must not cast errors to `ABSENT`. The implementation validates present bytes against the strict v1 descriptor/registry codec and size limits. A malformed or unsupported document yields `CORRUPT_METADATA`, while a structurally valid but unexpected owner, association or state yields `CONFLICT`.

## Refusal-only result taxonomy

| State | Observed situation | Policy |
| --- | --- | --- |
| `BEFORE_STATE` | Exact descriptor and registry before bytes, including permitted genuine absence | Does **not** imply Notes are empty or that an operation may be retried without checks |
| `DESCRIPTOR_ONLY` | Exact descriptor after-state, registry before-state | Explicit guarded recovery review required |
| `REGISTRY_ONLY` | Exact registry after-state, descriptor before-state | Explicit guarded recovery review required |
| `AFTER_STATE_REVIEW_REQUIRED` | Both exact after-state bytes | **Not** READY: locking, native owner, durability, fsync, journal finalization and currentness remain unproven |
| `CONFLICT` | Unexpected valid metadata/owner/association or unmatched digest | Preserve current bytes; no replacement, alias, rollback or automatic migration |
| `CORRUPT_METADATA` | Oversized, invalid, unsupported-schema or undecodable present document | Preserve bytes; refuse to mask corruption as absence |
| `ACCESS_UNVERIFIED` | At least one file unreadable, or underlying status inconclusive | Never silently report ABSENT, UNBOUND or a ready collection |

All results expose only a constant sanitized message and enum. Owner SIDs/UIDs, binding paths, association IDs and transaction bytes remain omitted. This is **not** an access-control decision, even if the parsed registry owner happens to match the intent. OS-owner identity and ACL/UID checks must be performed by a future native guarded reader with live handles, locks and currentness checks. Inputs supplied by another caller are not security evidence.

## Deterministic test scope

`tests/test_teacher_private_recovery_review.py` covers initial binding, intentional move and copied workspace fork, including before/after and one-sided states; the intentionally unchanged sidecar during rebind; unreadable versus absent; malformed, oversized and unsupported metadata; unexpected owner and association identity; invalid type/presence combinations; sanitized representations/errors; import side effects; and continued absence of Notes services and `notes.*` advertised capabilities. It uses synthetic data only. Oversized test buffers are allocated **inside** test functions, not pytest parameter lists, avoiding Windows's 32,767-character environment-variable limit.

The runner must check the exact branch/HEAD/remote, SHA-256 payload manifest, additive three-file scope, Ruff formatting with AST equivalence, focused regressions, strict mypy, full pytest, Git whitespace/scope, then commit and push only on complete success. Passing those gates is **D1 source qualification of this pure classifier only**, not native D2 security qualification.

## Next gates and exclusions

Production use must remain blocked until owner D0 approval and native verified private-root qualification. Subsequent sub-slices must implement protected local directory creation, Windows handle/DACL and Linux/macos ACL/locality qualification, actual cross-process lock ordering, strict no-follow file reads, write/fsync/journal recovery and explicit association/binding flows. This slice does not write a registry or descriptor, automatically replay/rollback a transaction, interpret school data, issue protected store handles, create records, or alter the release/version. #239 owns Notes CRUD; #240 owns menu/CLI; #243 owns private backup and transfer; #244 owns broader installed qualification.
