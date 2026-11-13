# Core #238 Slice 3F2 — Registry after-image staging primitive

## Scope

This additive slice introduces an internal, create-only, transaction-named
registry after-image staging primitive and synthetic failure tests. The staging
file is a sibling of the existing owner-private `registry.json`, never a
replacement for it. Neither the existing registry nor the workspace descriptor
is opened for writing, renamed, deleted, or modified by this helper.

## Security and durability boundaries

- Input is an exact canonical, validated `PrivateTransactionIntent`; the
  staged data are its canonical `registry_after` bytes, not arbitrary producer
  data. The operation refuses initialization until a separate absence protocol
  exists. The transaction ID determines a fixed suffix filename, not an
  arbitrary caller-supplied path.
- Private root syntax is checked against Core's supported owner-local root.
  Linux requires a verified non-root effective UID, a no-follow parent FD,
  exclusive create, 0600 mode, native owner, link count 1, known local backing,
  absent access ACL, file `fsync`, and parent-directory `fsync`.
- Windows checks the current process-token SID and native restrictive DACL,
  local fixed backing, exclusive `CREATE_NEW`, and create-time explicit DACL;
  it requests write-through and flushes the file. The Windows namespace
  durability limitation remains unresolved.
- A post-create failure returns `creation_unverified` and **preserves** the
  partial stage. Collision never overwrites a foreign or existing stage.
- The stage does not prove that a journal candidate was admitted, or even that
  a qualifying journal exists. The primitive deliberately neither obtains
  ordered locks nor returns a commit token. It is not yet wired into a
  production transaction coordinator or made accessible to Notes or producers.
- A crash or refusal may leave orphan stages in the owner-private root.
  Before any actual binding commit, a later coordinator must implement a
  stage census and recovery/refusal protocol, a retained write-target guard,
  exact-before CAS, atomic install/flush on the supported filesystem, and
  crash-point tests. No automatic stage cleanup is authorized here.

## Review and qualification

The new tests use only synthetic bytes and principals. They exercise Windows
native-call simulation, collisions, inaccessible/foreign owners and partial
write/flush errors; native Linux checks require non-root execution. Full Core
regression, Ruff, strict mypy, and Windows qualification are performed by the
pinned guarded runner before commit and push.

## Invariant

A successful result is **staged_unqualified**, never READY, durable admission,
registry replacement, binding commit, or Notes record authority.
