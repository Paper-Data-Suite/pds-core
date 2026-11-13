# Core #238 — Slice 3E6: protected exact registry-byte observation

**Base:** `b2c04b02e073a95231364fe109829ce5a547684c` (completed Slice 3E5).
**Scope:** Three additive files only. No existing contracts or public APIs are modified.

## Boundary

Slice 3E5 cross-checked caller-supplied registry bytes against a guarded SHA-256 observation. That is advisory evidence; it does **not** give recovery code a natively sourced exact current registry image. Slice 3E6 introduces `_teacher_private_registry_image_snapshot.py`, a narrowly scoped internal read-only exact-byte registry inspection. The older digest-only registry API remains unchanged, and no metadata file is written.

The public entry point for this private module holds the existing **retained registry guard**, including ordered workspace/registry locks and journal-directory/registry identities. Within that guard it verifies the effective OS owner, local protected registry file, identity continuity and canonical v1 registry bytes. Results are sanitized; the optional exact image is deliberately omitted from `repr`. The caller receives **no open file handle**, no reservation, and no authority to initiate a new association, apply a transaction, recover, retire a journal or access Notes.

On Linux, the native reader uses no-follow, directory-relative file opens, owner UID, file mode 0600, link count, ACL and local backing checks, and bounded reads. It compares native and path identity, size, timestamps, owner and parent stability before/after reading. On Windows, it opens with read-only share semantics, verifies the file DACL, local volume, existing coordination file, retained file signature and a separate current-path handle. It rechecks ownership and security after reading. A changed identity, malformed registry, owner mismatch or unknown security condition fails closed.

## Explicit limitations

- A successful result is **not** an atomic joint snapshot with the workspace descriptor or transaction journal. The workspace descriptor is not retained by this module.
- Two independent registry reads are **not** a durable commit and do not guard against other OS users, cloud synchronization, or a non-cooperating process on an external filesystem.
- This slice does not establish crash recovery, replay, journal admission, exact-before CAS, write-target identity, binding commits, initial binding, or Notes data access.
- The internal raw bytes are sensitive metadata and MUST NOT be logged or returned through public UI, exceptions, or diagnostics.
- macOS, network/cloud-backed private stores, and unsupported/unknown filesystem assurances remain unqualified; only Windows and Linux are targeted for native gates.
- Native full-suite Windows evidence and source type/lint checks must come from the guarded runner; isolated tests are not release qualification.

## Gate matrix

1. Canonical exact registry image; malformed/noncanonical, oversized, foreign-owner and empty content refusal.
2. Sanitized refusal states and no record/CLI capability activation.
3. Unsupported and invalid requests; no lock reentry while a retained outer guard is held.
4. Successful guard exit; injected failing exit overrides apparent success; owner drift discards bytes.
5. Linux native fixtures: restrictive 0600 file, missing file, permissive file, symlink, corrupted bytes, owner mismatch and owner-change refusals.
6. Windows repository native tests plus the full Core pytest/Ruff/strict-mypy gates (not attested until execution on Windows).
7. Exact expected baseline, origin, remote, file blobs and clean worktree; automatic commit/push only on complete qualification.

## Handoff

A future **separately guarded** two-tree recovery composer may use this native exact registry evidence alongside an independently qualified workspace descriptor image and retained journal image, with *all* required handles and locks owned by one operation. These bytes alone are never write authorization.
