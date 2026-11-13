# Core #238 — Slice 3G37: Retained native destination/stage custody

**Baseline:** `0437df7eb58c583d78db3a04fc1999ae974ebc54` (qualified 3G36).

**Scope:** Additive, read-only recovery inspection. No public Notes service or recovery mutation.

## Contract and observations

The existing `retained._hold_existing_retained_descriptor_guard` retains ordered
local locks and native registry, transactions/journal and workspace descriptor
handles. Within that same scope, 3G37 retains an additional native handle for
the exact prepared registry stage and its private directory. Both sets of
handles remain inside Core-owned context managers until the last check.

A canonical, non-initialization stage-to-registry intent must pass the 3G35
production barrier (which **remains blocked**), match the current process owner,
Core-qualified private root, and the accepted workspace binding. The exact
canonical transaction is decoded again inside the held guard. Three repeated
protected observations check the journal, old registry, descriptor, and staged
registry bytes, the native file census and parent stamps, and stable
transaction namespace. The new stage handle is checked before and after each
frame, after final owner/namespace checks, and when its context exits.

For Linux, the stage is opened relative to a verified private directory FD
using `O_NOFOLLOW` and `O_RDONLY`; its entry and held FD must keep the same
native signature, owner UID, mode `0600`, single-link shape, size, absent
access ACL, and qualified local backing. For Windows, Core's existing native
read-attributes handle, FileId/metadata signature, DACL validation, fixed
local-volume checks, and independently reopened path checks are reused.
No stage handle is returned, and no stage file or private directory is created.

## Failure modes

Malformed requests, initialization, revision mismatch, stale/changed intent,
private-root or binding mismatch, unavailable native protection, stage open
failure, changed stage/registry identity, changed owner, namespace/image drift,
interruption, guard/release failures and unexpected native I/O fail closed.
Results are sanitized fixed enum/message pairs and an unchanged list of all
unqualified production-write requirements; no paths, owner values, bytes,
handles, callbacks, or permission tokens escape.

## Explicit limitations and next boundary

These retained observations are **not a protected production compare-and-swap**.
An uncooperative same-user or privileged actor may still mutate data outside
PDS's cooperative local locks. A preflight result becomes stale when its guard
releases; a future writer must repeat all required checks in the very same
operation-owned guard immediately around its actual mutation. The checks do
not qualify durable parent-directory replacement, crash recovery, rollback,
metadata pair commit, journal retirement, cloud/distributed coordination or
Notes activation. Windows native tests and the focused Core suite must pass
before the slice can be committed, and broader installed/classroom acceptance
remains outstanding for issue #238.

## Qualification

- Local isolated dependency-stub suite: 59 passed, 1 Linux native case skipped
  because the isolated runner has a root EUID (Core intentionally disallows it).
- Source archive manifest and runner syntax: checked at packaging.
- Native Windows test, focused issue suite, Ruff and strict mypy: **pending**.
- Full repository checkpoint: deferred after 3G30 (6,191 passed, 176 skipped).

**Suggested next slice 3G38:** Write-window planning with an operation-owned
pre-replacement snapshot and explicit refusal classification, without enabling
a production replacement or journal retirement.
