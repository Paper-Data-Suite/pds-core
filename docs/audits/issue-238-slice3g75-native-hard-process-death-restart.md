# Core #238 — Slice 3G75: hard process-death recovery under native scratch custody

**Baseline:** `ed5324991d1f1ac6daecff8ba30c6057f9900c33`, draft PR #247.

## Decision

3G74 established a cooperative, operation-held read-only native observation. 3G75 must show that an abrupt writer process termination releases its native handles and cooperative lock, **without** using a Python `finally` block, and that an unrelated installed-wheel process can classify the exact surviving journal and metadata safely. This addresses **process-death** recovery only. It does not claim machine failure, cached-write survival, ACL safety, or OS-specific power-loss durability.

## Scope

Four files: one new installed-wheel scratch verifier, a focused test file, this audit, and an additive CI step/artifact in the existing issue-238 installed-native matrix. Existing installed-wheel no-write, one-file, two-document, fresh-process, triage, and operation-held custody gates remain intact. There is **no production module mutation**.

## Synthetic operation and independent observation

- Construct a genuine fixed synthetic FORK_COPY intent and exclusively create its original registry, descriptor, journal and both stage files in a newly created temporary root. No teacher/student content or caller-selected production paths enter the operation.
- Start a separate installed-Core Python process with a restricted fixed scratch phase. Inside its cooperative lock and while retaining five native file IDs, verify the exact prepared bytes, perform zero, one, or two **single-attempt** same-directory renames, verify stage identity transfer and unchanged pending journal, and terminate with `os._exit` from within the native handle/lock context. The child does not run Python stack unwinding or cleanup. No fallback or retry is permitted.
- Confirm the exact deliberate process exit status. From another installed-Core interpreter, reacquire the operation lock and all native identities, and classify the **actual** surviving checkpoint (prepared, registry-only, both-after-journal-pending) without accepting an asserted phase. Any mismatch blocks.
- Independently reproduce three negative fixtures: after hard exit, tamper with the journal, insert an unexpected name, or alter the descriptor. In every case, a new guarded interpreter must classify `conflict_preserve`. No journal is retired.
- Sanitized evidence reports fixed checkpoint labels, six hard exits, six separately guarded restart processes, and explicit `false` markers for production mutation, automatic replay, retry, retirement, power-loss durability, commit and noncooperating writer exclusion. Never emit private paths, handles, raw IDs or metadata to CI evidence.

## Qualification

Exact local/remote 3G74 head, clean worktree, current CI blob, source file absence, secure source archive manifest, exact source/test/audit hashes, bounded four-file patch, focused pytest, Ruff, strict Linux and Windows mypy, isolated candidate wheel, and the prior six plus new installed-wheel gates. Commit and push only after all pass. CI on Windows and Ubuntu must independently pass.

## Limits and next step

An intentional `os._exit` is not a power-loss or kernel-crash test. The cooperating scratch lock does not exclude noncooperating processes; native file IDs and double-checking do not make two separate renames atomic. Both successful and failed cases remain pending-journal *holds*. Until the durable production transaction and replay/retirement protocol are proven, **production writes, automatic replay, journal retirement, Notes CRUD/menu/CLI, and READY private handles remain disabled.**
