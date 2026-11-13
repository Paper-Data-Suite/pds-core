# Core #238 — Slice 3F6: retained-guard/write compatibility gate

**Scope:** synthetic regression tests and this audit only; no production writes or
changes to existing native guard semantics. **Baseline:** qualified Slice 3F5
`fff85584c0a797d61c8b0ddf1b6e602d46f3980b`.

## Problem confirmed by source review

The existing retained guards were designed for read-only observation. On Linux:

- `_teacher_private_retained_journal_guard._identity` includes the transactions
  directory's `st_ctime_ns`. An exclusive journal candidate creation commonly
  changes that directory timestamp, even while inode, owner and mode remain
  unchanged. Its post-yield check therefore refuses the scope.
- `_teacher_private_retained_registry_guard._linux_signature` includes both
  `st_mtime_ns` and `st_ctime_ns` of the protected private root. Creating a
  transaction-specific registry after-image stage beside `registry.json`
  commonly changes those timestamps. Its post-yield check likewise refuses.
- A nested descriptor guard includes these retained scopes. Neither a
  `CREATED_UNQUALIFIED` journal candidate nor a `STAGED_UNQUALIFIED` registry
  after-image can be promoted to a transaction authority on the strength of
  those results. A guarded create may leave evidence on disk and subsequently
  be classified as guard-refused. That is safe refusal, not proof the create
  never happened.

Windows guards compare different native handle identities and protections;
that difference must not be treated as proof of Windows namespace durability.

## Regression boundary

New tests construct synthetic stat metadata and use disposable temporary
filesystems, verifying that parent-directory timestamp changes are material to
existing Linux guards even when ownership and inode remain stable. The tests
explicitly preserve the existing fail-closed behavior and keep public Notes
capabilities unchanged. They do **not** weaken or modify the guards.

## Required mutation-aware successor

Before enabling a transaction writer, implement a **distinct explicit
mutation-aware retained scope**, not a broad relaxation of the read-only
scope. It must retain ordered local locks and native file/directory handles;
prove source and destination parent/target identity, owner, ACL, local backing,
exact before-bytes, journal/stage association, and the exact expected namespace
mutation. Revalidate final paths and parent identity after the operation and
refuse any unexpected entries, replacements, hard links or drifts. Reject
non-cooperating same-user writers and cloud/network arbitration claims.

The write-aware scope must document Windows write-through/flush semantics and
POSIX file-then-directory fsync ordering without claiming cross-file atomicity.
It must supply a resumable crash-checkpoint protocol before any metadata CAS or
registry replacement, and an explicit initialization-absence protocol before a
first binding. Production Notes records and public READY/storage handles are
outside this slice and remain disabled.

**Result:** The present read-only guard is an effective refusal boundary, not
an admissible transaction-write guard. A passing test suite here qualifies
that fact, not a working commit implementation.
