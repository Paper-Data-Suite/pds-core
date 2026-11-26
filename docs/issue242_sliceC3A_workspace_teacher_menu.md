# Core #242 — Stage C3A staged workspace preference teacher flow

**Status:** Source/acceptance candidate on the dedicated #242 feature branch,
pending exact-SHA focused Windows qualification. The actual GitHub issue body
was updated to record C2B acceptance and specify C3A **before** this code.
No public callable-menu availability, `classroom.menu.v1`, merge or release.

## Qualified services composed

Stage C3A uses only the already qualified Core C1/C2A read-only preview and
guarded commit service. C2B provides its matching script-safe CLI commands.
The teacher menu **does not** run a subprocess or recreate the writer:

- `plan_guarded_workspace_preference_change` supplies before/after saved
  preference, effective-workspace changes, environment precedence, and exact
  current/candidate review tokens.
- `commit_guarded_workspace_preference_change` is called **once**, with both
  unmodified tokens and `confirmed=True`, only after an explicit teacher
  confirmation from the reviewed screen.
- The incoming `TeacherContextHint.workspace_root` is an untrusted browsing
  hint **only**, not the saved-preference authority or the path committed.

## Teacher journey behind the C3A test gate

The existing B2 classroom menu retains workspace/year/class/roster/student
read-only browsing, B/M/Q navigation and stale-context checks. The staged
C3A mode adds one fourth home-screen option, **Manage saved workspace
preference**, with two operations:

1. Review a new saved workspace destination; the teacher supplies a path.
2. Review clearing the saved preference; no existing workspace data is
   removed or migrated.

The review displays previous/proposed **saved** roots, current/proposed
**effective** roots, active environment override, and whether the selected
workspace would be initialized. **No raw internal token is displayed.**
The teacher can enter `C` to commit the reviewed change **once**, `B`
to abandon review and return to the operation chooser, `M` to return to
the caller's main menu or `Q` to request caller-owned quit. A second
`B` returns to the staged classroom home screen, and a third returns
the caller-owned `BACK` disposition. EOF/interrupt cancels without writing.
Invalid/unsupported confirmation does **not** commit.

A committed change returns immediately to the caller: the teacher cannot
continue using potentially stale classroom state inside the same menu.

## Return contract

Each result preserves the caller's opaque `return_token` without printing
it. Navigation is independent of durability.

| Observation | `exit` | `durability` | Changed scopes |
| --- | --- | --- | --- |
| Confirmed committed preference | `BACK` | `COMMITTED` | `WORKSPACE` |
| Reviewed no-op | `BACK` | `NO_CHANGE` | none |
| Back, cancel, M/Q, invalid confirmation | corresponding | `NO_CHANGE` | none |
| Stale candidate/config, failed review or refused commit | `FAILED` | `NO_CHANGE` | none |
| Post-write ambiguous outcome | `FAILED` | `INDETERMINATE` | `WORKSPACE` |

All results instruct the producer to independently reload **workspace,
school year, class, roster, work revision, and permissions** before resuming.
The local preference lock has no distributed/CAS guarantee with legacy
writers, cloud storage or independent computers. The UI does not claim one.

## Gating and deferred scope

The public `run_workspace_classroom_menu` remains `UNAVAILABLE` unless
a private synthetic acceptance switch is set. That switch is false by
default. The previously accepted B2 read-only switch is unchanged and
remains read-only. The C3A path does not enable school-year, class,
roster, student or Standards mutations. Their service composition and
acceptance remain separate issue #242 work. No producer handoff
authorization is inferred from this implementation.

## Acceptance

`tests/test_issue242_classroom_menu_workspace.py` uses synthetic user
configuration and workspace paths, keeping real user preferences isolated.
Tests check:

- Public and noninteractive `UNAVAILABLE` boundaries.
- Exact confirmed set and reset with true `WORKSPACE/COMMITTED` receipts.
- Empty preference no-op, no marker/lock/config creation without commit.
- Cancellation at target and review screens; B/M/Q/EOF no-write behavior.
- Stale changed saved config causing refusal rather than silent replay.
- Injected exception after canonical config replacement producing
  `INDETERMINATE`, not a false no-change result.
- Preserved B2 class browsing and visible environment override.
- Opaque return token never printed.

Qualify alongside B2/C2B/C2A/C1 focused tests, Ruff format/lint and strict
mypy on changed Python files, with exact Git SHA and clean worktree.
Do **not** run a full repository regression for this stage alone.

**Next:** C3B service/menu composition for school-year and class, then
Standards and roster actions according to issue #242. Main-menu/producer
adoption and capability publication are deferred until their own
integration and installed-wheel acceptance.
