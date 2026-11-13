# Core #238 — Slice 3G55: Canonical descriptor-after-stage custody

## Scope and immutable starting point

- Feature branch: `238-establish-private-teacher-workspace-storage`.
- Qualified starting commit: `072446430aeb72e97865b578ceb2c8243f3fb769` (3G54).
- Verified remote `main`: `a0d5e1a50580bbe025f0cad23c7e8524203a52ec`.
- Adds **one private module, one regression suite and this audit**. No public API, capability, live record service, startup side effect or production write.
- The protected 3G54 handoff validates the canonical `FORK_COPY` intent, the pending journal, the registry before-image and its stage, but does not independently retain and verify a separately prepared **workspace-descriptor after-stage**.

## Contract introduced

`review_prepared_canonical_descriptor_stage(step, revision, intent, private_root, workspace_root)` is an **internal observation**, not admission. Before crossing into existing native locks it requires:

1. A real `STAGE_TO_REGISTRY` step and exact canonical `FORK_COPY` intent, with distinct before/after registry and descriptor bytes.
2. The exact expected registry revision and existing qualified root shapes.
3. The production write barrier to remain `PRODUCTION_BLOCKED` with its complete nine-requirement taxonomy.
4. Current effective OS owner and canonical workspace binding to agree with the intent.

Inside the existing transitionable journal/descriptor scope, with both ordered locks and the original descriptor and pending journal retained by Core, the implementation:

- requires an already prepared registry-stage native checkpoint (read-only `_classify_present`),
- derives a **fixed** descriptor-stage name from the canonical transaction UUID: `.<transaction-id>.descriptor-stage` under the verified workspace `.pds` directory,
- reads only that stage, never a caller-supplied path, and requires its bytes to equal the canonical `descriptor_after`,
- performs two independent native reads with equal file identities and bytes, rechecks owner/current checkpoint, and checks the write barrier again before release,
- returns only a bounded sanitized state; **no native handles, bytes, paths or authorization escape**.

Native Linux reads use an absolute-root, `O_NOFOLLOW | O_DIRECTORY` dirfd walk, no-follow stage open, regular-file/single-link and strict size checks, and retained-vs-named identity/content/parent comparisons. Native Windows reads use `FILE_FLAG_OPEN_REPARSE_POINT`, a stable `FileIdInfo`-backed file signature, exact handle-based `ReadFile`, a second independently opened handle, and the existing safe workspace-ancestry check.

The stage is **not created by this slice**, and a missing or unsafe stage is a refusal rather than a request to create/recreate it. This is a new prerequisite, not a claim that all existing prepared transactions already contain it.

## Refusals and recovery semantics

- Bad request, unsupported OS, noncanonical or non-fork intent, revision mismatch, unsafe roots and changed effective owner fail closed.
- Missing descriptor-stage evidence, nonregular/reparse/symlink/link-count conflicts, changed file identity, truncated bytes, unexpected journal or registry checkpoint, stage-content conflict, native guard failure and interruption return distinct hold/refusal outcomes.
- Every state, **including** `stage_present_barrier_blocked`, retains the journal and pending recovery artifacts, prohibits automatic retry and retirement, and reports production writes and durability as blocked/unqualified.
- Native observations are not multi-file atomicity or evidence of directory-entry persistence. A successful read expires on guard release and cannot be carried into a later mutation as a token.
- Existing Core metadata, generic `.pds/workspace.json`, Suite/producer integration, Notes CRUD/capabilities and installed release boundaries are unchanged.

## Tests and qualification gates

- Isolated dependency-stub suite: 39 passing tests (not native Core qualification).
- Native Windows must rerun the real 3G55 regression suite and a no-write, fail-closed smoke check.
- Qualified runner pins the entire inherited 268-file Git blob set, baseline and two remote refs, validates additive source hashes, checks off-checkout Ruff formatting without AST change, and runs the 107-file focused #238 suite, Ruff lint/format and strict mypy before commit/push.
- Full repository checkpoint last recorded at 3G40: 6,864 passed, 179 skipped. This slice intentionally defers a new full checkpoint; D2 installed wheel, Windows/Linux matrix, actual persistence qualification and macOS remain separate acceptance gates.

## Next operation-owned boundary

The future writer must prepare and verify **both** staged after-images while retaining journal/descriptor/registry native custody and locks throughout mutation; it must establish postimages, recovery behavior and a supportable crash-durability policy before marking the transaction durable or retiring its journal. The stage reader here cannot grant that write authority. A synthetic scratch-only demonstration cannot substitute for an OS-owner-qualified production recovery protocol.
