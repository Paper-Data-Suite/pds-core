# Core #240 — Candidate Notes & Tasks qualification and adoption status

**Development branch:** `240-notes-tasks-menu-cli`. **Starting #240 base:**
`f5cf26b98686e7a31c1dd5e47f7ebbaab069ede7` (merged Core #239).
**Release:** none. The package still reports the existing Core distribution version;
**do not publish that wheel as 0.6.6**.

## Candidate implementation checklist

- [x] #239 workspace-native Idea/Task/Reflection records and guarded services
- [x] Callable interactive Notes entry with typed return/context result
- [x] Direct noninteractive `pds-core notes` service-backed commands
- [x] Opt-in `:notes` at audited `core` main-menu choice prompt, not text entry
- [x] Quick Capture, browse, search, filters, Task state, archive/unarchive
- [x] No per-user Notes database, producer mutation, or Notes sync service
- [x] Slice D Windows regression: 3,432 passed, 19 skipped, zero failures;
  Ruff clean and mypy clean across 328 source files (2026-11-21).
- [x] Slice D isolated installed-wheel smoke outside the source checkout
  (2026-11-21); candidate SHA-256 recorded below.
- [x] Post-review correction qualified on Windows (2026-11-21):
  3,434 passed, 19 skipped; Ruff/mypy clean; isolated installed-wheel smoke
  including negative CLI exits (candidate SHA-256 below).
- [x] Teacher reviewed actual Notes workflows and accepted the functions,
  navigation and task actions apart from stacked screen output (2026-11-21).
- [x] Requalify the screen-lifecycle usability correction and its final wheel.
- [ ] Teacher confirms clean redraw on the corrected installed candidate.
- [ ] Independent source/CI PR review before merging #240

**Qualified Slice D source commit:** `19e353664a15ba87d68a959cb97fc65f5d811208`.
**Slice D candidate-wheel SHA-256:**
`dc3486f2ba01ca853c8dd1779cf094b2590f3a3aa4962fd2471a7a8fbac2b822`.
This hash describes the prior Slice D wheel, not the post-review wheel. The
post-review correction wheel passed its synthetic installed smoke (SHA-256
`2f9629add65a2f816fe5ee977ad774e1a9d2b471be22624eabb176bbcd43f0d9`)
and was committed as `babf95e80acf215abdf56bf85ab561d932c5d9d2`.
The screen-lifecycle repair candidate will be rebuilt after the new tests pass.
**Screen-lifecycle candidate-wheel SHA-256:** `28db9441f2af5bebe2f6b9713044b1ae50f1fc063c6b1b6eaf3de7a4937b42c9`.

**Post-review candidate-wheel SHA-256:** `2f9629add65a2f816fe5ee977ad774e1a9d2b471be22624eabb176bbcd43f0d9`.

**Implementation tokens in the candidate distribution:** `terminal.header.v1`,
`terminal.notes_command.v1`, `notes.records.v1`, `notes.menu.v1`, `notes.cli.v1`.
These are build capabilities, **not** a release/adoption attestation.

## Run installed candidate smoke

1. Build candidate without changing the Core version:
   `python -m build --wheel --no-isolation`
2. From the repository root, run:
   `python scripts/notes_240_wheel_smoke.py --wheel dist/pds_core-0.6.6-py3-none-any.whl`
3. Save the terminal transcript with the candidate commit SHA, wheel SHA-256,
   fresh-venv install path, successful Core quick-capture/Task lifecycle,
   producer-like return result, and CLI status. Only synthetic data may appear.
4. Execute the teacher review of prompts: can one Idea be captured without IDs,
   then an existing Task found/completed, Reflection edited, and archived items
   recovered? Are the `:save`/`:cancel` instructions clear? Does `B` return to
   the immediate Notes screen without abandoning a confirmed save? Do errors
   distinguish unavailable workspace from empty Notes? Document friction and
   fix any material UX failures before closing #240.

The smoke script creates a new **temporary venv** and private synthetic
workspace; it installs the exact specified wheel without networking or source
imports, exercises Core and direct CLI and removes its temporary files.
It does not send a note to a real producer, change workspace preferences,
install into the teacher's existing environment, or publish a Core release.

## Separately qualified consumers and release gates

| Surface | Status | Gate/owner |
| --- | --- | --- |
| Core source menu + CLI | Implemented in #240 branch | Post-review qualified; screen redraw retest pending |
| Clean candidate wheel | Post-review wheel tested; screen-fix wheel pending | Installed smoke and manual clean-redraw retest |
| Published consolidated Core release | Not done | #244 and remaining Core work |
| Suite menu adoption | Not done | Suite #54, with installed artifact qualification |
| Actual producer-menu return / `N`/`W` preserved | Not done | Independently adopting producer repo |
| Actual work/home OneDrive bidirectional and conflicts | Not done | #244 with two devices |
| Suite whole-workspace backup/restore includes Notes | Not done | #244 release gate |
| Classroom/user trial | Not done | Post-qualified installation and teacher review |

Synthetic Core producer-like round trips prove only the in-process API; they
must **never** be reported as an actual Quillan/ScoreForm/Concord/Meridian/Vitrine
adoption. The teacher must retain the caller's private selection/revision and
revalidate it on return; Core cannot guarantee producer authorization.

## Screen lifecycle acceptance (teacher feedback, 2026-11-21)

Teacher evaluation found the Notes capture, search, task lifecycle and return
behavior acceptable, but the terminal stacked every child screen. The Core
menu, Standards and Workspace menus already use `screen.clear_screen`; Notes
owned headers and its preview lacked that call. The repair makes a Notes-owned
screen transition clear the previous interactive terminal view by default;
redirected/captured output remains unchanged. Active multiline entry never
clears between lines. Confirmation, validation and conflict feedback carry to
the next relevant screen, including an unsaved draft for recovery. The teacher
must repeat a short real-terminal navigation check before PR approval.
