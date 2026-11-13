# Core #238 — D0 acceptance and Slice 3B7 Linux protected-child creation

**Issue:** [Core #238](https://github.com/Paper-Data-Suite/pds-core/issues/238)
**Baseline:** `2ffe1b327e9e048c65e92eec4f84a5b0ba56e452` (Slice 3B6)
**D0 acceptance:** Project owner explicitly approved five architecture decisions in the implementation discussion on 2026-10-25. The decision is also appended to GitHub issue #238.
**Scope:** One internal Linux-native protected child directory creation primitive. No public Notes service, registry or association binding.

## Accepted D0 decisions

1. A non-secret UUIDv4 workspace sidecar is distinct from `.pds/workspace.json`; the verified, user-local protected registry—not a copied sidecar alone—binds the local owner and workspace.
2. Owner scope is the effective native OS principal (Windows process-token SID or POSIX effective UID), never `actor_reference` or a teacher display name. Shared OS accounts are not separated.
3. Moves/ambiguous restores need deliberate review. Rebinding preserves an ID; forking a copied workspace produces a separate ID and does **not** copy private record content.
4. Cloud-synced workspaces may contain only the non-secret descriptor. Actual private Notes bytes remain in verified, OS-user-local storage; cloud propagation is not authorization, coordination, or restore.
5. Unknown filesystem locality, native ACL/ownership/links, locking, or race protection fails closed; no fallback to an unsafe store or active Notes capability.

**Acceptance scope:** D0 approves **implementation of guarded primitives**, including synthetic filesystem tests. It does **not** constitute D1 native-platform or D2 installed-artifact qualification, and it does **not** authorize teacher-facing private Notes persistence. Earlier Slice 1 documents marked “D0 candidate” remain historical snapshots; this decision record supersedes their pending-approval status for the five accepted architectural choices.

## Slice 3B7 implementation

`pds_core._teacher_private_posix_provision.create_restrictive_child_linux` is a private, explicitly called one-level `mkdirat` helper. It requires an already-existing Linux parent with effective-UID ownership, `0700` permissions, no POSIX access ACL, no traversed symlink, and no ancestor that another ordinary user can replace. It opens ancestry using `O_NOFOLLOW|O_DIRECTORY` directory descriptors, uses the held parent descriptor to create the child exclusively with `0700` requested at creation, and reopens/fstats the result. An unknown Linux `statfs` magic, including NFS, FUSE and overlay, is rejected, not guessed to be local. The finite allowlist is **a preliminary local-type filter**, not proof of backup durability, mount provenance or a full storage guarantee.

All outcomes are sanitized; no child path, UID, Notes body or usable storage handle is returned. `CREATED_RESTRICTIVE_UNQUALIFIED` confirms only the restricted child operation, **never** a `READY` association or Notes service. A preexisting child is left untouched; an invalid parent, permissions, ACL, filesystem or platform is refused. If a child was created but its postcondition cannot be established (e.g. a restrictive process umask or race), the outcome is `CREATION_UNVERIFIED` and the newly created directory is **not** silently removed or advertised as usable. Human review remains necessary; no note content has been written.

The operation is deliberately **not** integrated with the actual Notes local-data root or any producer/CLI/menu API; existing `workspace.py`, generic `.pds/workspace.json`, capability tokens and module data are untouched. It cannot create registry/descriptor/transaction/lock files. Windows and macOS return `UNSUPPORTED` from this entrypoint and still require their own native protected creation. POSIX/macOS is not presumed interchangeable with Linux.

## Evidence and remaining gates

`tests/test_teacher_private_posix_provision.py` exercises synthetic Linux child creation with explicit test-only locality mocking, existing-entry preservation, ownership/mode/ACL refusal, parent symlink, backing refusal, invalid names and umask-induced partial state. A **successful mocked-locality test is D1 functional evidence, not real installed D2 locality proof**. Run full pytest, Ruff lint/format, strict mypy, and repository hygiene on the guarded source branch. Actual Windows installed qualification of unrelated preflight remains unclaimed.

Remaining before active private Notes storage: approved owner-scope and private-root provisioning orchestrator; native Windows protected-directory/file creation with explicit current-token ACL and link/locality checks; Linux installed nonroot local-filesystem qualification; protected registry/sidecar coordination; lock-file initial creation; actual transaction journal persistence/fsync/recovery and revision CAS; explicit first binding and move/fork workflows; adversarial and installed-source D1/D2; #239 record storage. MacOS native qualification must either pass or remain explicitly unsupported. No new `notes.*` capability may be advertised by this slice.
