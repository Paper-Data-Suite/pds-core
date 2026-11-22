# Core #241 — Slice C noninteractive roster-edit CLI contract

**Status:** Service, source CLI, and initial isolated wheel accepted on Windows.
The final capability-bearing wheel and #241 integrated/CI gates remain pending.
No release or producer adoption is implied.

## Commands

The new commands are added to the existing roster group, retaining the published
`import-preview` and `import-commit` spellings and behavior.

```text
pds-core [--workspace PATH] roster student-preview CLASS_ID --change-file FILE [--format text|json]
pds-core [--workspace PATH] roster student-commit CLASS_ID --change-file FILE --expected-current-state-token TOKEN --expected-candidate-state-token TOKEN --confirm [--format text|json]
```

The command always resolves the existing selected PDS workspace through Core.
An explicit `--workspace` does not change saved configuration. Student IDs and
student names are read from the JSON source, not shell arguments. A `--change-file
-` consumes redirected stdin without prompting and refuses TTY stdin.

### Change JSON

Exactly one UTF-8 or UTF-8-BOM JSON object, maximum **16,384 bytes**, maximum
**64 change fields**. Duplicate keys (including nested fields), JSON NaN/Infinity,
unknown top-level keys, non-string IDs/operations/fields, invalid version, and
invalid payloads fail without writes. Full input content is not echoed on errors.

```json
{
  "schema_version": "1",
  "operation": "update",
  "student_id": "0007",
  "fields": {"period": "3"}
}
```

`operation`: `add`, `update`, or `remove`.
For add, `fields` must include `first_name`, `last_name`, and `period`
and may include existing optional columns. For update, `fields` must be a
nonempty partial patch of the permitted existing roster columns. For remove,
`fields` may be omitted or an empty object. Neither `class_id` nor
`student_id` is editable inside `fields`.

### Preview and commit

Preview is read-only and emits both `current_state_token` and
`candidate_state_token`, a student-scoped before/after field summary,
`changed_fields`, previous/proposed counts, and `no_change`/ `saved=false`.
Text mode visibly labels the result **PREVIEW ONLY - NO WRITE**.

Commit requires the **same JSON input**, both tokens, and `--confirm`.
The service revalidates current/candidate state under the same canonical
roster lock as existing full import. A valid no-op returns a
`status=no_change` receipt and does not rewrite the file. There is no
automatic retry or implicit confirmation. No module-owned records are changed.

Successful JSON uses the existing version-1 Core CLI envelope:
`schema_version`, `command`, `workspace`, `ok`, and `data`.
Failures additionally contain `error: {code,message}` with a bounded
`roster_student.<reason>` code; stdout is empty for text-mode errors.
The request's source contents, full roster, and raw exceptions are not
included in error messages.

### Stable process exit status

| Exit | Meaning |
| --- | --- |
| `0` | Preview rendered, commit succeeded, or confirmed no-op |
| `2` | Bad JSON/fields/IDs, validation refusal, missing `--confirm` or tokens |
| `3` | Requested class/student enrollment not found |
| `4` | Current/candidate state stale or another writer holds the lock |
| `5` | Unsafe canonical path, unreadable/invalid storage state |
| `6` | Definite write/lock management failure |
| `7` | **Uncertain write outcome**: inspect canonical roster before retry |

Parser-level invalid or omitted arguments return 2 as in other Core commands.
These are local file guards, not distributed cloud-sync transactions.

## Qualification and staged capability

The core service and earlier B1/B2 tests qualified on maintainer Windows.
This **CLI Slice C** requires its own success evidence for JSON parsing,
bounds, stdin/TTY refusal, state token replay and mutation, text sanitization,
legacy import parity, CLI help, candidate-wheel import and statuses.

The final candidate advertises `classroom.roster_edits.v1` after source/CLI
and initial installed-wheel acceptance. Installed-wheel and integration
qualification must now confirm this specific capability-bearing commit.
`classroom.menu.v1` stays withheld until #242. No release before #244.
