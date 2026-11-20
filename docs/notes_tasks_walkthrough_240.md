# Core #240 — Notes & Tasks teacher walkthrough (design freeze, Slice A)

**Status:** UX contract and navigation harness only. Slice A has no functional
Notes menu, does not persist records and does not advertise `notes.menu.v1`.
This is the target walkthrough for implementation in Slices B–D, not proof of
installed or producer adoption.

## Everyday teacher journey (synthetic data)

1. **Contextual entry:** At a qualified producer **menu-choice** screen, the
   teacher chooses `:notes`. The caller retains its work screen and any
   confirmed review, and supplies an opaque return token and only validated,
   eligible **non-student** context hints. A literal `:notes` in a text box is
   teacher prose, not a command.
2. **Quick Capture:** Core shows **Notes & Tasks** with **Quick Capture**, **Open
   Tasks**, **Recent Notes**, **Search/Filter**, and **Archived/Completed**.
   Quick Capture asks **Idea**, **Task**, or **Reflection**. A teacher types a
   planning Idea and explicitly saves. Core confirms **Saved** only after the
   #239 service returns a record and revision. `B` before Save cancels the
   draft without creating a file; navigation after Save does not undo it.
3. **Task later:** From a different session in the same *selected workspace*,
   Core shows **Open Tasks** (excluding completed and archived Tasks). A teacher
   selects an understandable preview, opens the Task, marks it complete, and
   sees the new status. Reopen is available from **Completed**.
4. **Find and revise:** Search does case-insensitive substring matching; class,
   module, work, category, and state filters narrow the validated records. Open
   a Reflection, edit text, and save with the revision originally read. If a
   different version arrived, refuse overwriting it and offer reload/inspect.
5. **Archive:** Archiving hides a record from the default recent list, not
   from the workspace. The teacher can view archived items and unarchive.
6. **Return:** `B` returns one Notes screen at a time; `B` at Notes home returns
   to the caller. `M` returns a **MAIN_MENU** disposition to the *caller*, not
   to a Core-invented process. `Q` returns **QUIT**. The caller checks its own
   return token, then revalidates work/currentness/permissions before resuming.

## Failure and empty-state language

- **Empty notebook:** "No Notes yet. Choose Quick Capture to add one."
- **No open Tasks:** "No open Tasks. Try Recent Notes or Quick Capture."
- **No search matches:** "Nothing matched. Try different words or filters."
- **Stale revision:** "This note changed elsewhere. Reload before editing."
- **Conflict copy:** "A sync-conflicted Notes file needs review. Preserve both
  versions and compare before writing again." Never delete conflict evidence.
- **Unreadable/invalid workspace:** "Notes could not be read in the selected
  workspace. Check workspace availability; nothing was changed."
- **Cancelled before Save:** "Cancelled. No changes were made."
- **Cancelled after a previous Save:** report the earlier confirmed change in
  durability and `change_scopes={NOTES}`; never imply a rollback.

Do not show student IDs, note bodies in routine errors, stack traces, raw paths,
internal tokens, or technical transaction codes. Actual teacher prompts are
reviewed in Slice D; Core-only harnesses do not qualify a producer adoption.

## Slice A boundary

- `teacher_context.py`: frozen request/result public shapes and validation.
- `teacher_menus.py`: callable injected-I/O seam; **returns UNAVAILABLE** for
  real calls until Slice B delivers the actual Notes workflows. A private
  navigation-only test gate permits Core's own synthetic B/M/Q/EOF tests.
- No changes to Core capability tokens, `core` menu options, `pds-core` CLI,
  module repositories, Suite, Notes services or workspace files.
- Next: Slice B replaces the preview-only implementation, adds persistence and
  verified durability reporting, then makes the menu genuinely available.
