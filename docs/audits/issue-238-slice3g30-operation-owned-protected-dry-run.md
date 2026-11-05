# Core #238 — Slice 3G30: Operation-owned protected checkpoint dry-run

## Decision and scope

Integrate the prepared stage-to-registry recovery checkpoint with the existing **retained protected guard**. Unlike 3G28, this review does not complete its check and transfer an advisory result to a separate scope. Instead, it acquires `_hold_existing_retained_descriptor_guard` **once** and retains the native descriptor, registry and journal protections, local ordered locks, and effective owner across all three checkpoint frames and the final parent/namespace review.

The three frames are: pre-admission, the **non-mutating operation boundary**, and post-boundary review. These are intentionally read-only frames; the middle frame does **not** execute the synthetic or production writer. There are no external callbacks, writer tokens, exported handles, raw images, or paths in results. No nested invocation of 3G22/3G28 (which would reenter the coordination locks).

## Existing contracts actually reused

* Existing descriptor/registry/journal retained guard: `_teacher_private_retained_descriptor_guard._hold_existing_retained_descriptor_guard`.
* Existing native protected namespace, ownership, exact-image and checkpoint routines: `_teacher_private_recovery_operation_guard._same_native_namespace`, `_teacher_private_ordered_coordination._owner`, `_teacher_private_recovery_exact_revision_review._images`, `_teacher_private_postcrash_reconciliation._classify_present`.
* Existing native identity census: `_teacher_private_recovery_native_identity_bridge._census`, and four parent-directory stamps from `_teacher_private_recovery_parent_continuity._parents`.
* Canonical intent and registry revision validation before protected guard acquisition.

Only a canonical, **existing** prepared `STAGE_TO_REGISTRY` rebind checkpoint is reviewable. Initialization, descriptor completion, journal retirement, and revision mismatch are refused before opening any protected scope.

## Qualification criteria

1. Exactly one protected native guard is acquired and released across three consecutive frames; observations run only while that guard is active.
2. Each frame requires matching staged namespace, owner, canonical pending intent, exact registry/descriptor/staged bytes, expected recovery classification, parent stamps and file identities/lengths.
3. Parent and file identity drift, byte drift, owner or namespace changes, forged/malformed frames, and exceptions fail closed.
4. Guard release failures override any otherwise matching result; interruption never reports a completed boundary.
5. Results are immutable status and fixed sanitized message only. No production writes, native writer hooks, reentrant guard, staging, journal unlink, CAS token, or Notes activation.

## Deliberate limits

A matching status is a **dry-run observation after all native guards have released**. It is neither permission to mutate protected teacher-private files, an exclusive same-user adversary defense, a durable commit proof, nor a checkpoint for journal retirement. Reader handle sharing, native directory durability and crash recovery remain separately unqualified. This slice adds no public writer or production mutation path.

The regression suite includes a synthetic protected-guard harness, native helper delegation tests, failure-injection matrix and frozen/status boundary assertions. The full source is to be qualified on Windows through the guarded runner, focused Core suite, Ruff and strict mypy before commit/push. Full pytest was last qualified in 3G24 (5,749 passed / 176 skipped); this slice restores a periodic full Core pytest checkpoint after six focused slices.

## Next implementation boundary

3G31 should close the **prepared stage replacement writer capability gap** using a bounded operation-owned adapter that cannot consume a previously released advisory result; it must retain native custody across read / prepared CAS precondition / native mutation / postimage inspection. Do not activate production writes until a separate durability and interruption protocol is qualified.
