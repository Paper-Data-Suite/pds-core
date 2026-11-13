# Core #238 — Slice 3G34: Disposable canonical two-root replacement

## Intent and boundary

Integrate the genuine canonical `PrivateTransactionIntent` (`3B4`), the inert typed
`PrivatePreparedWriteDescription` (`3G32`), the four-parent native retained
custody from `3G29`/`3G31`, and the actual scratch stage-to-registry filesystem
replacement. This is a **fixed, internal, synthetic-only integration rehearsal**.
It is NOT a continuation of an actual 3G33 production protected guard; 3G33
remains a read-only verifier and grants no mutation authority.

The only externally callable function is
`rehearse_synthetic_canonical_two_root_replace(step, interruption)`.
Its arguments are exact bounded enums; it accepts no source paths, metadata
bytes, owner, callback, native handle, transaction ID, or preapproved review.
It creates a fresh disposable `TemporaryDirectory`, two independent scratch
roots, and a v1 canonical REBIND_MOVE transaction with a **synthetic and
non-authoritative** POSIX owner label (`1000`) and fixed synthetic root strings
(`/synthetic_before`, `/synthetic_after`). Those labels NEVER describe a real
teacher or grant identity privileges even when the rehearsal runs on Windows.

## Native scope and exact checkpoint

1. Construct genuine v1 association descriptor/registry 2→3 and a canonical
   `PrivateTransactionIntent`; verify encode/decode equality and obtain its
   inert 3G32 fingerprints. Only the single `STAGE_TO_REGISTRY` enum is admitted.
2. Create **internally owned** journal, before-registry, staged after-registry
   and descriptor as separate regular files in two disposable roots.
3. Hold a native scratch byte lock plus all **four** parent directory
   FD/HANDLEs throughout canonical admission, the old-registry restrictive
   read, three independent full preimage checks, a single `os.replace`,
   exact postimage verification and file-only sync request.
4. Verify fixed namespace, full exact canonical pending journal, registry,
   descriptor and stage byte images, regular-file/no-extra-hardlink shape,
   native file identities and continually held parent identities. The active
   locked byte is checked by shape and native identity, not by a prohibited
   second read on Windows. Close the restrictive Windows registry reader
   before the replace attempt.
5. Require the prior staged file ID to become the registry file ID, with old
   registry ID displaced; unchanged transaction journal, descriptor and lock
   identities; and stage absence. Verify again after file-only fsync request.
6. Release all native parent handles and scratch lock. Return a **sanitized,
   non-authorizing** status. Injected interruptions never assert completion.

## Known security limitations

- Scratch lock is NOT production owner/ACL/backing-media qualification, an
  interprocess CAS, or a defense against an uncooperative same-user process.
- No production filesystem path, private user directory, workspace marker,
  journal, real teacher identity, or Notes record is written.
- `os.replace` and target file fsync cannot prove Windows/POSIX directory-entry
  durability or protect against crash windows; pending transaction remains.
- No production writer, descriptor completion, journal retirement, Notes CRUD,
  portability, capability advertisement, CLI, or menu is enabled.
- The fixed synthetic owner does not match the effective Windows SID and must
  never be passed as a proof of ownership to an actual protected writer.
- TemporaryDirectory cleanup is only cleanup of internally generated synthetic
  files; no user data are removed.

## Qualification plan

- Run dedicated isolated/synthetic regressions on Linux and native Windows:
  canonical codec round trip, first revision/description, exactly one native
  operation, retained parent custody, all injected interruption boundaries,
  invalid enums, read refusal, before/after image drift, OS-denied replace,
  guard refusal, no caller-controlled paths/bytes or returned permit.
- Exact branch and baseline pin verification: 3G33 HEAD
  `368da58f5ed2a01a371504ab8afa4dc456ce9fee`; preserve inherited Git blob
  pins and require the branch and main refs to match before mutation.
- Guarded runner performs off-checkout Ruff-format/AST checks, adds exactly
  three files, executes focused 3G34 and Core #238 tests, Ruff and strict mypy,
  then conditionally commits/pushes. Preserve candidate files on all failures.
- Full Core checkpoint remains deferred after 3G30 (6,191 passed, 176 skipped).
  The issue cannot be closed without a current full Core qualification and
  separate production owner/custody, persistence and recovery acceptance.

## Next engineering boundary

Slice 3G35 should **not** simply repackage a previous advisory finding into a
write permit. It must isolate the production-eligible mutation requirements
(verified effective OS owner, ACL/backing custody, guard-held file and parent
identities, exact canonical byte state, namespace and revision CAS) and supply
an explicit fail-closed transition contract before allowing any real protected
registry replacement. Implementing production mutation requires separate native
platform qualification; no Notes activation is implied.
