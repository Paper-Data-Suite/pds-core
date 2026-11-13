# Core #238 — Slice 3G36: guarded native production-prerequisite preflight

**Baseline:** `945de653f5a2247f2dbc6f88a62bfb415e5eefca` (qualified 3G35).
**Scope:** additive, private, read-only preflight; no public API, no production mutations, no Notes activation.

## Purpose and implementation

Connect Core's existing preliminary OS-principal/private-root inspection,
platform-native ACL/mode/backing checks, production write-denial barrier, and
retained descriptor/registry/journal guard to a *single* review of a proposed
canonical stage-to-registry recovery state. The new entry point is
`review_protected_production_native_prerequisites`. It accepts the existing
operation enum, expected revision, canonical transaction-intent object, and
existing private and workspace `Path` values. No raw writer callback, handle,
lock token, authorization boolean, or capability can be passed or returned.

The procedure first rejects unsupported operations and invalid arguments,
checks the established 3G35 production barrier, canonicalizes the transaction
bytes, requires the private root to equal Core's independently inspected
per-OS-user candidate, and observes the platform-native protection preflight.
It compares the canonical before/after registry owner fields to the effective
process owner and checks the exact proposed association's after-root against the
workspace path. Rebinds must have a genuinely different prior root.

It then enters **one** existing retained descriptor guard. Within that guard,
it re-decodes the intent and rechecks its exact serialization and binding,
re-observes Core's own private-root candidate and effective OS owner, and
repeats the native protection preflight around three exact protected recovery
frames. Each frame checks native namespace continuity, effective owner,
expected pending journal and metadata bytes, native parent/file identities,
and the prepared recovery checkpoint using already established private helper
contracts. The guard must also release without error. A refusal preserves
existing pending evidence; nothing is written or removed.

The only positive observation is `PROTECTION_OBSERVED_NO_WRITE`, a **stale,
non-authorizing finding emitted after successful guard release**. The return
object always carries the **entire** list of still-unqualified production-write
requirements from 3G35. This includes the owner/ACL requirement because the
present probe does not verify the target writer's final native mutation scope.

## Security limits and omissions

- Preliminary root inspection and native ACL/mode checks are read-only
  observations, not a production storage handle, complete Windows DACL
  authorization, hostile same-user-writer exclusion, or distributed lock.
- Reopening a path during a retained guard does not give a caller a durable
  compare-and-swap, independently protected destination file handle, or
  directory-entry persistence guarantee. For production writes, the final
  operation-owned writer must retain verified native custody across the actual
  mutation and independently re-establish the entire barrier taxonomy.
- Cloud-synced and network-backed workspaces do not gain distributed
  coordination guarantees. Unsupported accounts, inaccessible roots, unsafe
  reparse/symlink paths, and unqualified ACLs must fail closed.
- No `os.replace`, file creation, filesystem persistence, journal retirement,
  recovery replay, descriptor completion, Notes records or menu activation.
- No sensitive owner, path, byte image, digest, handle, or credential appears
  in an outcome or routine error message. Only synthetic test metadata is used.
- All existing issue #238 dependencies on Core #236/#237 and eventual Notes
  issues #239/#240/#243 remain unchanged.

## Regression and qualification

The isolated dependency-stub regression suite exercises 66 cases: stable
three-frame one-guard review, immutable sanitized outcome, invalid types and
operations, unknown private roots, unqualified native protection and ACL
reversal, owner and binding mismatch, namespace and image conflict, change
of canonical decoded intent under the guard, malformed serialized data,
interruptions, guarded release failure, and non-authorizing exports.

**Local isolated checks:** 66 passed; Python syntax passed. The isolation
stubs exercise orchestration only and do **not** qualify platform-native
filesystems or substitute for Core's installed dependencies.

**Windows acceptance gates:** exact clean 3G35 HEAD and remote refs; 211
inherited Git blob pins; three additive files; new regression module; 88-file
focused Core #238 suite; Ruff check/format; strict mypy; exact staging scope;
conditional commit and push. The full Core checkpoint remains deferred after
3G30's 6,191 passed / 176 skipped, with periodic full validation still needed
before closing #238.

## Next boundary

3G37 should establish and test **writer-owned native destination and staged-file
custody requirements** without enabling production replacement, moving the
preflight observations toward a provable operation-owned preimage/rename window.
Any final production commit, directory durability, journal retirement, and
Notes activation remain separate, explicitly unqualified gates.
