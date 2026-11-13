# Core #238 Slice 3F3 — Retained Registry Stage Inventory

## Baseline and purpose

- Source baseline: `178165db3af8d59e20d73d3bbeb5ad3b911222c1` (Slice 3F2).
- Existing private registry staging writes `.<transaction-uuid>.registry-stage` beside the protected `registry.json`.
- A failed write or flush can leave a stage without a corresponding successfully admitted journal; absence of pending journals does not imply absence of these stages.
- This slice adds a *read-only*, guarded inventory of stage-like filenames, not a stage-image reader or transaction coordinator.

## Qualified observational scope

The API obtains the existing ordered registry/workspace locks and retained private registry, journal-directory, and workspace descriptor guards. Under those guards it observes the owner and inventories the protected registry directory twice. On POSIX it opens the pre-existing parent via the protected no-follow parent opener, compares directory identities and metadata, and inspects stage-entry type, owner, mode, link count, and device using no-follow `stat`. On Windows it checks fixed-local backing, native directory preflight, repeated directory enumeration and basic no-follow stage-entry properties. Unknown or malformed stage-like names are never interpreted as an absence of stages.

The returned result is a sanitized state. It never lists paths or UUIDs, opens stage payload content, clears or repairs artifacts, creates files, promotes a journal, replaces `registry.json`, permits CAS, or exposes Notes. The native observation may be stale after the guard exits. Same-user hostile writers and cross-device/cloud synchronization are not arbitrated.

## Security limitations and next work

This inventory is not an authenticated stage-content proof: it does not prove a staged after-image equals a canonical journal intent, nor does it validate Windows stage-file DACLs. Before any replacement, a future coordinator must (1) qualify stage exact bytes and identity under a held native handle, (2) establish journal admission/durability semantics, (3) compare canonical before-images under retained write targets, (4) perform crash-safe CAS and recovery, and (5) treat all observed remnants as requiring explicit recovery review. Nothing in this slice expands the public Core capabilities or creates Notes records.

## Qualification

Source and synthetic tests must pass focused and full pytest, Ruff, strict mypy, Git hygiene, and exact feature/main pin guards before automatic commit/push. The code has no user-provided private fixtures, notes, or student information.
