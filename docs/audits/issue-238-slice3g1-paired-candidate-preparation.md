# Core #238 — Slice 3G1: paired candidate preparation, not commit

**Base:** qualified Slice 3G0 `bde16433f9c9bddab263df2b9b123a2967200e0b`.

## Scope and semantics

A strictly internal, opt-in orchestration function reuses the existing native
Linux/Windows **journal-creation** and **registry-stage creation** mutation
scopes and existing exclusive create-only primitives. It creates neither a
Notes record nor an owner binding, and modifies neither live registry nor
workspace descriptor. No new CLI, menu or public Notes capability is exposed.

### Finite checkpoints

| Point of interruption or refusal | Recoverable evidence | Caller outcome |
| --- | --- | --- |
| Before journal creation | No new candidate required | `JOURNAL_REVIEW_REQUIRED` for any attempted unqualified phase |
| Journal creation in progress, refused, or post-guard failed | Candidate **may** exist even when return says failure | `JOURNAL_REVIEW_REQUIRED`; no stage attempted; no automatic retry |
| Journal verified; stage not begun | Exact one pending journal may remain | Stage phase must review it independently |
| Stage creation in progress, refused, or post-guard failed | Journal and possibly stage remain | `STAGE_REVIEW_REQUIRED`; no rollback or automatic retry |
| Both guards and create primitives succeeded | Canonical candidate and stage observed | `PREPARED_REVIEW_REQUIRED`; **not** durable admission or commit |

The phases do **not** share one continuously held pair of locks: the journal
scope releases its ordered locks before the stage scope acquires them. The
second phase independently checks the exact journal bytes, registry/descriptor
before-images, OS owner and namespace. A same-owner non-cooperating process can
still interfere. If a crash occurs between phases, readers must classify the
pending journal and stage through the existing recovery review contracts;
no automatic re-entry, cleanup, or replay is allowed.

The operations provide **no cross-file atomicity**, no guaranteed stable
Windows directory-entry durability, no protected metadata CAS, and no authority
to replace `registry.json` or alter the association descriptor. POSIX file and
directory fsync ordering and Windows write-through are governed by the separate
native provisioners and need explicit end-to-end durability qualification.

Initialization continues to be refused pending its separate descriptor/registry
absence protocol. This change does not enable `notes.records.v1`,
`notes.menu.v1`, `notes.cli.v1` or any persistent Notes/Tasks workflow.

## Testing and evidence

Synthetic fault-injection tests pin phase order, platform dispatch, refusal
states, no second-phase execution after journal failure, preservation of files
on stage failure, no implicit retry/cleanup, and existing capability isolation.
All user-facing status strings are bounded and do not reveal private paths,
file contents, OS identifiers or transaction IDs.

Qualification requires focused pytest, Ruff, strict mypy, **full Core pytest**
and exact Git scope verification on the user's Windows Core checkout. A source
suite pass is not installed-wheel/native-platform/CI qualification. Security
review and native crash testing are required before enabling binding commit.
