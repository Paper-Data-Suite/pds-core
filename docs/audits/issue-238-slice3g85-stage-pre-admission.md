# Core #238 — Slice 3G85: stage-to-registry pre-admission remains blocked

## Scope

This slice does not create or update any production file. It adds a read-only
stage-to-registry pre-admission **inventory**, scoped to the current private
OS-local root, one existing workspace path and the current on-disk pending
transaction UUID. The caller supplies only a lookup hint and an expected
registry revision, **not** a credential, accepted journal, image or write permit.

The 3G83 existing ordered registry/workspace locks and retained descriptor
native guard are held throughout the 3G85 read-only review. The 3G80 private
root native custody is rechecked inside the held scope. The exact journal,
registry, descriptor and staged registry images are reread twice through 3G84
native handles; the journal is canonically decoded on each round and its owner,
accepted workspace binding and images classified by the 3G84 pure classifier.
The expected pre-operation revision must match the canonical journal witness
in both rounds. Directory stage inventory, namespace, root and process token
owner are rechecked before release. Nothing is committed or retired.

## Narrow decisions

Only a prepared stage-to-registry checkpoint can return
`prepared_review_blocked` (still explicitly non-authorizing). A missing stage,
conflicting namespace, changed image, mismatched revision, invalid journal,
changed native owner, failed retained guard or unsupported filesystem refuses
and preserves current artifacts. The review returns only a frozen sanitized
enum and nine unchanged production blockers, never a path, owner, journal,
byte image, native handle, lock or writer entrypoint.

A cooperating local lock **does not** establish a production exclusive guard
against uncooperative same-user writers, cloud synchronization, alternate
replacements, or a fresh writer invocation after this guard has released. No
power-failure durability, multi-document atomicity, replays, journal retirement,
first binding, or Notes capability can be inferred from a successful review.

## Qualification

- New tests cover exact two-round observation, revision mismatch, absent stage,
  image drift, canonical refusal, owner mismatch, lock refusal, invalid input
  and no-mutation static contracts.
- A separate isolated installed-wheel gate checks fail-closed invalid requests,
  nine blockers, source-versus-wheel provenance and zero production authority.
- CI extends the sixteen prior native installed-wheel gates with a seventeenth
  independent gate, with sanitized uploaded evidence.
- Production-write admission remains blocked by `_teacher_private_recovery_production_write_barrier`.

## Remaining work

All nine requirements remain unqualified as **production operation guarantees**.
The next slice should develop a separately qualified production writer-owned
exclusive guard, native parent custody and irreversible operation protocol,
not reclassify a released read-only observation as admission.


## Slice 3G85 Repair 1 — strict test typing, no production change

The first Windows local qualification passed 206 focused tests, Ruff check/format, then stopped at four strict Linux mypy diagnostics in the *test file*. The invalid-revision test supplied `bad: object` to a parameter annotated `int` and placed the `# type: ignore[arg-type]` on a different line after Ruff formatting. Repair 1 uses `typing.cast(int, bad)` solely to communicate the expected static type; at runtime the original invalid object still reaches the rejection path. The preimage-drift test captures and checks optional registry/descriptor bytes *inside* its callback before constructing the deliberately inconsistent second image, so mypy can establish its exact bytes return type. Runtime refusal assertions and the induced drift remain unchanged.

The production module, installed verifier, workflow, API, native lock/ACL/ownership/canonical barriers and sixteen predecessor installed-wheel gates are unchanged. The original seventeenth installed-wheel gate is still mandatory. All nine production qualification requirements remain open: no production mutation, binding, automatic replay, journal retirement or Notes activation.
