# Core #238 — Slice 3C3: Read-only workspace association descriptor observation

**Pinned baseline:** `106e872be525a83d1ca1e3b74203c6f5ee9f8eac` (3C2).
**Authority:** D0 owner approval recorded in issue #238; `docs/teacher_private_storage_contract_v1.md` §§2, 4–5.
**Stage:** Internal, non-authorizing observation only. No workspace binding, Notes records, public API, metadata writes or capability change.

## Implemented boundary

`pds_core._teacher_private_descriptor_snapshot.inspect_workspace_descriptor(workspace_root)` examines **only** the existing `<workspace>/.pds/teacher-private-association.json` sidecar, using the previously qualified **pure** metadata codec. It never interprets or rewrites the generic `.pds/workspace.json` marker, never invokes `ensure_workspace_root(create=True)`, and creates **no** directories, files, synchronization markers or lock files.

The result distinguishes `MISSING_METADATA_DIRECTORY` from `MISSING_DESCRIPTOR`, `CORRUPT_METADATA`, `REFUSED_PATH`, `ACCESS_DENIED`, `IO_ERROR`, `INVALID_REQUEST` and `UNSUPPORTED`. `OBSERVED_UNQUALIFIED` contains the nonsecret observed association UUIDv4 and SHA-256 digest, hidden from ordinary `repr`. Missing sidecar or metadata directory is **not** evidence of absent local registry bindings or empty private Notes. Malformed, oversized, unsupported-version and noncanonical bytes are preserved untouched, never replaced or silently interpreted as missing. No result is `READY` or a commit token.

On Linux, observation walks the existing directory chain with `O_DIRECTORY | O_NOFOLLOW` and held parent-relative file access, rejecting symlinks, unexpected file types and hard-linked sidecars. The read is capped at the schema limit, with file identity and size/timestamp rechecks. It intentionally does **not** require a local-only filesystem: unlike the private registry, a nonsecret workspace descriptor may live on cloud-synced storage. This accommodation never confers authorization to a private OS-user-local collection.

On Windows, `CreateFileW` opens each existing directory component with reparse-point inspection and reads the sidecar with a bounded native handle. It refuses directory/reparse/hard-linked files and rechecks directory observations before returning. Placeholder files that require unsafe reparse traversal can be refused. The handles are not retained across later operations; no secure atomic relationship between this descriptor and the local registry is established by these read-time checks.

## Threat model, caveats and next gates

The workspace may be moved, copied, restored from backup or updated by OneDrive or another process after observation. The sidecar UUID **is not a credential**, native OS principal, proof of continuity or entitlement to local Notes. Even a validated sidecar coupled with a separate 3C2 registry snapshot is **not a consistent two-document transaction**. The protected registry lock coordinates cooperative local operations only; it is not an effective cross-machine lock on synced workspace paths.

D1 tests use synthetic files and verify missing-vs-corrupt states, canonical codec round-trip, preservation of the generic marker, unchanged timestamps/bytes, symlink/hardlink rejection, bounded/sanitized outcomes, unsupported platforms and negative write APIs. Windows-native read tests must run on the actual Windows checkout; skips must not be described as native qualification. Full repository pytest, Ruff and strict mypy, plus exact Git scope and commit verification remain required.

**Next:** qualify an explicit **descriptor coordination and currentness protocol** alongside the local registry lock, rechecking both documents under a fixed acquisition order, detecting interruptions and concurrent cloud changes. Do not claim cross-device atomicity. No registry revision CAS, initialization, move, fork, recovery execution or `notes.records.v1` capability is introduced in this slice.
