# Core #238 — Slice 3G98: synthetic two-root binding evidence and owner-mode holds

## Baseline and narrowly bounded scope

This slice follows accepted 3G97 `ac4b7c73c3d43670d61d00e993717ebce6096ad9`
(197 passing focused tests, 29 native installed-wheel gates, 15/15 GitHub CI).
The next product prerequisite is a consistent *workspace association descriptor*
and *local private binding registry*, separated from OS-owner authority. The
slice exercises **only** internally created, disposable two-root fixtures.
Its public probe accepts exactly one fixed scenario enum. It accepts no real
workspace path, private-root path, identity, association ID, credential,
payload, native handle, callback, or teacher data.

Two fresh subdirectories are created in one random temporary sandbox:
`workspace` (synthetic association sidecar only) and `private` (synthetic
binding-registry image and existing-file coordination lock only). The sides
carry a fixed synthetic association ID, a deliberately fake owner marker and
a versioned schema. **The fake owner marker is not a process-token SID,
effective UID, authentication claim or usable production owner identity.**
The fixture does not touch Core's `.pds/workspace.json` marker.

Files are created exclusively with POSIX owner-only 0600 at creation (never a
permissive-then-chmod window); directories request mode 0700. Linux checks
fresh filesystem UID, 0700/0600 modes, hard-link count, symlink exclusion,
file descriptors, and stable native parent identity. Windows retains the two
parent handles through Core's native helper and rejects basic reparse points,
but explicitly does **not** qualify current-token SID or effective DACLs.
POSIX ACLs that defeat modes are also not covered by this experiment.
The Core cooperating lock is held during the two-root read-only comparison.

## Seven deterministic scenarios

| Case | Required state and effect |
| --- | --- |
| Consistent descriptor and registry | `consistent_but_unqualified_hold`; no binding authority |
| Different association in private registry | `association_conflict_hold` |
| Conflicting *synthetic* owner marker | `synthetic_owner_marker_conflict_hold`; not an OS identity check |
| Copy with same descriptor ID at second workspace root | `duplicate_association_hold`; no implicit collection aliasing |
| Unsupported descriptor schema | `malformed_metadata_hold` |
| Extra untrusted registry metadata | `malformed_metadata_hold` |
| Private root is changed to mode 0755 | Linux: `posix_protection_refused`; Windows: `windows_dacl_unqualified` without asserting Unix modes |

The coherent case demonstrates only that two exact images agree while both
native parent handles remain retained during the read. It is **not** an
explicit first-time binding or proof of OS ownership. Registry or descriptor
conflict does not trigger reset-to-empty, rewriting, merging, migration,
recovery, or automatic choice of the original vs copy. Unsupported platforms
and malformed enum inputs fail before creating scratch. Taxonomy drift also
refuses before creating scratch.

## Explicitly unqualified requirements

- Effective Windows token SID and effective private DACL on production roots;
  real owner authentication and POSIX ACL qualification.
- The actual workspace's safe canonical root, untrusted path hints, presence of
  an existing private binding, descriptor opt-in creation, and root location.
- Concurrent real binding, moved/copied/restored workspace decisions, fork-copy
  transaction, or a durable two-root commit.
- Non-cooperating same-owner writer exclusion, atomic content-CAS, native
  handle-relative two-root replacement, directory crash durability and Notes.
- Production mutation, automatic replay/retry, journal retirement, or Notes
  records/menu activation. All **nine** production-operation blockers remain.

## Qualification and next engineering gate

Fifteen focused source cases cover seven fixtures, five malformed enum inputs,
requirement drift, unsupported-platform refusal, and the public capability
boundary. The **30th** isolated installed-wheel gate repeats all seven
scenarios, checks installed wheel provenance, the unchanged repository scratch
root, positive native-handle observations without authority, effective ACL
nonclaims, and strict sanitized reports. The 29 predecessor gates remain
unchanged. Qualification requires Ruff, strict dual-platform mypy, focused
pytest, exact commit/workflow/worktree preflight and conditional exact-scope
commit/push; failures leave files untouched and never reset/stash a checkout.

3G99 should begin explicit real-root **read-only** owner/ACL admission
inventory, with separate verified Windows token/DACL and Linux effective ACL
conditions. Never promote a synthetic descriptor/registry coherence test into
permission to bind. The terminal capabilities remain only
`terminal.header.v1` and `terminal.notes_command.v1`.


## Slice 3G98 Repair 1 — Windows-target mypy enum narrowing

The initial Windows qualification passed 212 focused tests (12 skipped),
Ruff check and Ruff format, and strict Linux mypy across 536 files. The
Windows-target strict mypy pass stopped on a comparison-overlap diagnostic:
with the early Windows-only refusal, the analyzer inferred that a later
`POSIX_PRIVATE_ROOT_MODE_DRIFT` branch could not be reached.

The repair extracts that original, pre-scratch Windows refusal condition
into a typed predicate. The predicate checks the same exact enum and platform,
and still returns `WINDOWS_DACL_UNQUALIFIED` before creating scratch files.
On Linux the same POSIX mode-drift branch remains reachable, detects unsafe
mode and returns `POSIX_PROTECTION_REFUSED`. The change is confined to
the implementation, plus this append-only audit addendum. Tests, installed
wheel verifier, CI insertion, and all 30 installed-wheel gates remain intact.

The guarded repair authenticates the exact accepted 3G97 commit and the
five-file interrupted 3G98 worktree (including AST/comments and CI bytes),
then executes the original qualification and conditional commit/push.
No automatic retry or production write capability is enabled; all nine
production-operation blockers remain open.
