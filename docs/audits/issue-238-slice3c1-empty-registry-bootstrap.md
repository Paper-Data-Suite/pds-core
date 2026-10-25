# Core #238 — Slice 3C1: Protected empty-registry bootstrap candidate

**Baseline:** `ed24ae2fe010215feaf0987974aad6315f434d51` (Slice 3C0).
**Design authority:** Owner-approved D0 recorded in Core #238 and Slice 3B7 audit; `docs/teacher_private_storage_contract_v1.md`, particularly §§2 and 5.
**Scope:** Internal, opt-in, create-only empty `registry.json` candidate. This is *not* a verified workspace binding, record persistence, cross-document atomic commit, or Notes service.

## Why an empty registry is a distinct operation

The private registry can exist before any workspace association. This slice exclusively creates the canonical v1 document with the effective native owner, registry revision **1**, and **zero** bindings. It does not accept registry bytes, an actor label, user-selected principal, copied descriptor, or arbitrary root from a producer. A subsequent reviewed INITIALIZE operation must treat the empty registry as the prior revision-1 document (not silently assume registry absence), and advance monotonically under the eventual two-document transaction protocol.

Unlike binding initialization, the empty bootstrap writes **one** owner-local document and no workspace sidecar. It does not claim dual-document atomicity. Existing registries of any schema or contents are left byte-for-byte untouched: `ALREADY_EXISTS` does not mean healthy or empty, and future inspection must independently decode and validate them.

## Security behavior

`pds_core._teacher_private_registry_bootstrap.create_empty_private_registry_candidate(existing_private_root)`:

1. Rejects unsupported platforms and paths other than the exact preapproved user-local Notes v1 root. No implicit root, transaction-directory, collection, lock-file, or workspace creation.
2. Requires an existing nonempty `.registry.lock`, acquires its nonblocking cross-process lock, and does not remove or rewrite it. Refuses lock contention or missing/unsafe locks instead of bypassing coordination.
3. Requalifies the parent tree and the existing lock's native protection while coordination is held. Linux uses no-follow directory/file descriptor checks, effective UID, owner-only mode, ACL absence and a strict local filesystem-type allowlist. Windows checks the effective process SID, parent DACL/reparse evidence, fixed NTFS/ReFS backing, and an opened lock-file handle's DACL, size, single link, and reparse attributes. Windows does **not** attempt to read the byte range while it is locked.
4. Derives the exact canonical empty registry bytes from the actual effective owner, and exclusively creates `registry.json` with `O_CREAT|O_EXCL`, mode `0600` (Linux), or `CREATE_NEW` with owner/SYSTEM/Administrators protected DACL (Windows). No overwrite/replacement/ACL repair.
5. Flushes the content, checks new file protection, and returns `CREATED_RESTRICTIVE_UNQUALIFIED` only for a restrictive created candidate. Post-create ambiguity returns `CREATION_UNVERIFIED`, preserves the file for explicit review, and never claims rollback or READY.

**Important limits:** Linux filesystem magic is a preliminary backing filter, not a retention, mount-provenance or crash-durability guarantee. Windows pathname-based reinspection does not supply immutable parent-directory handle continuity or prevent every same-user race; a successful `CREATED_RESTRICTIVE_UNQUALIFIED` is therefore *not* a protected transaction-authority capability. No producer-facing call site invokes this helper. Real installed Windows ARM64 and nonroot Linux qualification, native hostile-reparse adversarial tests, and crash/recovery tests remain mandatory.

## D1 evidence and release barriers

Synthetic unit tests cover canonical zero-binding schema, wrong roots and arguments, missing/unsafe/contended lock, effective UID and protected file mode, unchanged existing unknown registries, dangerous parent mode, unsafe local filesystem, symlink lock, unexpected lock contents, restrictive umask post-create partial state, and absence of Notes capabilities. Windows-native synthetic fixture tests exercise protected root and lock creation, followed by empty-registry creation and duplicate preservation. The Linux test run executed under a non-root local account; the Windows tests run on the owner's real Windows checkout only.

The guarded runner qualifies the additive three-file scope with focused pytest, Ruff, strict mypy, full pytest and remote HEAD/working-tree checks, committing only on success. No site packages or public APIs are changed.

**Still required:** Secure transaction lock ordering across the owner registry and potentially synced workspace descriptor; durable journal/currentness checks; guarded metadata replacement/CAS; recovery and move/fork conflict review; installed platform and adversarial security evidence; eventual #239 Notes record storage. The only existing teacher-experience capability tokens remain `terminal.header.v1` and `terminal.notes_command.v1`.
