# Core #238 — Slice 3G97: retained native custody and fresh identity review

## Scope and reason for the gate

The accepted 3G96 persistence review holds uncertain on-disk checkpoints without
replay, but a byte-for-byte snapshot cannot by itself distinguish an unchanged
file object from an independent same-byte replacement. 3G97 adds a *native
identity-vs-contents* check while a parent-directory handle remains retained.
It remains a fixed-enum, newly allocated disposable experiment with no caller
paths, owner identity, teacher records, workspace root, note content, transaction
intent, or write authorization. Parent-directory retention is not handle-relative
replacement, content CAS, or a guarantee against noncooperating writers.

## Reproducible process and native window

The experiment creates fixed 0600 synthetic registry, descriptor, stage, journal
and lock files. A separate 3G95 producer runs a fixed 3G94 checkpoint sequence
and hard-exits with an expected status. The caller acquires the existing Core
cooperative lock, obtains exact byte images and opened-file native identity
(device/inode/size) for registry, descriptor, stages and journal, then releases
the lock. It retains the real native parent-directory handle across the
competing child and fresh read-only inspector. The inspector reacquires Core's
lock independently. After inspection, both current bytes and file identities
must be identical to the immediately preceding observation. No recovery or
journal retirement is executed.

Six cases are checked:

1. An unchanged registry-replaced but unacknowledged checkpoint is held uncertain.
2. An unchanged `both_pending_review` journal remains pending manual review.
3. A child ignores the cooperative lock and replaces live registry with an
   equal-byte different-identity file after the initial observation.
4. The same equal-byte substitution is repeated for the registry stage.
5. The same equal-byte substitution is repeated for the pending journal.
6. A child modifies registry bytes in place; the native identity is retained
   but the classifier correctly identifies conflicting file contents.

For cases 3–5, the fresh journal/image classifier returns the same logical
state as before the substitution. 3G97 nevertheless detects changed device/inode
identity and produces an explicit **hold**, demonstrating why a previous read of
contents is not sufficient transaction custody. For case 6, changed size does
not by itself imply changed inode: compare file identity independently of size.
All six retain the pending journal and prohibit recovery or replay.

## Supported limits and nonclaims

The child uses internally chosen temporary paths and a single fixed entry name,
not a caller-supplied destination. Retaining a parent-directory fd/HANDLE does
not pin every contained filename; short-lived per-entry file descriptors do
not prevent a later rename. On Linux, entry opening requests O_NOFOLLOW; on
Windows a native parent HANDLE is retained through Core's existing helper.
Native inode/file-ID availability varies by filesystem: unsupported or
contradictory values fail closed instead of authorizing a transaction.

Neither a valid content hash nor a detected identity mismatch establishes
power-loss ordering, a general security exclusion of same-account processes,
production owner/ACL custody, or a kernel expected-content compare-and-swap.
Only *cooperating* writers honor the advisory Core lock. An unexpected native
result produces a sanitized refusal. No real private root, Notes record, active
binding, automatic replay, journal retirement or cross-root transaction is
accessible through this probe. All nine production readiness blockers remain
open and the terminal-only public capability set stays unchanged.

## Qualification

Fourteen focused tests cover six native scenarios, five malformed enum inputs,
requirement drift, unsupported-platform refusal and the public no-authority
boundary. The 29th isolated installed-wheel gate repeats six scenarios,
counts exactly sixteen fresh Python interpreters, verifies candidate-wheel
origin, all negative authority flags, and no repository/scratch-root mutation.
The first 28 gates remain unchanged. Guarded delivery requires an exact 3G96
commit and CI blob, clean worktree, five-file scope, Ruff, strict Linux/Windows
mypy, focused pytest and the complete installed-wheel matrix before a
conditional commit and push. On failure, preserve the checkout as-is.

## Next gate

Use 3G98 to classify conflicting *two-root* evidence and native owner/ACL
custody at the boundary of explicit binding, without enabling a real write
until every relevant production prerequisite is qualified. No percentage of
preparatory tests is a substitute for live production admission criteria.
