# Core #238 — Slice 3A: Strict private metadata codecs (no storage activation)

**Source baseline:** `8e0e9aaac392ada7c55355218f915746d20e4e29` (Slice 2).
**Scope:** Versioned, pure, bounded v1 association descriptor/registry model and codecs; no production writes.
**D0 posture:** Owner review of the proposed security/transaction architecture is still required before enabling creation or persistent private binding. Passing codec tests is not approval or native filesystem qualification.

## Purpose and contract alignment

`pds_core._teacher_private_metadata` is an *internal*, import-side-effect-free implementation of the schema sketches in `docs/teacher_private_storage_contract_v1.md` §§2.1–2.3. It supports deliberate future guarded persistence without introducing a Notes store, records, CLI, workspace sidecar, app-data directory, or visible `notes.*` capability. It does not alter `pds_core.workspace` or either #237 terminal primitive.

Exactly two metadata document types are supported:

1. **Workspace sidecar descriptor**: strict schema `pds.teacher-private-association`, integer version `1`, canonical lowercase UUIDv4 association ID; at most **4 KiB**. No owner, path, user, class, student, secret or record text.
2. **OS-user-private registry**: strict schema `pds.teacher-private-registry`, integer version `1`, explicit owner *shape* (`windows_token_sid` or `posix_euid`), positive revision, bounded array of unique UUIDv4 associations, positive per-binding revision, absolute accepted-root syntactic form, optional bounded opaque fingerprint and currently exact `active` state. At most **512 KiB / 1,024 bindings**. This metadata may contain private owner and path fields; its **`repr` suppresses them**. Existing folder permissions are **not** inferred from parsing a registry.

The codec rejects unknown keys/versions, malformed/bool versions, noncanonical or non-v4 IDs, nonpositive revisions, owner value shape mismatches, duplicate keys at any nesting level, duplicate association IDs, non-UTF-8, malformed/nonfinite JSON, control/format characters in paths, relative or traversal paths, dangerous Windows UNC/device paths, oversized documents and bindings. Failures use sanitized `PrivateMetadataError.code` values and never incorporate the original text or private path. Deterministic pretty JSON encodes with sorted keys and final newline. No implicit migrations, schema-repair writes, owner changes, locking or authorization are implemented.

**Important distinction:** An owner value parsed from a JSON document is **untrusted data**. Only the future native OS owner/permissions verifier can compare it against the real process token/effective UID and qualify a local store. Sidecar IDs, decoded metadata objects and absolute paths are **not** credentials or storage handles. Do not let #239 accept any as authorization. A legitimate file from a different OS owner must be denied by native verification even if it passes this syntax check.

## D1 and implementation qualification

`tests/test_teacher_private_metadata.py` uses exclusively synthetic UUIDs and paths, verifies codec round-trip, invalid/duplicate/future schemas, owner/value and absolute-root syntax, bounding, immutable models, private `repr`, no import write/prompt behavior, and preservation of only the two previously qualified teacher-experience capability tokens.

Before commit: run targeted pytest including Slices 1/2 and workspace/terminal regressions; full pytest; Ruff lint/format; strict mypy; Git whitespace and exact-change-scope checks. The branch still identifies `pds-core` version `0.6.6` as development source only; no new published release is implied.

## Blocked activation / next sub-slice (3B)

Slice **3B** must implement and qualify real platform-specific **protected creation** (Windows native ACL/effective DACL; Linux and macOS UID/mode/ACL/mount checks), safe directory handles, qualified cross-process locks, expected-revision compare-and-swap and recoverable journal/atomic metadata commits. It must demonstrate native refusal where security/locality cannot be verified. Only after explicit D0 owner acceptance and test qualification may that code be reachable for actual teacher-private files. Creation, first binding and move/fork decisions still belong to the distinct future guarded operations in Slices 3B–5. macOS native evidence and Windows ARM64/security differences must be recorded honestly, not simulated as having passed.

No Notes bodies, student identifiers, producer-owned records, shared login isolation, general workspace backup or private export/import are provided here. Cross-device portability remains #243.
