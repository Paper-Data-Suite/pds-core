# Core #242 — C2B noninteractive workspace preference CLI

**Status:** Implementation candidate on the dedicated #242 feature branch,
pending exact-commit Windows qualification. The actual GitHub issue body was
updated with this command contract **before** implementation. No shared-menu
mutation, capability advertisement, branch merge or official release.

## Command contract

The new routes operate **only on the saved per-user workspace preference**,
not a caller's currently selected workspace data root:

```text
pds-core workspace preference-preview set PATH [--format text|json]
pds-core workspace preference-preview reset [--format text|json]

pds-core workspace preference-commit set PATH \
  --expected-current-state-token TOKEN \
  --expected-candidate-state-token TOKEN --confirm [--format text|json]

pds-core workspace preference-commit reset \
  --expected-current-state-token TOKEN \
  --expected-candidate-state-token TOKEN --confirm [--format text|json]
```

The teacher-facing shared menu must retain both tokens **internally**, not
ask teachers to copy them. CLI scripts are different: tokens are explicit
so scripts can prove they are committing exactly the reviewed proposal.
No CLI operation prompts or silently supplies `--confirm`.

`--workspace` is **not accepted** with these routes. The global CLI
bootstrap dispatches only these specific commands before resolving the
saved workspace. That ensures a corrupt or missing preference returns a
bounded, structured error and cannot trigger unrelated workspace-library
loads. The existing `workspace show/set/reset/validate/paths`, Core menu,
Notes and all other CLI commands keep their previous bootstrap behavior.

## Output and exit contract

`--format json` provides one JSON object on stdout with
`schema_version: "1"`, `command`, `scope: "user_workspace_preference"`,
`ok` and `data`. A refused operation has `ok: false`, empty `data`
and a stable `error.code`/`error.message`, with no raw exception text.
Text mode writes a readable proposed before/after, config resolution,
environment precedence, initialization implication, and both review tokens.
It explicitly says **PREVIEW ONLY - NO WRITE**. Commit output identifies
`committed` or `no_change` and reminds the caller to reload its context.

| Status | CLI exit code |
| --- | ---: |
| Successful preview or committed/no-change result | 0 |
| Invalid request, missing confirmation or malformed token | 2 |
| Stale saved config, different candidate or active local writer | 4 |
| Invalid/corrupt/unreadable canonical configuration | 5 |
| Local write/lock failure with known refusal | 6 |
| Uncertain write outcome; inspect canonical state before retry | 7 |

The CLI forwards C2A's **separate current and candidate** tokens and
`confirmed=True` exclusively when `--confirm` is present. It does
not reimplement the workspace writer, duplicate token validation,
or force a retry after an ambiguous write. A re-run after successful
commit with old tokens is refused as stale, not silently replayed.

## Safety and compatibility

The new handlers call `pds_core.classroom_workspace_commit` and cannot
provide a distributed compare-and-swap guarantee. The local lock only
coordinates new C2A/C2B writers: the legacy CLI, independent processes
and synchronized provider conflict copies do not necessarily participate.

An approved set operation may initialize a missing selected workspace
and create its canonical marker/settings folders. A reset only removes
the saved user preference, never historical class rosters or producer
work. Preview and declined confirmation never create a workspace,
preference, marker or lock. Malformed canonical config and unsafe
paths are refused before a new write.

## Acceptance

`tests/test_issue242_workspace_preference_cli.py` uses synthetic paths
and private config monkeypatching to cover read-only preview, committed
set/reset, stale replay and different candidate, explicit `--confirm`,
invalid token and `--workspace` refusal, malformed config structured
error independent of CLI bootstrap, missing-target initialization,
environment override, write uncertainty and preservation of historical
files, text/JSON rendering, no prompting, missing required flags,
and legacy set/reset compatibility.

Run focused C2B/C2A/C1/workspace CLI tests, Ruff format/lint and strict
mypy for changed files, then verify clean Git state and exact SHA.
This is **not** full Core regression, installed-wheel acceptance or
permission to advertise `classroom.menu.v1`.

## Next

Compose only the qualified service+CLI into the staged read-only controller
with an explicit before/after and **one** meaningful teacher confirmation.
Properly account for `WORKSPACE` durability/change scopes in shared
return receipts; revalidate all caller state on any menu return.
Other school-year/class/Standards workflows remain governed by issue #242.
Consolidated official release remains #244.
