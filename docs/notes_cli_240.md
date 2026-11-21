# Core #240-C — Noninteractive Notes CLI contract

**Status:** Source-level Slice C; not a released Core capability. Source changes
are not evidence of an installed candidate, producer adoption, Suite integration,
or real work/home OneDrive qualification.

All routes operate on the existing selected PDS workspace through the Core #239
record services. The global `--workspace PATH` argument overrides workspace
selection for **this invocation only**. Reads never create `.pds/notes/v1/`.

## Commands

| After `pds-core [--workspace PATH]` | Meaning |
|---|---|
| `notes create --category task --text-file FILE` | Save Idea/Task/Reflection; FILE may be `-` for piped stdin |
| `notes list` | Browse non-archived Notes |
| `notes search QUERY` | Case-insensitive substring search |
| `notes show NOTE_ID` | Read text, state, and revision |
| `notes edit NOTE_ID --expected-revision REV --text-file FILE` | Replace text only |
| `notes complete NOTE_ID --expected-revision REV` | Complete a Task |
| `notes reopen NOTE_ID --expected-revision REV` | Reopen a Task |
| `notes archive NOTE_ID --expected-revision REV` | Archive without deletion |
| `notes unarchive NOTE_ID --expected-revision REV` | Restore archived record |

`create` accepts optional `--module-id`, `--class-id`, `--work-id` (validated
non-student identifiers). `list` and `search` accept these filters and
`--category`, `--status {all,open,completed,archived}`, `--include-archived`.
`open` and `completed` apply to Tasks; `archived` selects archived records.
The status `all` defaults to non-archived records unless opted into archived
items. Filtering is in memory, never a new index or database.

`--format text` is the default; `--format json` is available for all operations.
List/search JSON is `{ "count": N, "notes": [NoteRecord, ...] }`. Show and
mutation JSON return one NoteRecord including the revision. Explicit JSON
requests can contain full private note text; redirect output appropriately.
Text list/search emit only bounded previews; text show emits body content with
terminal-control sanitization. Error output does not include private note text,
raw paths, or stack traces.

Input files must be UTF-8 and are bounded at 32 KiB before #239 record-size
validation. `--text-file -` reads redirected stdin (never opens an interactive
prompt). Literal `:notes`, `B`, `M`, and `Q` in note content remain data.
Every mutation uses the specified expected revision; stale edits never
implicitly reload and overwrite.

## Exit status

| Code | Meaning |
|---|---|
| `0` | Success, even for an empty search |
| `2` | Invalid CLI argument, text, or schema input |
| `3` | Requested Note not found |
| `4` | Stale revision: reload first |
| `5` | Inaccessible, malformed, unsafe, or conflicted workspace Notes |
| `6` | Write error or unsupported mutation on record type |

No additional backup/export/sync system is implemented. Actual two-computer
OneDrive behavior and Suite backup/restore remain consolidated-release #244 gates.
