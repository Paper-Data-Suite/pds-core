# Core #238 — Slice 3G51: disposable journaled operation/restart handoff

## Purpose and security scope

Follow qualified 3G50 (`0da193b3879dece3b15e4aa5e7ed20e931fb56cc`) with an **executable, interruption-aware coordinator rehearsal** rather than another isolated read-only classifier. This intentionally uses only fresh `TemporaryDirectory` roots and internally fixed synthetic registry, descriptor, stage and journal images. The entrypoint accepts **only a bounded interruption enum** and exposes no production path, transaction, callback, handle, replay token or writer permit. No production path is opened by the new module.

This slice **does not implement a production transaction coordinator**. It tests handoff rules for its eventual implementation. The production write barrier from 3G33 remains unchanged.

## Concrete operation-to-restart sequence

The new `pds_core/_teacher_private_recovery_journaled_restart_drill.py` reuses the 3G48 scratch file- and directory-flush request primitives and fixed image data. It creates the registry before-image, descriptor before-image, both prepared stages and a pending journal under one disposable native scratch lock. It verifies the complete synthetic prepared namespace and exact byte images; issues file flush requests for the journal and two stages, then parent-directory flush requests for all three locations **before attempting any replacement**. If a request fails, no later replacement occurs and the pending journal remains available for the restart observation.

When preparation succeeds, the module makes **one** registry stage-to-registry `os.replace` attempt. It verifies the registry-after/descriptor-before checkpoint, then requests registry file and parent flushes. It next makes **one** descriptor stage-to-descriptor `os.replace` attempt, verifies both after-images, and requests descriptor file and parent flushes. It does not delete or rename the journal. A native refusal after an attempt is an unknown operation outcome even when the new test-local bytes appear unchanged; it never triggers a blind retry.

After this entire operation scope exits, the module independently **reopens and reacquires** the existing scratch lock, reopens the protected file names, checks the exact pending journal image and entire small synthetic namespace, and returns one of three distinct **hold-only** checkpoints: prepared stage; registry after-image with descriptor pending; or both after-images with journal pending. Unexpected files, symlinks, image mismatch, an unsafe lock, and any reopening refusal fail closed. This is an **in-process interruption and reopen drill**, not a machine reboot or crash simulation. The temporary files are intentionally disposed after the restart observation; the durable evidence-preservation requirement applies to a future production coordinator, not to this scratch directory.

## Refusal and success semantics

| Condition | Required behavior |
| --- | --- |
| Invalid argument or unsupported platform | Refuse before creating scratch |
| Interrupted after prepared journal/stages | Report prepared-stage hold; no replacement attempted |
| Interrupted or native refusal after first replacement attempt | Reopen and report registry/descriptor checkpoint if exact; no automatic replay |
| Interrupted or native refusal after second replacement attempt | Reopen and report both-after checkpoint if exact; no retirement |
| File or directory flush refused | Preserve exact restart observation, classify request unqualified, no retry |
| Restart lock refusal, unexpected namespace or image | Refuse restart classification, never infer completion |
| All flush requests returned and both after-images match | **Scratch observation only**, journal remains pending, durability/retirement unqualified |

All returned review objects are sanitized, contain no paths/bytes/native handles, set `pending_evidence_must_remain=True`, `production_writes_blocked=True`, `automatic_replay_forbidden=True`, `journal_retirement_forbidden=True`, and `durability_unqualified=True`.

## Evidence and outstanding gaps

- Isolated Python/Linux local test suite: 32 passed (including real Linux native file/parent flush requests). The external Windows runner must qualify the Windows-native path, focused Core tests, Ruff and strict mypy before a commit is allowed.
- The separate native Windows probe from 3G49/3G50 returned `requests_returned_unqualified` for all three directory roles. **A returned directory-flush request is not proof of rename or two-file power-loss durability.** This drill does not change that.
- Scratch lock and synthetic file modes do not establish teacher-private root ownership, restrictive Windows ACLs, native production guard or hostile same-user exclusions.
- There is no independently installed crash/restart process, cross-volume operation, durable multi-file CAS, production journal creation, actual descriptor completion or safe journal retirement.
- The 3G47 and 3G50 existing protected native restart readers and policy remain read-only; this drill never passes synthetic observations as production evidence.
- No Notes endpoint or public mutable storage function is added.

## Qualification and delivery

Exactly three additive files (module, regression test, audit), based on the exact 3G50 head and the unchanged `main`. The source-only package has a manifest/hash for each file; the guarded runner requires Windows, exact remote refs, a clean worktree, 256 inherited Git blob IDs, checksums, Ruff AST-equivalent formatting, the 3G51 tests, the 103-file focused Core suite, Ruff and strict mypy. The full Core checkpoint remains deferred after the previously green 3G40 run. On any failure do not commit, push, reset, stash or delete candidate files.

## Next acceptance boundary

Translate the rehearsed operation/restart sequence into the **existing protected transaction-owner scope**, without reusing scratch positive results as write authority. Production rollout remains blocked until explicit native Windows mutation, registry/descriptor/journal recovery, directory persistence policy and safely qualified retirement have been demonstrated together.
