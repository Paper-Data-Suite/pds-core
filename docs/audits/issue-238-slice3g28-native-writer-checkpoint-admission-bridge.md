# Core #238 — Slice 3G28: Native writer checkpoint admission bridge

## Purpose

Connect the only bounded operation rehearsed by the 3G27 synthetic native writer (`STAGE_TO_REGISTRY`) to the already implemented protected native recovery checkpoint classification. **This slice makes no production writes and issues no writer capability.** The returned result is advisory and stale after the existing guard releases.

## Inherited native evidence

`review_native_private_writer_checkpoint_admission` calls `review_native_private_recovery_parent_continuity` (3G22) exactly once, with the explicit `REVIEW_PREPARED_RESTART` checkpoint and the caller's expected registry revision and canonical intent. The 3G22 reader owns the entire retained descriptor, registry and journal scope with ordered local locks; its native classification verifies stage presence, journal/registry/descriptor/stage byte images, native file IDs, stable private and workspace parent identities, namespace inventory and OS owner during the same read-only scope.

A successful 3G22 `PARENTS_STABLE_REVIEW_REQUIRED` status becomes **`PREPARED_EVIDENCE_REVIEW_ONLY`**, not `admitted`, `ready`, `write`, or `committed`. No returned guard, handle, path, file ID, token, byte image, callback or operation permit is available.

## Fail-closed and scope constraints

- Invalid operation enum, revision, intent type or path objects are refused before native review.
- Initialization, descriptor completion and journal retirement are not admitted and do not invoke the native reader.
- Exact typed native reader results are required. Forged objects, strings or unknown states are refused.
- Parent/file identity drift or unqualification, image conflicts, unexpected checkpoint/namespace, revision/step mismatches, owner changes, guard refusals, interruptions and I/O errors are mapped to fixed sanitized non-success states.
- Native reader errors never reveal private paths or metadata in returned text. The positive status cannot be used as a CAS reservation because the underlying native scope has **already released**.
- No writer import call, `os.replace`, stage consumption, private file changes, journal deletion, service registration, or Notes access exists in this bridge.

## Qualification evidence and limits

The local isolated regression suite checks all native classifier statuses; exact positive dispatch and arguments; refusal of unsupported operations and invalid values without I/O; forged-result rejection; exception sanitization; immutable results; non-reentrant delegation; and the actual source-level guard/identity/classifier calls in the 3G22 native implementation. The isolated harness stubs imported types but uses the committed 3G22 classifier's public shape and source for static inspection. Final qualification **must occur on Windows within the full Core repository**, including its focused suite, Ruff and strict mypy.

Local native Windows success would still be a read-only observation, not proof of crash durability, cross-process or cloud exclusivity, or protection from same-user hostile modification. A future real writer must acquire its own continuously held native protection and revalidate **immediately before** mutation; it must not trust this bridge result. Protected production writes, directory persistence, journal retirement, and Notes activation remain prohibited by 3G28.

## Next boundary

3G29 should define a *writer-owned* protected operation scope that retains the required guards while revalidating checkpoint/identities and independently proving suitable native write custody. Qualify only on disposable controlled fixtures first, and do not accept the advisory result of 3G28 as an authorization token.
