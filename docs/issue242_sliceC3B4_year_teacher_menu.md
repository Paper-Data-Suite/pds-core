# Core #242 — C3B4 private school-year management menu

**Status:** Candidate only on the dedicated #242 branch, awaiting
exact-SHA Windows qualification. Scope was recorded in the live GitHub
issue **before implementation**. No public menu availability, capability
advertisement, merge or release is authorized by this stage.

## Qualified authorities reused

C3B4 composes C3B1 read-only administration planning, C3B2 guarded
school-year writes and C3B3 noninteractive CLI parity. The teacher
menu calls the same canonical C3B2 service **in process**; it does not
shell out, duplicate the writer, mint approval or bypass reviewed tokens.

In `pds_core.teacher_menus`, the new private
`_CLASSROOM_SCHOOL_YEAR_PREVIEW_TEST_ONLY` flag defaults to `False`.
When set for **synthetic qualification only**, the existing staged
classroom controller retains B2 read-only workspace/class/roster/student
browsing and C3A's reviewed saved-workspace preference management, then
adds `5. Manage school year`. All existing private-gate paths retain
their behavior. Normal public `run_workspace_classroom_menu` remains
`UNAVAILABLE` and noninteractive public use is refused.

## Teacher workflow

The teacher chooses **Review opening the first year** or **Review
closing the active year**. Opening requires a validated `YYYY-YYYY`
identifier; both actions require an **explicit ISO 8601 timestamp with
UTC offset**. No implicit 'today', local-time conversion, or silent
historical date is invented. An entered timestamp is held unchanged
for the review and commit. Examples:
`2026-09-08T08:00:00-04:00`,
`2027-06-30T12:00:00-04:00`.

The review shows the canonical selected workspace, operation, prior
record status, previous/proposed active year, exact effective timestamp,
and whether the action is a no-op or preserves class/roster/producer
files. It intentionally does **not** show the internal SHA256 tokens.
The teacher must enter one `C` to commit exactly the reviewed action.
`B` cancels the review to the action chooser and ultimately returns to
the parent classroom home; `M` returns to the caller-owned main menu;
`Q` requests caller-owned quit; EOF/interrupt cancels. Invalid
input, an unsupported timestamp or any other response besides `C`
does not write.

The selected root and active-year baseline are taken from the
controller's **authoritative Core discovery snapshot**, not directly
from a caller-provided `TeacherContextHint` as a write instruction.
If the active year changes between viewing the classroom context and
review, the action refuses. If canonical state changes after review,
the guarded C3B2 service rejects stale state/candidate tokens and the
controller returns a failed receipt. The menu returns immediately after
any confirmed commit, no-op or uncertain write so the caller cannot
continue with stale workspace/class/roster state.

## Return semantics

| Observation | Exit | Durability | Changed scopes |
| --- | --- | --- | --- |
| Confirmed year open or close | `BACK` | `COMMITTED` | `SCHOOL_YEAR` |
| Confirmed same-year no-op | `BACK` | `NO_CHANGE` | none |
| B, M, Q, EOF or declined review | corresponding navigation | `NO_CHANGE` | none |
| Stale context, changed state or safe refusal | `FAILED` | `NO_CHANGE` | none |
| Canonical writer may have succeeded before failing | `FAILED` | `INDETERMINATE` | `SCHOOL_YEAR` |

Each result retains the caller's opaque `return_token` without printing
it and tells the caller to **revalidate workspace, school year, class,
roster, work and permissions** on return.

## Exclusions and concurrency limits

C3B2 deliberately refuses closed-year replacement, opening another year
over an active different year, and establishing a first-year record over
unreconciled existing class folders. The menu introduces no escape hatch.
An authorized close leaves canonical class folders, rosters and producer
data untouched. The local C3B2 lock coordinates participating new writers
only; it is not distributed compare-and-swap across cloud sync or legacy
CLI processes. No rollback or automatic retry is claimed after an
indeterminate write.

Class creation, rollover preservation, Standards and roster mutations,
producer adoption and public capability publication are **not** in this
slice. They remain separate #242/#244 gates.

## Synthetic acceptance

`tests/test_issue242_classroom_menu_school_year.py` uses only temporary
synthetic workspace folders and a test-only menu switch. It verifies
public and noninteractive `UNAVAILABLE` boundaries; exact confirmed
first-year open and active-year close; same-year no-op without a lock or
rewrite; preservation of producer files; no token leakage; B/M/Q/EOF,
bad year, naive timestamp and declined confirmation; changed active-year
context; injected stale state after preview; `INDETERMINATE` after
canonical replacement; closed-year history refusal; and preservation
of staged B2/C3A navigation.

The Windows qualification must run **scoped automatic Ruff formatting**
on the C3B4 changed Python files, then Ruff check, strict mypy and focused
C3B4/C3A/B2/C3B3/C3B2 regression. Any changes made by Ruff may be
committed and pushed automatically only after every gate passes and a
remote exact-head, allowed-path, and clean-tree check. No broad
`ruff check --fix` and no unrelated historical-file formatting.

**Next:** Continue #242 with guarded class creation, partial-create
recovery and CLI parity before enabling its teacher-menu action; then
Standards and roster management and final integrated/installed acceptance.
One consolidated official release remains #244.
