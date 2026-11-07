# Core #238 — Slice 3G52: Canonical FORK_COPY journaled restart (scratch only)

## Security objective

Exercise a genuinely canonical, *two-document* private metadata transaction across the 3G48 flush ordering and 3G51 independent restart handoff, without treating synthetic evidence as authorization to mutate real teacher-private storage. Prior 3G34 rehearsed a real canonical intent with registry-only replacement; prior 3G51 rehearsed a two-document replacement using synthetic byte strings. This slice tests their missing intersection, including a **FORK_COPY** that changes both the registry and workspace descriptor.

## Entry point and scope

`rehearse_canonical_two_document_restart(interruption=...)` creates all content inside a new `TemporaryDirectory`. It accepts **only** one exact interruption enum. It accepts no caller-supplied path, metadata, owner, image, callback, native handle, recovery token, or retry. It constructs actual schema-v1 metadata, a canonical `PrivateTransactionWitness(FORK_COPY)`, and an encoded and round-tripped `PrivateTransactionIntent`, with fixed explicitly **synthetic** POSIX owner/root labels even on Windows. These values are not an OS owner or production root verification.

The protected registry-stage name uses the pending transaction UUID. The second descriptor-stage name is **disposable protocol rehearsal only**, not a production-authorized namespace or filename. Existing Core production storage will never be opened by this entry point.

## Ordered native scratch operations

1. Create a fresh disposable two-root layout under one scratch-native operation lock. Write exact canonical before-images, exact staged after-images, and canonical pending journal.
2. Require exact names, regular file images and a pure `classify_private_registry_stage_transition` match to the prepared checkpoint.
3. Request native file flushes for the pending journal and both stage files; request native parent flushes for both roots and the journal directory.
4. Confirm the canonical before-image again; make one registry stage replacement; inspect the registry-after/descriptor-before checkpoint.
5. Request registry file and parent flushes; confirm the intermediate checkpoint; make one descriptor-stage replacement.
6. Inspect both after-images; request descriptor file and parent flushes; inspect them again. Never retire or rewrite the journal.
7. **Release the operation lock**; reacquire it in a fresh native scratch scope, reopen all paths, repeat exact image, name, and canonical transition checks, and verify the pending journal remains.

## Refusal and interruption invariants

- All injected faults and real refusals preserve the pending journal **until synthetic fixture disposal**. TemporaryDirectory cleanup is not production journal retirement.
- A replacement attempt may have succeeded even if `os.replace` raised or a post-attempt flush failed; no automatic retry is authorized. The phase and checkpoint are advisory, not proof of prior persistence.
- Unexpected files, mismatched bytes, a missing/malformed stage, altered journal, unknown namespace, or classifier disagreement become `CONFLICT_PRESERVE` or `CANONICAL_IMAGE_CONFLICT_PRESERVE`.
- Restart-lock acquisition/release failure overrides any apparent success. Interrupted operation outcomes are never promoted to a commit.
- No durable-commit state, Notes capability, replay recommendation, stage removal, journal retirement, or production writer is exposed.

## Limitations / next acceptance boundary

This code does not establish native owner/ACL/parent-directory custody for **real** teacher-private files, hostile same-user writer exclusion, transaction CAS, power-loss survival, or a portable Windows durability guarantee. A returned Windows flush request remains `durability_unqualified=True`. The native Windows test result must be confirmed by the user on Windows, alongside Ruff, strict mypy and the focused Core suite. A production implementation must combine the already-protected 3G45 operation-owned scope with a true journaled two-document transaction and restart/retirement protocol in the same guarded lifecycle; **it must not call this scratch rehearsal** as its production writer or accept a review result as execution authority.

## Qualification plan

The guarded 3G52 runner pins the exact completed 3G51 branch and main refs, all inherited Core #238 Git blobs, exact additive three-file scope and source SHA256. It Ruff-formats off checkout (AST-equivalent only), runs 3G52 tests and a native Windows scratch drill, the focused Core #238 tests, Ruff lint and strict mypy. It commits and pushes only after all qualification gates pass, preserving an interrupted checkout for narrow repair without reset/cleanup.
