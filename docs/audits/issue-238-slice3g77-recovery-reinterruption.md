# Core #238 — Slice 3G77: hard re-interruption inside synthetic recovery

## Baseline and decision

- Base: `ce4b730b098416950eb848ab65dc512d91f24033` (3G76); draft PR #247.
- 3G76 accepted in CI run `43149729062` (15/15 jobs, Windows and Ubuntu), with installed wheel proof of **bounded synthetic** post-death completion.
- **Decision:** exercise a **second real process death occurring inside the recovery operation**, under 3G76's retained native file/parent handles and cooperative operation lock. Distinguish native state after a call may have completed from a pre-attempt state, without relying on phase claims or blindly repeating a call. Do not introduce any production writer or retry protocol.

## Four-file additive scope

- Add `scripts/verify_issue238_installed_recovery_reinterruption.py`, `tests/test_teacher_private_installed_reinterruption_3g77.py`, this audit, and one additive CI installed-wheel step with sanitized artifact. Leave every production source module and all eight prior installed-wheel gates untouched.
- Build a **fresh synthetic canonical FORK_COPY** registry/descriptor/journal plus both stage files in a new temporary root; first kill a separate synthetic writer process before either replacement, then verify its pending-journal checkpoint using a new installed interpreter and operation-held native custody (3G75/3G74).
- Launch a second installed interpreter that enters 3G76's **existing guarded `_recover_one`** operation and (test-only, subprocess-local) replaces its narrow `_native_step` call with a crash marker. Force `os._exit` (no interpreter unwinding) at three precise points: before registry rename, immediately after the registry rename returns, or immediately after descriptor rename returns. The original operation-owned native handles and cooperative lock are held at the forced death. A completed native rename is never retried within that process.
- Verify exact exit status 81/82/83 with zero stdout/stderr; start a separately guarded installed interpreter to **infer** the surviving checkpoint (prepared/registry-only/both-after pending-journal) from filesystem bytes and native IDs. After this independent classification, explicitly run a **new synthetic-only** 3G76 completion rehearsal from the observed checkpoint and require exactly 2/1/0 remaining native operations. A third observation must find both after-images and the journal still pending. This is a deliberate test harness continuation, not automatic production replay.
- Repeat after registry-stage death with three adversarial conflicts: corrupt journal, unexpected namespace entry, or changed descriptor. Both the independent classifier and a bounded synthetic recovery attempt must refuse all three, perform zero writes, and preserve the exact scratch image.
- Keep all output sanitized: fixed state strings, counts, OS, installed wheel digest, boolean claims. Do not emit teacher/student data, registry bytes, caller paths, principals, native handles, or raw file IDs.

## Limits and qualification

- Distinguish `os._exit` from kernel/host failure. The experiment does **not** prove disk durability, multi-document atomicity, security against non-cooperating writers, or production replay. A post-attempt error is ambiguous. The journal remains pending in every passing case. No retirement, READY binding, Notes operations, or production mutation authority.
- Runner exact HEAD/remote `ce4b730...`, clean worktree, workflow blob identity, manifest and file hashes, source AST, four-file-only patch. Qualify focused native tests, Ruff, Linux+Windows strict mypy, fresh installed candidate wheel, all eight previous native gates, and new installed-wheel test; automatically commit/push only on full green. Windows/Linux GitHub CI on PR #247 is decisive acceptance.

## Slice 3G77 Repair 1 — strict ModuleType attribute typing

- The stopped 3G77 local run passed 114 focused tests (3 skips), Ruff, and CI guards, but strict mypy refused two direct assignments to `_native_step` on a dynamically imported `ModuleType` (`attr-defined`, lines 91 and 95). No commit or push occurred.
- Replace exactly two assignments with `setattr(recovery, "_native_step", ...)` under the unchanged `try/finally`, preserving the same private test-subprocess hook, native operation and guaranteed restoration during orderly unwind. Update the single source-contract test literal to inspect the new syntax.
- Preserve all other implementation, the original focused and installed-wheel qualifications, and the pending journal; no production writer, automatic replay, retry, retirement or Notes authorization is enabled.
- Re-run 3G77 tests, Ruff, strict mypy for Linux and Windows, candidate-wheel and all nine installed-wheel gates. Accept only on complete local qualification and independent Windows/Linux CI.
