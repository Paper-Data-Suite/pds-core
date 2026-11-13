# Core #238 — Slice 3C2: Locked, read-only owner-registry snapshot

**Pinned baseline:** `c2ee31f1323db7a2b9969e4fd41f99d5f7e3a90b` (Slice 3C1)
**Authority:** D0 approval recorded in issue #238 and the 3B7 audit; storage contract v1 §§2, 4–5.
**Qualification status:** Non-authorizing inspection primitive, not a READY/record service or commit/plan token.

## Boundary and purpose

The create-only Slice 3C1 bootstrap can leave a protected `registry.json` candidate, but the later binding plan must distinguish a genuinely missing registry from a corrupt one, and verify actual effective OS ownership and on-disk bytes **while** coordination is held. This slice adds `pds_core._teacher_private_registry_snapshot.inspect_existing_private_registry(existing_private_root)` and nothing to public service dispatch. No file or directory is created, truncated, repaired, renamed, or deleted. No binding or journal write occurs. No Notes record or capability is exposed.

The helper requires the exact approved local v1 private-root path and an existing, exclusive `.registry.lock` acquired through the Slice 3B6 noncreating cross-process helper. It requalifies the lock and parent before reading an existing `registry.json`. It reads through a no-follow, parent-relative descriptor on Linux or a nonsharing Windows `CreateFileW` handle with `OPEN_EXISTING` and `FILE_FLAG_OPEN_REPARSE_POINT`, refuses unexpected file types/links/modes/ACL/volume evidence, checks the strict canonical v1 registry codec and effective principal, and rechecks supporting evidence before returning an observation.

A bounded result contains only a sanitized state, registry revision, binding count, and SHA-256 digest. It deliberately omits registry bytes, owner SID/UID, accepted workspace paths, association IDs, file path, writable descriptor, and a READY state. The digest and revision are **not authorization, a CAS reservation, a session secret, or immutable future facts**. The future transaction writer MUST reacquire and independently reverify exact bytes, owner, registry/descriptor coordination and all security properties under the actual commit lock set.

## Refusal semantics

- `MISSING` is returned only when the qualified existing root and lock are present and the registry itself is absent. Missing registry **does not** imply no private Notes.
- `CORRUPT_METADATA` covers malformed, noncanonical, zero-byte, oversized or unsupported-version content. Existing bytes remain untouched.
- `OWNER_MISMATCH` covers an otherwise valid registry whose owner principal or kind does not match the effective native owner.
- `REFUSED_PROTECTION`, `REFUSED_BACKING` and `ACCESS_DENIED` keep native security distinct from malformed content. A missing, unsafe or contended lock is `COORDINATION_UNAVAILABLE`. An incomplete or racy read is `IO_ERROR`.
- `OBSERVED_UNQUALIFIED` is the strongest result and **never** means a bound workspace or usable private Notes storage.

## Adversarial limits and next gates

Read-time checks and nonsharing Windows file handles reduce exposure but do **not** prove that an existing registry and a synced workspace descriptor form a durable cross-tree transaction. Windows directory handles are not retained across the later operation, Linux backing allowlists are preliminary, and cooperation by a different process cannot be inferred solely from a lock-file convention. This module does not resolve same-OS-account hostile programs, backup/sync durability, reparse/volume changes outside held handles, or unqualified filesystems. No automatic migration, repair or implicit new registry creation is allowed.

`tests/test_teacher_private_registry_snapshot.py` covers pure v1 interpretation, canonicality, mismatched owners, sanitized fields, noncreating missing/corrupt handling, nonroot Linux filesystem behavior, protected file modes and symlink refusal, lock contention, backing failures, and guarded synthetic Windows-native fixture construction. Linux tests run as a **nonroot** local user; native Windows and full repository Ruff/strict-mypy/pytest remain gates on the user's checkout. A platform-specific skip must never be described as native qualification.

Next: coordinate a workspace descriptor guard separately from the protected registry lock; establish precise owner-currentness and CAS preconditions, then guarded journal-first registry/descriptor updates with interruption reconciliation. No `notes.records.v1` capability, public Notes APIs, or record writes under Core #238.
