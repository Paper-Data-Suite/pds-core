# Core #238 — Slice 3G33: In-scope protected write-intent verification

**Baseline:** `fbd055ec9e4c2317a5b553a17a3dcd6a7cd6801f` (qualified 3G32)
**Branch:** `238-establish-private-teacher-workspace-storage`
**Disposition:** read-only verification; **NO protected mutation or permission to mutate**.

## Contract and dependency boundary

The 3G32 `PrivatePreparedWriteDescription` is metadata, not a write permit. Its
hashes can be freely copied, replayed and forged. It carries no path, handle,
lock, callback, token or protected writer. The 3G33 review accepts **the canonical
transaction intent itself**, a bounded stage-to-registry step, expected revision,
and two existing native roots; it does **not** accept a caller-supplied
3G32 description or a previous 3G29/3G30 advisory result as authority.

The new private review function:

`review_protected_native_prepared_write_intent(step, expected_revision, proposed, existing_private_root, existing_workspace_root)`

1. Rejects invalid exact operation, revision, intent type, unsupported platform
   and unsafe root requests *before* native guard acquisition.
2. Creates a **non-authorizing** candidate description via 3G32's pure API;
   invalid, noncanonical, initialization or stale revisions refuse early.
3. Acquires a **single** existing native descriptor/journal/registry guard, via
   the same retained protection primitive used by 3G29/3G30. No nested guard
   acquisition, writer entry, caller callback or operation slot exists.
4. Reconstructs the description and canonical intent **again inside** custody,
   rejecting a changed description, exact byte type or serialized SHA-256.
5. Observes three consecutive native frames using 3G30's `_observe` and
   `_frame_state`: exact pending journal, registry preimage, descriptor before,
   staged registry after, recovered checkpoint, all four native file stamps,
   four parent stamps, unchanged effective owner and stage/journal namespace.
6. Additionally compares **live native image hashes** to the re-derived 3G32
   fields for pending intent, registry before, staged registry after, descriptor
   before; the descriptor after fingerprint is checked against the canonical
   candidate but is **not** misrepresented as an on-disk after-image.
7. Rechecks final namespace, effective owner and parent continuity before
   leaving the same guard. Only after successful guard release can it emit the
   positive **advisory** `PROTECTED_INTENT_REVIEW_ONLY` state. A guard-release
   error overrides apparent success.

The returned result contains **only** a bounded state and sanitized fixed
message. It is immutable and deliberately excludes native identity data, exact
bytes, private paths, owner information, transaction identifiers, handles,
guards, executable callbacks, admission tokens and writer permits.

## Threats and refusal behavior

| Unqualified condition | Refusal family |
| --- | --- |
| Invalid step, revision, supplied paths or intent | Invalid / operation refusal |
| First binding, mismatch, noncanonical intent | Initialization / revision / canonical refusal |
| Re-derived description differs, serialization changes | Intent drift — preserve |
| Prepared checkpoint or native image differs | Checkpoint / image conflict — preserve |
| Parent or file stamp diverges during continuous guard | Parent / file conflict — preserve |
| Journal/stage namespace or OS owner changes | Namespace conflict / owner changed |
| Guard acquisition/release refused, unsupported OS | Guard refusal / unsupported |
| Interruptions and other native read failures | Interrupted preserve / IO error |

**Boundaries not crossed in 3G33:** no protected writer, production registry
replacement, descriptor completion, transaction journal retirement, fsync/flush,
proof of crash durability, Notes record CRUD, menu or CLI activation. One
process-local guard and three observations do not establish exclusion of every
same-user adversarial process or persistence after power loss. The positive
result is stale immediately upon release and **must never be consumed as
execution authorization**. A future protected writer must independently
revalidate the entire canonical intent, OS owner, ACLs, native parent/file
identities, protected namespace, stage and journal *inside its own continuously
held protected mutation guard* and separately qualify postimage/durability.

## Qualification and synthetic test data

All tests use synthetic transaction IDs and bytes, never teacher/student data.
The isolated 3G33 mock-native regression suite tests one guard, three frames,
re-derivation, changed candidate, raw-intent drift, four image alterations,
owner/namespace conflicts, guard release refusal, interruptions, request type
refusals and sanitization. Isolated stubbed tests are **not** native Windows
qualification. The guarded Windows runner validates exact HEAD, origin and
remote state, all inherited Git blob pins, clean candidate scope, SHA-256
archive/manifest integrity and AST-preserving Ruff formatting before adding
exactly three new files. It then runs dedicated tests, the focused Core #238
suite, Ruff, strict mypy, and conditional commit/push.

The full Core regression checkpoint remains deferred after the successful 3G30
run (6,191 passed, 176 skipped). A future full checkpoint is still required
before the issue can be closed; native release, durability, ownership and
backup/restore qualification remain separate acceptance gates.
