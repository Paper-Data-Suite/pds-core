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
- [ ] Final Windows repository regression, Ruff, mypy, release hygiene
- [ ] Fresh installed-wheel smoke outside source checkout (run script below)
- [ ] Teacher review against the actual interaction transcript (see prompts)
- [ ] Independent source/CI PR review before merging #240

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
| Core source menu + CLI | Implemented in #240 branch | Candidate QA and PR review pending |
| Clean candidate wheel | Not yet accepted | #240 installed smoke pending |
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
