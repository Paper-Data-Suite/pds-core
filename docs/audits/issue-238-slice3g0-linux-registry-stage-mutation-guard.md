# Core #238 — Slice 3G0: Linux registry-stage mutation-aware native scope

**Baseline:** qualified 3F9 `d1f6bd04c3eba32992dcc33c7ac4fc287b297e95`.
**Scope:** one additive Linux-only internal guard, one regression module, and this audit. No existing code changes.

## Boundary

- Existing immutable registry guard checks private-root timestamps. Creating a
  registry stage changes those timestamps and invalidates a legitimate read-only
  guard. The new independent Linux stage scope therefore retains an open native
  private-root directory descriptor and a separate, original `registry.json`
  descriptor, without using the timestamp-sensitive immutable registry scope.
- Native private-root identity and protection remain verified through `fstat`
  plus independent no-follow path lookup: device, inode, owner, mode, link count,
  0700 owner-private directory, no ACL, known local backing and effective UID.
  Only root *mtime/ctime* may change as a consequence of the expected new entry.
  The live registry retains its **complete** native file signature, owner-private
  0600 protection, link count one, no ACL and local backing; it is independently
  looked up again by name after the scope. The parent directory and live file
  descriptors are retained until normal exit.
- Existing local ordered coordination, immutable journal-directory guard and
  workspace `.pds` descriptor guard remain in force. The journal directory is
  not mutated in this scope. All stage operations require an existing, unique,
  canonical matching journal; exact native pre-image reads of the live registry
  and workspace association must agree with the proposed intent both before
  and after the expected stage addition.
- A double directory listing of the *whole* private root is taken before and
  after. The only allowed delta is one canonical transaction-specific
  `.<UUID>.registry-stage` name. An unrelated addition, removal, rename,
  malformed stage-like name, existing stage, unexpected journal, or mismatching
  metadata refuses the operation. Native stage inspection checks immutable
  file identity, same principal, 0600 permissions, no ACL/hard-link, and exact
  after-image bytes twice; failure does not trigger deletion or rollback.
- The helper itself creates **no files**; a future coordinator must explicitly
  invoke the separately qualified exclusive-create, fsync file/parent primitive
  inside the retained scope. No stage result or normal guard exit is a durable
  journal, atomic CAS, binding, Notes permission, write handle or replay token.

## Constraints and remaining risks

An expected set delta plus retained local file/parent descriptors does not
prevent hostile same-owner writers from mutating a directory and restoring its
listing between scans. Nor do local advisory locks serialize cloud or network
writers. POSIX file/parent `fsync` requirements are provided by the separate
create-only primitive, not by this guard. Windows remains addressed by the
separate 3F9 native Windows stage guard.

Before enabling metadata mutation, implement a coordinated mutation protocol
which also proves durable journal admission, exact-before CAS, crash recovery,
write-target continuity and transactional checkpoint handling. A separate
protected absence protocol is required for first initialization. Public
teacher Notes capabilities are unchanged.

## Validation

Synthetic tests enforce expected single-stage delta, wrong/extra/removal names,
preexisting stages, unrelated pending journals, before-image disagreement,
stage bytes and journal bytes mismatch, owner drift, retained anchor refusal,
non-authorizing capabilities, and unsupported platform behavior. Disposable
native POSIX tests run under an unprivileged Linux account and verify the
retained root and registry identity: one new stage is allowed while replacing
registry.json or weakening 0700 parent protection is refused. Native tests
are skipped on Windows and when run as root.
