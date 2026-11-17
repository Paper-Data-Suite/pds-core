# Core #238 — Slice 3G93: Windows `ReplaceFileW` postcheck-to-call race

## Objective and bounded trust boundary

3G92 demonstrated a native Windows `ReplaceFileW` backup on a fixed, synthetic
registry and stage. This follow-on documents a gap: retaining a parent directory
HANDLE and a cooperating lock does not make a **path-based** `ReplaceFileW`
conditional on the file identities observed before an uncooperative process ran.
The diagnostic accepts exactly one fixed scenario enum, allocates a disposable
OS temp root, and uses constant names and bytes. It cannot open a real private
root, teacher workspace, Notes record, caller path, callback, or actual intent.

## Deterministic native scratch exercise

The diagnostic creates a registry before-image, stage after-image, pending
journal, and lock. While holding the established cooperative OS lock and native
parent DIRECTORY handle, it verifies exact images and native file identities.
Then it does **one** of the following:

1. Normal baseline: call `ReplaceFileW` with a fresh backup name.
2. Live race: a separate Python interpreter, ignoring the lock, substitutes an
   equal-byte, *different-identity* registry file after the final precheck.
3. Stage race: that independent interpreter substitutes an equal-byte,
   different-identity stage after the final precheck.

The scratch-only caller intentionally proceeds after the race and calls the
same 3G92 `ReplaceFileW` helper. It requires an exact new registry image, exact
backup content, a consumed stage name and an unchanged pending journal. A
successful postimage **does not prove** that the kernel checked the original
preimage identity or content. This is a deliberate negative demonstration, not
a transactional writer implementation or safe response to observed drift.

## Important limitations

- Windows sharing tests in 3G91 apply to open handles; no watched-file handle
  excluding FILE_SHARE_DELETE is held in this deliberate postcheck race.
- `ReplaceFileW` remains path-named; a same-owner uncooperative writer can act
  after a cooperative check. Backup bytes may match an original image even
  when an unobserved replacement occurred.
- The test rejects unsupported filesystems or platforms and any unexpected
  native result rather than claiming broad Windows guarantees. Linux refuses
  this Windows-specific protocol before creating scratch.
- `ReplaceFileW` partial failures must preserve evidence and cannot authorize
  blind retries. Power-loss ordering, multi-document atomicity, owner/ACL,
  real descriptor binding, protected native handles, stage/journal retirement,
  recovery and live Notes remain separately unqualified.

All nine production-operation blockers, the immutable production write barrier,
original terminal capability set, and no-replay/no-retirement/no-Notes boundaries
remain unchanged.

## Qualification

The 25th installed-wheel gate checks the three native Windows scratch scenarios,
explicit Linux refusal, exact installed candidate wheel provenance, bounded
sanitized result labels and all negative authority flags. All 24 previous gates
remain enabled. The guarded delivery requires exact 3G92 Repair 1 baseline,
remote SHA, CI blob, no worktree dirt, no collisions, strict Ruff/mypy, focused
pytest and 25 installed-wheel gates before conditional commit/push.

## Next engineering gate

Design a **cooperating-writer** transaction and journal-recovery protocol with
explicit checkpoints and conservative recovery from uncertain rename/replace
states. Do not claim that Windows or Linux offers an atomic expected-content
compare-and-swap against hostile code sharing the same OS identity. Keep
production write authority closed until the real root, binding, ACL, journal,
interruption and durability conditions are qualified.

Reference: Microsoft's `ReplaceFileW` documentation:
https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew
