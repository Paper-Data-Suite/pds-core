# Issue #238 — Slice 3E7: Native workspace descriptor byte-image review

## Scope

Introduce `pds_core._teacher_private_descriptor_image_snapshot` as a strictly internal read-only observation of the exact bytes of an existing `workspace/.pds/teacher-private-association.json` file. The workspace may be synced and is **untrusted**: the observed descriptor is not a proof of OS ownership or private registry binding. No public dispatch, storage capability, binding commit, journal admission, recovery mutation, or Notes record is provided.

The public review holds existing ordered registry/workspace locks, native private journal and registry anchors, and the workspace descriptor's native file and metadata-directory identity through the retained descriptor guard. Its internal Linux/Windows byte reader never reacquires those locks. The effective OS principal is checked before and after the native read, and guard-exit refusals override a matching image.

## Native observations

- **Linux:** no-follow directory-fd traversal from `/` through the workspace and `.pds`, `O_NOFOLLOW` file opening, regular-file and single-link checks, bounded read, and exact file and parent identity/metadata rechecks against the current path. A descriptor on a synced workspace is **not** required to have the owner-private registry's file mode or private local backing.
- **Windows:** reparse-refusing ancestry checks, a non-following `CreateFileW` read handle with read-only sharing, FileIdInfo-backed file identity from the retained descriptor guard, bounded `ReadFile`, and a second independent handle and ancestry recheck before returning bytes. The sidecar is **not** treated as protected by the private registry's DACL.
- Both paths accept only byte-for-byte canonical v1 association-descriptor encoding. Malformed, truncated, oversized, changed, symlinked or multiply-linked sidecars fail closed; no repair or deletion is attempted.
- Returned exact bytes are internal advisory evidence excluded from `repr`. Messages contain no paths, IDs or descriptor contents. They are not a durability witness, CAS token, safe-to-commit authorization or Notes capability.

## Qualification and residual risk

Regression tests cover canonical observations, invalid content and requests, guard failures on entry and exit, principal drift, Linux symlink and hard-link refusal, mid-read replacement detection, and a native Windows workspace-file read. Windows-native and full-suite qualification are required before merging.

The reader cannot exclude non-cooperating sync writers or attest that bytes are durable on the backing volume. It also does not retain a write target or join the descriptor bytes to the registry and journal under one write-authorizing transaction. Those are separate future gates; creation, initialization absence, durable journal admission, exact-before CAS, crash recovery, binding commits and installed-wheel acceptance remain unimplemented by this slice.
