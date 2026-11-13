# Core #238 — Slice 3G38: Operation-owned pre-replacement window (NO WRITE)

## Scope and purpose

Build on the qualified 3G36 production-native preflight and 3G37 held stage
identity by keeping **one retained descriptor/registry/journal lock scope** and
**one separately held stage-file scope** across four fresh, exact native checks.
The third frame models the immediate pre-replacement boundary; the fourth frame
checks that the modeled boundary caused no drift. **The boundary is a no-op.**
This module exports no write operation or callback and never calls `os.replace`.

The implementation reuses Core's existing owner inspection, native ACL and
local-backing refusal, canonical transaction codec and inert write description,
retained native guard, stage-handle custody, native namespace census, exact
journal/registry/sidecar/stage images, and current parent/file identities.
It introduces no independently trusted owner, path, metadata, permission, or
untrusted filesystem proof. No path from a journal is used as authority.

## Non-negotiable preconditions

1. Only a typed stage-to-registry step is observed. Initialization, descriptor
   completion, and journal retirement are not admitted.
2. The 3G35 production barrier must return `PRODUCTION_BLOCKED`. This is a
   **mandatory denial**, not an approval or capability.
3. The complete proposed intent must round-trip through the strict canonical
   codec. The exact 3G32 fingerprints are computed before and **again inside**
   the operation-owned guard, including directly before the modeled boundary.
4. Core's independent private-root/owner/native security checks must match;
   owner, registry binding, workspace and stored revisions remain constrained.
5. Four exact frames must match native protected journal, registry, descriptor
   and registry-stage content; stage and registry identities must be distinct.
   Native file stamps, parent continuity, owner and namespace must not drift.
6. The native stage HANDLE/FD must survive all four frames; the inherited guard
   must retain the destination and metadata anchors until after final checking.
   An unsuccessful guard or stage release cannot produce the advisory success.

## Outcomes and limits

`NO_OP_BOUNDARY_OBSERVED_NO_WRITE` is a **post-release advisory observation**.
It is not a reservation, permit, durable compare-and-swap, writer execution,
transaction commit, recovery decision, or safe replay instruction. Failure states
are sanitized and preserve pending evidence. The result object contains no
path, user identifier, handle, bytes, callback or executable authority.

**Not yet qualified:** production stage-to-registry mutation, hostile same-user
writer exclusion, Windows replacement sharing at the actual production boundary,
parent directory-entry durability, cross-device/cloud serialization, crash-safe
journal progression and retirement, first-binding initialization, or Notes.

## Regression and acceptance

The accompanying tests exercise the operation/argument refusal surface, frozen
sanitized results, all nine stage-handle check positions, stage versus registry
versus journal/descriptor identity drift, four exact byte-image conflicts, owner
and namespace drift, in-guard canonical fingerprint drift, modeled fourth-frame
continuity, interruptions, and failed guard/stage release. Isolated dependency-
stub testing does not substitute for the guarded native Windows qualification.

The guarded runner must verify the exact feature-branch baseline and inherited
Git blobs before applying the three additive files, then qualify the focused
Core #238 suite, Ruff, strict mypy, and a conditional commit/push. The last full
repository checkpoint remains 3G30 (6,191 passed / 176 skipped); do not rerun
that checkpoint on every incremental slice.

## Next step

3G39 should establish a **bounded, fail-closed pre-replacement transition
contract** for the real operation, including exact Windows sharing/reopen
constraints and explicit crash-state expectations, without interpreting a
previous advisory finding as a write permit. Do not activate production writes
until durable replace/recovery and security custody are qualified together.
