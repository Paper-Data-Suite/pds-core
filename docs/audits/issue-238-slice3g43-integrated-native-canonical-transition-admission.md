# Core #238 — Slice 3G43: integrated canonical/native prepared transition review

**Baseline:** `6ccbb65d3abbe670910cdd5dec26edf5c54195f9` (qualified 3G42)
**Main:** `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`
**Scope:** Three additive files; no Core public API, Notes records, record CRUD, producer changes, or write barrier changes.

## Integration achieved

Core owns a single existing journal/descriptor lock scope (`3G41`) and retains the old-registry and prepared-stage native handles (`3G42`) for all observations. In that continuously held scope, a private observational entrypoint checks:

1. Stage-to-registry operation and exact canonical private transaction intent; registry revision and current production **BLOCKED** state.
2. Native process-token/UID owner, effective protection and owner/workspace binding before entry and at every frame.
3. Exact pending-journal namespace and stage inventory for the prepared transaction; no extra stage or foreign journal may be accepted.
4. Native parent, original-registry, and stage identities at four frame boundaries and immediately before return (nine native ID checks in total).
5. Four canonical byte-image frames: journal intent, registry before-image, workspace descriptor before-image, and staged registry after-image, with native file/parent identities and prepared checkpoint.
6. Description fingerprint consistency inside the guard and a final parent-continuity check.
7. Guard and pair release failures: fail closed even after otherwise successful observations.

All returned results are frozen, pathless, non-authorizing, and preserve pending recovery evidence. The entrypoint exposes no writer, callback, native handle, raw private path or release-spanning admission token. It calls no `os.replace`, `unlink`, or file writer. It does not use the immutable registry guard which would falsely reject an expected registry replacement. A positive result is *not* transferable outside the guard.

## Security and outstanding gates

This slice does **not** perform a production replacement or authorize any production file mutation. The production write barrier from 3G35 remains unchanged and blocking. Existing guard identity observations cannot defeat hostile same-user races or coordinate distributed/cloud filesystems. No claim is made about durable directory persistence, journal retirement, recovery replay, or Notes readiness.

Remaining work before enabling mutation includes a guarded **in-scope** native replacement attempt, refusal/ambiguous-outcome classification, exact old/new postimages, directory flush/durability and restart protocol, descriptor coordination, crash/recovery convergence, journal retirement, installed-wheel native proof and CI. The successful 3G40 native scratch rehearsal is not production authority.

## Qualification

Synthetic isolated 3G43 tests exercise four frames, nine native checks, refusal at each native check, byte-image drift, malformed revisions/steps, wrong owner/binding/namespace, guard/pair release failures, and negative capability/source boundaries. Windows runner additionally executes the full focused #238 suite, Ruff, and strict mypy on the actual checkout. The latest full Core checkpoint from 3G40 was **6,864 passed, 179 skipped**; avoid repeating it every minor slice. Native Windows test and CI results must be supplied by the runner; do not infer them from isolated fixture runs.
