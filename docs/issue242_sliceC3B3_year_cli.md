# Core #242 — C3B3 noninteractive school-year CLI parity

**Status:** Source candidate on `242-workspace-classroom-management-menu`;
exact-SHA Windows qualification pending. The actual issue #242 description
specified the command contract **before implementation**. The public shared
teacher menu is still unavailable, and `classroom.menu.v1` is unadvertised.

## Commands

The commands manage the **canonical school-year record in the selected Core
workspace**, not the user's saved workspace preference. The optional global
`--workspace ROOT` uses normal explicit/environment/saved/default precedence.

```text
pds-core [--workspace ROOT] workspace year-preview open 2026-2027 \
  --effective-at 2026-09-01T08:00:00+00:00 --format json

pds-core [--workspace ROOT] workspace year-preview close \
  --effective-at 2027-06-30T18:00:00+00:00 --format json

pds-core [--workspace ROOT] workspace year-commit open 2026-2027 \
  --effective-at 2026-09-01T08:00:00+00:00 \
  --expected-current-state-token TOKEN \
  --expected-candidate-state-token TOKEN --confirm --format json

pds-core [--workspace ROOT] workspace year-commit close \
  --effective-at 2027-06-30T18:00:00+00:00 \
  --expected-current-state-token TOKEN \
  --expected-candidate-state-token TOKEN --confirm --format json
```

Both actions require an explicit ISO 8601 timestamp including a UTC offset.
The exact timestamp, canonical workspace, current state and operation are
bound to the candidate digest. Changing the year, timestamp, workspace or
underlying state invalidates the reviewed candidate. The CLI never prompts,
implicitly confirms, retries uncertain writes or bypasses canonical guards.

The CLI handler directly invokes qualified C3B2
`plan_guarded_school_year_change` /
`commit_guarded_school_year_change`. It adds no new school-year writer.
Only the two new commands bypass generic workspace/library bootstrap so
they can **resolve the selected workspace themselves** and emit one safe
structured error even if the saved workspace selection is invalid. All
previous workspace/Standards/Notes commands retain their normal dispatch.

## Output and exit contract

`--format json` produces a single JSON object on stdout with
`schema_version: "1"`, `command`, `scope: "school_year"`, `ok` and
`data`. Errors contain an empty `data` object and a stable,
path-free `error.code` / `error.message`. Text mode prints a readable,
escaped workspace path and reviewed state, both explicit tokens and
`PREVIEW ONLY - NO WRITE`, or a confirmed transition receipt. A confirmed
`committed` result includes `changed_scopes: ["SCHOOL_YEAR"]`;
`no_change` returns an empty `changed_scopes` list.

| Result | Exit |
| --- | ---: |
| Successful preview, committed action, no-change | 0 |
| Bad input token, missing confirmation or unsupported timestamp | 2 |
| Changed state, different proposal, local lock or year-history conflict | 4 |
| Invalid or unreadable workspace/canonical school-year record | 5 |
| Known lock/write refusal | 6 |
| Write outcome uncertain; inspect record before retry | 7 |

Argument-parser errors (e.g., missing `--effective-at` or a naive timestamp)
return the usual CLI parsing status 2 and do not write. For valid parsed
commands, the handler maps bounded service errors to the structured
status and never prints raw exception details or path information in
JSON error messages.

## Safety and explicit nonclaims

Canonical C3B2 enforces only initial-year opening, same-active-year no-op
and active-year close. A different already-active year, closed-year
replacement or initial-year adoption of preexisting class directories is
**refused**. The local writer lock coordinates participating new writers;
legacy commands and cloud sync do **not** provide distributed CAS.

Confirmed close does not remove class folders, rosters or producer-owned
records. Preview, stale refusal and missing `--confirm` never write.
A post-write failure is `write_outcome_uncertain`: do not retry blindly.

## Synthetic qualification

`tests/test_issue242_school_year_cli.py` uses synthetic workspace
directories and a patched user-preference/default location; no teacher
data. Seventeen scenarios exercise first-year preview and commit, stale
replay, no-op, close preserving producer files, confirmation requirement,
candidate year/timestamp changes, invalid tokens, stale state, closed-year
record protection, lock ownership, uncertain write **after replacement**,
malformed canonical record, invalid workspace, no prompting, parsing
rejections, and legacy `workspace show` compatibility.

Qualify at an exact SHA using the new CLI tests, C3B2/C3B1 school-year
service tests and existing workspace CLI tests, Ruff format/lint and strict
mypy for **changed Python files**, and a clean synchronized Git checkout.
Do not run full-repo tests for this single stage.

**Next:** C3B4 will compose qualified year service + CLI into the **private
test-gated** teacher menu, with one readable teacher confirmation,
`SCHOOL_YEAR` durable-scope receipts and unconditional caller revalidation.
Class creation and partial-write recovery are separate work. No merge,
release or public capability until full #242 and consolidated #244 gates.
