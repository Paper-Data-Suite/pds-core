# Core #238 — Slice 3G15: Recovery-operation postcondition matrix

## Scope

This slice adds a **pure, internal, fail-closed postcondition classifier** for three future recovery operations. It is not a writer and receives no filesystem paths, OS identities, handles, locks or callbacks. It observes **caller-supplied** before/after byte images, not the machine's filesystem. Such images must be captured and qualified independently by a future native mutation coordinator.

The operations considered are stage-to-registry replacement, descriptor after-image completion, and journal retirement. All require a **canonical, non-initializing** transaction intent. Witness revisions and decoded registry revisions must match, with after revision exactly one greater than before revision. The requested revision must equal the revision appropriate to the operation's *starting* registry image.

## Exact transition matrix (journal, registry, descriptor, stage)

All byte identities are exact, not normalized or reparsed:

| Future operation | Required before | Described after | Advisory finding |
|---|---|---|---|
| Stage-to-registry | (journal intent, registry before, descriptor before, stage = registry after) | (same journal, registry after, descriptor before, no stage) | Exact transition **observed**, review still required |
| Descriptor completion | (journal intent, registry after, descriptor before, no stage) | (same journal, registry after, descriptor after, no stage) | Exact transition **observed**, review still required |
| Journal retirement | (journal intent, registry after, descriptor after, no stage) | (journal absent, registry after, descriptor after, no stage) | Journal absence **unqualified** — no durability claim |

A mismatched starting image is refused. A completely unchanged pair is `NO_PROGRESS_PRESERVE`; any other image mismatch is `POSTCONDITION_CONFLICT_PRESERVE`. Malformed or over-limit byte images, invalid operation kinds, noncanonical intents, and invalid or mismatched revisions are refused before making any positive observation. Keyboard interruption during classification returns a preserve-evidence state. The returned dataclass has a sanitized fixed message, without raw images, paths, identities, revisions, or write tokens.

## Security and qualification limits

1. **No native custody:** This classifier does not prove file identity, path protection, local backing, OS-user ownership, lock continuity, or CAS. Earlier read-only modules establish only advisory native observations; they are not a writer.
2. **No atomicity or durability:** Matching byte images are not a persisted directory-entry guarantee, atomic multi-file transaction, crash recovery protocol, or proof against same-user hostile modification. In particular `journal=None` does not prove durable journal retirement.
3. **No write authority:** No stage replacement, descriptor write, journal delete/replay, workspace association, or Notes service is implemented or advertised. Public capabilities remain `terminal.header.v1` and `terminal.notes_command.v1` only.
4. **Independent future gates:** A real operation must independently qualify the private root and OS owner, retain all native guards, recheck the expected revision, execute only an approved single operation, inspect postconditions inside the retained scope, verify native persistence and interruption states, and refuse unsafe filesystems. Passing this classifier alone cannot authorize any such step.
5. **No teacher data touched:** The slice contains only a new Python module, new tests, and this audit. The runner checks all inherited baseline blob pins and candidate scope, and conditionally commits only after target-platform qualification.

## Synthetic acceptance

The isolated 3G15 regression harness passed **107 tests** covering correct transitions, idempotence, wrong revisions, cross-phase inputs, changed journal/registry/descriptor/stage images, bounded input validation, invalid intents, simulated interruptions, frozen/sanitized results and absence of Notes/writer exports. These tests use synthetic codecs, not real teacher data. The repository's Ruff, strict mypy, native Windows and full focused Core #238 checks remain for Windows qualification. The full Core integration checkpoint was green in 3G13 (4,867 passed; 174 skipped) and need not run every slice.

## Next dependency

A future **guarded writer-owned operation** must integrate this postcondition contract with genuinely retained native handles, expected-revision CAS and qualified persistence. Until then, no mutation or journal-retirement path is authorized.
