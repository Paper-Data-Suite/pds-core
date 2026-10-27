# Core #238 — Slice 3C5: bounded paired registry/descriptor observation

**Pinned predecessor:** `aa65e56a4e49e3c8b782342a9079eea1345ff554` (Slice 3C4).
**D0 authority:** Core #238 accepted decisions and `docs/teacher_private_storage_contract_v1.md`.
**Status:** Internal, read-only **UNQUALIFIED** observation. Not an owner binding, approval, transaction lock plan, CAS predicate, or Notes service.

## Added scope

`pds_core._teacher_private_pair_observation.observe_private_registry_and_workspace_descriptor(existing_private_root, existing_workspace_root)` combines the **existing** strictly qualified local `registry.json` reader with the **existing** untrusted `.pds/teacher-private-association.json` reader. It requires the exact owner-local Notes v1 root, a syntactically permitted workspace root, and the already-existing `.registry.lock`. It acquires that private cross-process lock exactly **once** and uses the existing *internal under-lock readers*, not public snapshot functions that would attempt nested acquisition.

Read sequence while holding the same private lock:

1. Inspect owner-private registry through native parent/file checks; receive canonical owner-checked revision, count and digest.
2. Inspect the untrusted workspace descriptor through native no-follow ancestry checks; receive canonical UUID and digest.
3. Inspect the descriptor a second time and require identical state, UUID and digest.
4. Inspect the registry a second time and require identical state, revision, count and digest.

Only successful, stable, individually protected observations yield `OBSERVED_UNQUALIFIED`, and the result deliberately says **no association is authorized**. It may include bounded revision/count and opaque UUID/digest observation fields, none of which is a secret, CAS authority, binding proof, or writable handle. The result's repr excludes UUID and digests. All other outcomes omit them.

## Refusal and preservation

- Distinguish `MISSING_REGISTRY`, `MISSING_DESCRIPTOR`, unsafe or corrupt `REFUSED_REGISTRY` / `REFUSED_DESCRIPTOR`, and `COORDINATION_UNAVAILABLE`. A missing registry is **never** assumed to imply no old Notes records.
- Any differing status, revision, count, digest or UUID between the paired reads yields `CHANGED_DURING_OBSERVATION` and no returned identity/digest. A malformed or noncanonical document remains untouched.
- Root validation and unsupported-platform refusal happen **before** lock acquisition. No directory/file creation, repair, deletion, chmod, rename, registry bootstrap, journal creation, sidecar replacement, or Notes-record operation is performed.
- This slice adds exactly one internal source file, one test file, and this audit; no existing runtime API is modified and no `notes.records.v1` capability is added.

## Security limits — MUST NOT promote to authority

The private `.registry.lock` coordinates cooperating local processes, **not** remote OneDrive updates, other synchronization clients, hostile same-account processes, or copies of workspace folders. Repeated equality does **not** exclude ABA changes between observations, does **not** make a cross-volume/cross-computer atomic snapshot, and does not verify that the descriptor UUID appears in the registry, matches the accepted workspace path, or is approved for the effective principal. A valid sidecar UUID alongside an empty registry is deliberately reported only as `OBSERVED_UNQUALIFIED` (binding count zero). The caller must **not** infer READY or auto-attach private Notes from that result.

Before any mutation: define and enforce complete lock ordering, owner/path identity and old-byte CAS requirements under held native handles; compare the local registry binding to the exact workspace; require explicit review for move/copy/restore; write durable journal-first intent; maintain fsync/replace guarantees; implement interruption reconciliation; and pass platform-specific installed security qualification. None is introduced here.

## Verification

Tests cover normal read order and exactly-one-lock bracketing, identical versus divergent digests/revisions, missing/corrupt registry and descriptor, busy coordination, invalid root/no IO, sanitized failures, no write-authority exports, Linux nonroot local-file fixtures with preserved bytes/mtimes, and a Windows-native fixed NTFS/ReFS temporary protected-root fixture. Linux locality is **synthetically** qualified in tests and is not a D2 platform attestation. Local tests run under a nonroot Linux user; Windows native tests and the entire repository test/type/lint suite remain required on the user's checkout before commit.
