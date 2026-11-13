# Core #238 — Slice 3G2: Exclusive prepared-pair checkpoint

## Purpose

The read-only Slice 3F5 retained checkpoint validates journal, stage, and two metadata image pairs but intentionally does **not** prove the transaction directory has only the intended journal or that the stage namespace contains only the expected stage. This slice adds an **internal, non-authorizing, read-only census** inside one retained descriptor guard, before and after symmetric native byte inspection. It reuses the existing 3F5 native readers and 3E3 exact-image checkpoint classifier instead of creating another independent file parser.

## Conditions and refusals

- Canonical non-initialize intent, validated rooted paths, and a supported Windows/Linux OS branch.
- Retain ordered coordination plus journal-directory, registry-file and workspace-descriptor native guards while observing names and bytes.
- Require precisely the expected `<transaction_id>.json` in the transaction directory and exactly one stage-like entry in the private root, `.<transaction_id>.registry-stage`. Additional non-stage ordinary root entries are allowed, but any root namespace change between the two observations is refused.
- Use the existing strict stage inventory to reject malformed or unqualified stage entries, native image readers to verify the journal, registry, descriptor and stage twice, byte equality with proposed intent and after-image, and the crash-checkpoint classifier for live metadata.
- An already partially applied or after-state checkpoint remains **review required**; no implicit rollback or overwrite. All failures preserve files.
- No file creation, deletion, migration, binding, metadata CAS, journal retirement, replay, protected write handle, task or Notes records.

## Limitations

A matched pair is an observation and not proof of durable directory entry ordering or local atomic commit. OS-visible directory enumeration cannot exclude hostile same-OS-user or asynchronous cloud writers. The previous reader and all immutable guards retain their previous API and refusal semantics. Tests use synthetic identifiers and contents only. Native Windows and Linux integration plus installed wheel checks remain required by #238 D2.

## Next boundaries

Prove platform-specific durable write/checkpoint semantics and protected exact-before registry/descriptor transition, then define explicit replay/retirement and first-binding absence handling before exposing any public storage or Notes capability. Usability remains separately accepted under Core #239/#240.
