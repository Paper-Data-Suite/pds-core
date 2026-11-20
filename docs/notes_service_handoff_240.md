# Core #240 Notes service handoff

`pds_core.notes_service` supplies the #239 data layer. It has no menu, CLI or
producer imports. `pds_core.notes_storage` supplies `list_notes`, `get_note`,
`search_notes`, and `notes_dir`. All functions resolve the selected Core
workspace through `resolve_workspace_root`; the optional `workspace_root`
argument is the same explicit override used by other Core workspace APIs.

| Operation | Call | Return |
| --- | --- | --- |
| Create | `create_note(category, text, context=None, workspace_root=None)` | New `NoteRecord`, revision 1 |
| Edit | `edit_note(note_id, text, expected_revision=..., workspace_root=None)` | Updated `NoteRecord` |
| Task complete/reopen | `set_task_completed(note_id, bool, expected_revision=..., workspace_root=None)` | Updated `NoteRecord` |
| Archive/unarchive | `set_archived(note_id, bool, expected_revision=..., workspace_root=None)` | Updated `NoteRecord` |

Callers must display a record's revision and pass it back on each update. A
`StaleNoteError` means reload before any retry. `NoteAlreadyExistsError` is a
creation ID collision; create a fresh Note rather than replacing it.
`NotesConflictError` means preserve the unexpected/conflict copy and request
manual review. `NotesReadError` means the selected workspace or record is
unavailable, malformed or unsafe; it must not be presented as an empty list.
`NotesWriteError` means the save failed and the caller should inspect the
workspace before retrying. Record validation errors surface as
`NoteValidationError`/`ValueError`; bad caller argument types as `TypeError`.

The service stages bounded UTF-8 bytes in the same directory, flushes them,
and uses exclusive hard-link creation or `os.replace` for an update. The local
OS lock serializes writers sharing one computer and temp directory. It does
not lock a second computer or provide OneDrive compare-and-swap. A sync
conflict copy blocks further Notes reads/writes until the teacher preserves and
compares both versions and resolves them manually. No automatic merge or
conflict deletion is provided.

#240 should build the interactive Notes menu and noninteractive commands over
these operations, including honest conflict/error presentation and return to
the caller's previous screen. Keep `notes.records.v1` unadvertised until the
actual service, menu integration and #244 release gates qualify the installed
Core artifact. The separate Suite design document still needs a narrow
workspace-native Notes correction; no Suite files were edited here.
