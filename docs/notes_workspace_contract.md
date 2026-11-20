# Core #239 — Workspace-native Notes & Tasks contract

**Status:** Proposed implementation contract for review; no Notes feature is yet
advertised or released. **Core release policy:** complete all Core work, then one
consolidated Core release. Do not create additional Git worktrees.

## Non-negotiable location

The **existing selected Core workspace** is the source of truth. The teacher
already selects the same PDS workspace via Core on work/home machines, typically
through a OneDrive-synchronized folder. Notes are ordinary UTF-8 files inside
that workspace, **not** an OS-user-local app-data store.

Proposed layout (no change to the existing `.pds/workspace.json` marker):

```text
<selected PDS workspace>/
  .pds/
    workspace.json            # existing Core marker, unchanged
    notes/
      v1/
        note_<uuid4hex>.json  # one complete record per file
```

No new workspace association ID, local owner registry, rebind/fork engine,
secondary sync process, cross-root transaction journal or private-data export.
The directory is not created by a read, by import, or by displaying a menu.

## Schema and API scope

`pds_core.notes_records` defines pure `NoteRecord` and optional `NoteContext`,
`new_note`, `validate_note`, `encode_note`, and `decode_note`. Exact schema v1:
`schema_version` (integer 1), `note_id`, `category` (`idea`, `task`,
`reflection`), `text`, `revision` (positive integer), `created_at`, `updated_at`
(UTC seconds), `completed` (Task only), `archived`, and optional `context`
(non-student `module_id`, `class_id`, `work_id`). No student-ID field or
producer-owned evidence data. Content is private only to the extent the
configured workspace/sync provider is private; do not claim encryption,
local-OS-user isolation, or instantaneous synchronization.

`notes_records` is the strict codec. `notes_storage` reads without mutation.
`notes_service` creates, edits, completes/reopens Tasks and archives/unarchives
Notes using explicit revisions. Core #240 owns the teacher menu and CLI.

## Write and synchronization requirements for next implementation

- Never accept a filesystem path or caller-provided actor label as an alternate
  Notes root; resolve the selected workspace through existing Core workspace APIs.
- Use bounded same-directory temporary files and replace operations to preserve
  previous file content on an interrupted save where the filesystem supports it.
- Do **not** assume a rename is a distributed compare-and-swap across OneDrive
  clients. Recheck the current record revision/bytes before local replacement;
  when stale or a conflict copy exists, **refuse** and preserve both revisions.
- The local lock serializes processes on one computer only. It lives in the OS
  temporary directory, keyed by the selected workspace path, and has no
  cross-machine authority. A synced conflict copy or unexpected temporary file
  blocks reads and writes until a person reviews it. To recover, preserve both
  files, compare their record IDs, revisions, timestamps and contents, choose
  the intended text/status, and save a new revision after resolving the conflict
  outside Core. Do not silently delete either version.
- Cross-device concurrent writes are an explicit **limitation**. Test real
  OneDrive conflict behavior (not just a local two-folder simulation), and do
  not claim a guaranteed merge/synchronization transaction.
- Absent/corrupt/conflicted collection is distinguishable from an empty one;
  do not delete unknown files or conflict copies to make a test pass.
- **#244 release gate:** verify that established Suite whole-workspace backup
  and restore actually preserve `.pds/notes/v1/` bytes, including conflict
  evidence. Core documents the intended opaque backup contract but cannot
  qualify the separate Suite implementation from this repository.

## Teacher-facing acceptance and downstream scope

From Core/Suite, capture a Task in the selected work workspace, synchronize,
open the **same selected workspace** at home, find/update it, and synchronize
back. Core #240 owns the menu/CLI and return to previous screen. Suite #54 owns
consumption of the Core service; separate producer adoption remains optional
and must be actually tested before claimed. Green header exists already on
Core main; do not reimplement or release it independently.
