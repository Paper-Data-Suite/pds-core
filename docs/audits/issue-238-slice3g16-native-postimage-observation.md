# Core #238 Slice 3G16 — Retained native recovery postimage observation

## Purpose and scope

Bridge the 3G14 continuously retained native review and 3G15 pure postcondition
classifier **without introducing a production recovery writer**. Under one existing
retained descriptor/journal/registry guard, examine the currently protected
journal, registry, association descriptor, stage namespace and effective owner.
Observe the byte images twice and classify the exact current postimage against
the corresponding synthetic expected preimage from the canonical pending intent.

This is an internal, non-authorizing review API. It does not expose any handles,
paths, owner information, revisions, image bytes, callbacks, mutation tokens, or
Notes capabilities. The returned result contains only a sanitized enum and
message. No on-disk teacher-private files are modified, created or deleted.

## Allowed observation states

1. `stage_to_registry`: the exact pending journal remains, the native registry
   matches the transaction after-image, the descriptor remains at its before-
   image, the stage is absent, and the requested *pre-operation* revision agrees
   with the canonical witness. Return `stable_postimage_review_required` only
   after two matching native images and final owner/namespace checks.
2. `descriptor_after_image`: the exact pending journal remains, the native
   registry and descriptor match their after-images, the stage is absent, and
   the requested *pre-operation* revision equals the canonical after-revision.
   Two matching native observations yield advisory review only.
3. `journal_retirement`: always return `retirement_unqualified` **before any
   lock acquisition**. The retained scope requires a pending journal namespace;
   it cannot certify absent-journal provenance, its parent-directory durability,
   safe retirement, or an authoritative completed transaction.

The synthetic starting image represents the expected predecessor described by
the pending intent, not a historical observation. Thus **even a matching native
postimage does not demonstrate that this process performed a transition**.

## Refusal matrix

- Wrong operation kind, malformed roots/intent, noncanonical registry transition,
  bad or noninteger revision: refuse before native lock acquisition.
- Stage remaining, no-progress state, missing/malformed native image, incorrect
  journal/registry/descriptor bytes, unexpected stage, conflicting checkpoint:
  preserve evidence and refuse progression.
- Native owner drift, stage/pending namespace changes, inventory drift, image
  drift between passes, missing native custody or failed retained-guard release:
  fail closed, including when the evidence looked correct before the failure.
- Keyboard interruption, unsupported platform, permission denial and native I/O
  failures: return sanitized refusal and preserve all recovery artifacts.

The code uses already-existing native, bounded image readers and the 3G15 pure
postcondition classifier. There are no reentrant readers or untrusted callbacks
inside the guard, and no reusable write permission leaves that scope. The guard
must exit successfully before a review result is returned.

## Boundaries deliberately not qualified

- No mutation/commit/replay/descriptor write or journal deletion.
- No proof of historical preimage provenance, compare-and-swap atomicity across
  devices, resilience against a hostile same-user process, or crash durability.
- No journal retirement, first binding, Notes/Tasks records or permissions.
- No public `notes.records.v1`, `notes.menu.v1`, or `notes.portability.v1`.
- No claim of native Windows qualification until the guarded 3G16 runner passes.

## Qualification plan

Run 91 regression cases for the native guard, current-state image verification,
revision and namespace refusals, interruption, error, and guard-release paths.
Then run focused Core #238 pytest, Ruff, strict mypy and the periodic full Core
suite. Commit exactly three additive files only after every gate is green; pin
all inherited issue files to their original Git blobs, with no resets, stashes,
or automatic cleanup on failure.
