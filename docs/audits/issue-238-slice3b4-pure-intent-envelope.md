# Core #238 — Slice 3B4: strict, non-mutating transaction-intent envelope

**Pinned source baseline:** Core `174f57d007423dbd10d155cef7f89a4e8ab73a74` (Slice 3B3).
**Authority:** `docs/teacher_private_storage_contract_v1.md` §5 and `docs/security/teacher-private-storage-threat-model.md`.
**Status:** Implementation and qualification candidate; **not** formal D0 approval, durable journaling, native security qualification, a working Notes service or a release.

## Bounded implementation

`pds_core._teacher_private_transaction_intent` is an internal, import-side-effect-free codec for a **proposed** private transaction-intent journal. It combines the previously qualified `PrivateTransactionWitness` with exact proposed **before/after bytes** for both documents:

- the separate non-secret workspace descriptor (`descriptor_before`, optional; `descriptor_after`);
- the OS-user-private registry (`registry_before`, optional; `registry_after`).

The canonical UTF-8 JSON envelope uses schema `pds.teacher-private-transaction-intent` and integer version `1`, exact keys, canonical RFC 4648 base64 encoding, bounded payload sizes and validated SHA-256 digests. The maximum envelope size is conservatively bounded; embedded descriptor and registry bytes also retain their original strict 4 KiB and 512 KiB limits respectively. Metadata is validated by the existing v1 descriptor/registry codecs **after** digest verification. The codec refuses duplicate keys, unknown schemas, unknown versions, malformed JSON/base64, changed owner identifiers across a transition, unrelated registry binding changes, invalid revisions or UUID transitions, and attempts to alias two associations to the same accepted path.

For the three supported operations, the proposed transition policy is:

| Operation | Required changes | Forbidden changes |
| --- | --- | --- |
| `INITIALIZE` | Add one fresh association with first binding revision, preserve prior registry bindings; preexisting registry may be absent or present | Adopt/replace another association, reuse another association's accepted location, invent an old descriptor |
| `REBIND_MOVE` | Preserve association UUID; increment its binding revision; update its accepted location; increment registry revision | Allocate a new association, alter unrelated bindings, treat unchanged descriptor bytes as a failed write |
| `FORK_COPY` | Preserve old association/binding; add exactly one fresh association with a distinct accepted location | Copy another collection into the new binding, mutate the original binding, reuse the original accepted location |

**Important security distinction:** This envelope can include the **private** registry's local accepted-root path and OS principal identifier, so its **future file must live only inside the qualified OS-user-protected private location**. Never place it beside `.pds/teacher-private-association.json`, in the synced workspace, in public diagnostics, or in GitHub artifacts. The typed model suppresses all content in its `repr`; validation errors have bounded fixed text. Tests use synthetic paths, principals and UUIDs only. Encoding/decoding is **not authentication**: a malicious actor can manufacture internally consistent hashes and a well-formed envelope.

## What this does not do

There are **no filesystem operations** in this module. It cannot read actual current sidecar or registry bytes, prove a file owner, check ACLs, create directories, acquire locks, persist an intent, replay an interrupted write, mark a binding `READY`, import Notes, or automatically reconcile an ambiguous copy or move. The existing pure classifier from Slice 3B3 remains only an observation, even when both hashes match. A future writer must verify current OS principal, effective protections, file handles, workspace identity, expected revisions, pending transaction state, cross-process locks, and explicit teacher decision **before** persisting anything, then implement recoverable write ordering and journal fsync. A future reader must not treat a valid journal as owner authorization.

No imports or changes to `pds_core.workspace`, Quillan/Concord/other producers, roster handling or CLI are introduced. `get_teacher_experience_capabilities()` remains exactly `terminal.header.v1` and `terminal.notes_command.v1`. No new release or consumer support is claimed.

## Evidence and gating

- `tests/test_teacher_private_transaction_intent.py`: synthetic all-operation canonical round-trips; registry-owner continuity; unchanged unrelated bindings; digest validation even against forged matching digests; duplicate/future schema and invalid/oversized metadata; privacy/non-leakage; import-time no-write and negative Notes capability tests.
- The guarded local runner must verify the exact issue branch, pinned baseline SHA, remote state, allowed three-file scope, source hashes, source AST after Ruff formatting, focused and full pytest, Ruff, strict mypy and staged whitespace before commit/push.
- This source-only D1 candidate is **not D2 installed native filesystem qualification** and **not D0 approval for private writes**. Mac/Linux/Windows protection/locking and filesystem-locality gates remain open. The next security-sensitive work is OS-native locks, protected directories and journal atomicity, subject to explicit design/security authorization.

Ordinary whole-workspace backup still excludes eventual private Notes content; export/import/restore remains #243. Actual Notes records and menus remain #239/#240, respectively.
