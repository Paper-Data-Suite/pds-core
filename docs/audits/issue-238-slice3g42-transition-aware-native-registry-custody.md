# Core #238 — Slice 3G42: Transition-aware native registry identity custody

**Branch baseline:** `ac9f7fb7d4d508ce685fa1e26a857c73d4d1c443` (qualified 3G41).
**Main baseline:** `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`.
**Scope:** Three additive files. **No production write.**

## Problem and decision

3G41 gives an operation-owned journal and descriptor guard without a permanent old-registry entry identity invariant. A future legitimate rename must be able to retain native *old* registry and *staged* after-image handles while recognizing that the staged file ID becomes the registry directory entry. The older retained-registry review guard refuses any registry-entry change at release and cannot implement this future transition.

This slice introduces a separate **non-authorizing native identity reader**, retaining the two file handles under the **existing** 3G41 journal/descriptor/ordered-lock guard. It opens the exact `registry.json` entry and the prepared `.<canonical transaction ID>.registry-stage` with read/attribute access, not write/create access. The Linux path uses `O_NOFOLLOW`, native parent verification, UID, mode, link, ACL and local backing checks; the Windows path uses existing native handle, ID, DACL, local-volume and parent-walk primitives with sharing-compatible opens. The identity classifier refuses mismatched parent, detached/changed old or stage handles, missing or foreign registry, premature stage removal, aliases and unexpected extra stage entries. Only a stage file **with exactly the retained staged file ID** may match the post-replacement registry entry with the stage entry absent.

The live entrypoint is strictly **read-only**, checks five native identity observations under one scope and requires the prepared-before state again on context exit. The expected-stage-installed branch is a **typed, tested recovery classification**, not an executable transition, a valid Notes binding or durable success. No handle, ID, path, byte image or callback is returned. Public capabilities and the always-blocking production write barrier are unchanged.

## Critical limitations and work remaining

- **No authorized mutation:** no production `os.replace`, stage consumption, journal retirement, sidecar completion, recovery replay, or Notes/Tasks activation. All outcomes retain pending evidence for review.
- **Identity alone is insufficient.** Native file IDs do not prove canonical bytes, transaction revision, journal identity, owner-to-workspace binding, crash persistence or durable directory flush. The preexisting intent and image guard must be integrated into the same operation-owned scope **before** any production replace.
- Windows operations are read-only and can refuse due to actual sharing policy. `FILE_SHARE_DELETE` is necessary but is not a security grant. Administrators and hostile same-user actors remain outside this local advisory threat boundary.
- Linux filesystem/ACL and Windows effective DACL must be natively qualified. Test-host stubs are not evidence that production permission checks pass; macOS remains unqualified.
- Platform read-only behavior under unsupported backing, changed owner or ambiguous namespace fails closed. An expected file-ID transition may still be nondurable or tampered; **no automatic retry** follows it.
- The 3G40 full Core checkpoint passed **6,864 / 179 skipped**. This slice's Windows runner runs the focused #238 suite, Ruff and strict mypy. Installed wheel, CI/matrix, release and D2 gates remain unqualified.

## Test matrix

- Prepared and exactly staged-installed state classification, both preserving recovery requirements.
- Refuse old/stage/parent identity changes, foreign replacement, missing registry, stage missing before replacement, stage aliasing, invalid native ID and volume types.
- Verify exactly five checks under a single retained guard; refuse every check-point drift, owner change, guard release failure, bad transaction ID or size, and unsupported preflight.
- Native Linux exercise uses disposable files with controlled fixture ACL/backing probes when running unprivileged on Linux; native Windows exercise uses real file handles/file IDs on disposable files with *test-only* mocked protection gates. These prove handle/identity plumbing **not** production DACL/ACL qualification.
- Verify the module contains no file mutation operation or Notes activation.

## Next boundary

3G43 should combine canonical registry and stage bytes, signed-off per-transaction native identity, fresh owner/binding/namespace validation and the transition-aware handles **inside one writer-owned scope**, still with a read-only integration run first. Only after pre/post execution and crash-durability semantics are qualified can production mutation or journal retirement be considered.
