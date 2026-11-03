# Core #238 — Slice 3G17: nonauthorizing operation admission and interruption triage

## Baseline and intent

Base: `5e5bc968515a4767c0f0ad79f7e1073347cd9a18` (qualified Slice 3G16).

This slice creates a private, non-exported operation-admission **review** and a pure interruption-state classifier. Neither executes a recovery operation. Both return sanitized frozen results without paths, private bytes, owner IDs, native handles, a reservation, or a write token.

### Native admission review

`review_private_recovery_operation_admission` maps only the **stage-to-registry** and **descriptor-after-image** operations to the exact compatible 3G14 single-retained-guard review. It supplies the caller's expected registry revision and original proposed transition to the existing 3G14 validator. A 3G14 match becomes `STABLE_PRECONDITION_REVIEW_REQUIRED`, **not** admitted/executable. All other recognized guard states map to refusal/preservation; an unknown native result or exception fails closed. `JOURNAL_RETIREMENT` is rejected *before* invoking the native reviewer.

The 3G14 guard has fully released by the time the sanitized result is returned. The result has **no lifetime, reusability, or CAS semantics**. A future writer must independently reacquire native protection and revalidate all facts inside its own mutation-aware scope. No remote/synced-workspace coordination, hostile-same-user exclusion, or durable persistence is established.

### Untrusted phase and interruption triage

`classify_private_recovery_operation_interruption` accepts a **reported** phase (`NOT_STARTED`, `RETURNED`, or `INTERRUPTED_OR_UNKNOWN`) and two caller-supplied byte images. It delegates canonical transaction-image validation, expected registry revision, precise preimage and postimage checks to 3G15. If the phase is unknown/interrupted and input is structurally/canonically qualified, the result is invariably `INTERRUPTED_PRESERVE`, even if an exact after-image was supplied. A reported return and exact after-image yield `POSTIMAGE_REVIEW_REQUIRED`, not success/durability. A reported nonexecution with changed images produces `UNEXPECTED_CHANGE_PRESERVE`. A reported return with unchanged images produces `NO_PROGRESS_PRESERVE`. Journal retirement remains `RETIREMENT_UNQUALIFIED` in noninterrupted phases, and is never promoted to durable absence.

Reported phases and snapshots are **untrusted statements**, not native proof. No filesystem calls, native write, stage consumption, descriptor update, transaction replay, or journal deletion are performed by this classifier. The two functions are **not an atomic admission/commit sequence**, and their outputs cannot be combined into a write permit.

### Test boundaries

111 synthetic parameterized tests cover native-admission mapping and refusal, type and revision guards, journal-retirement refusal before native review, unexpected guard results and interrupts, each described phase, exact/incorrect before/after image pairs, wrong revision, noncanonical transaction, initialization, exception paths, frozen sanitized outputs, and absence of Notes capability advertisement.

All unit tests use synthetic byte strings and monkeypatched native reviewers. They do not prove Windows or Linux native durability, lock behavior, or filesystem recovery. Windows verification requires the guarded on-device qualification runner; full Core integration was last verified at Slice 3G16 (5,154 passed, 174 skipped). The next milestone must continue with writer-specific native guard lifetime and power-loss protocol design before executing any real mutation.

## Security non-claims

- No recovery mutation, journal retirement, file deletion, durable commit, or OS ACL change.
- No callable/executable write token, callback, permit, or reusable authorization.
- No Initial Association or Notes/Tasks CRUD, CLI/menu, public capability, or portability.
- No proof that submitted phase/image descriptions correspond to real past writes.
- No automatic retry or replay after interruption.
- No security assertion about shared logins, sync folders, untrusted same-user writers, or power-loss recovery.
