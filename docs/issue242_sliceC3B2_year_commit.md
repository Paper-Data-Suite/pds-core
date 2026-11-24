# Core #242 — C3B2 guarded school-year transition service

**Status:** Candidate on `242-workspace-classroom-management-menu`,
focused Windows qualification pending. The actual GitHub issue specified this
service's scope **before implementation**. No new CLI command, menu action,
capability, merge, or official Core release is authorized by this stage.

## Canonical authority and supported operations

The service `pds_core.classroom_school_year_commit` composes the already
qualified C3B1 read-only school-year planner and Core's existing canonical
`school_years.open_school_year` and `close_school_year` writers.

Supported operations:
- **Initial-year open:** only if the workspace exists, no prior year-state
  record exists and no class folders already require history reconciliation.
  Writes one canonical year record with the reviewed, explicit aware
  `opened_at` timestamp.
- **Same active year:** reviewed **no-op**, without rewriting the record,
  creating a lock, or overwriting the existing opening timestamp.
- **Close active year:** writes the canonical closed-state timestamp provided
  in the review, retaining the original opening time and all existing class,
  roster and producer files. A closure time before the recorded opening time
  is refused.

**Not authorized:** opening a new year over an active different year, opening
any year over a closed-year record, or initializing a first year on top of
existing class folders. The existing `open_school_year(..., overwrite=True)`
path is **never** invoked by this service. Closed-year rollover needs a
separate durable preservation policy and acceptance.

## Reviewed state and commit contract

```python
review = plan_guarded_school_year_change(
    workspace_root,
    SchoolYearChange("open", "2026-2027"),
    effective_at=aware_datetime,
)
receipt = commit_guarded_school_year_change(
    workspace_root,
    SchoolYearChange("open", "2026-2027"),
    effective_at=aware_datetime,
    expected_current_state_token=review.current_state_token,
    expected_candidate_state_token=review.candidate_state_token,
    confirmed=True,
)
```

The read-only review reports canonical workspace root, old/new school-year
state, a 64 KiB-bounded exact-byte current-state fingerprint, and a separate
candidate digest binding canonical root, old-state fingerprint, operation,
new year and **exact timezone-aware effective timestamp**.

The commit API requires explicit confirmation. It refuses absent/malformed
tokens, changed state or candidate, invalid timestamps, conflicting years,
and closed-year history replacement. Current-state fingerprint is checked
**before interpreting a potentially changed proposed action** and again
under the local C3B2 writer lock. It then reuses the exact canonical Core
year writer, reloads the saved record, checks its contents and computes a
post-write fingerprint.

Outcomes:
- `committed`: canonical readback matches the reviewed transition.
- `no_change`: same active year; zero new writes or lock.
- `current_state_changed`, `candidate_changed`, `write_conflict`: refused
  without applying the reviewed change.
- `write_outcome_uncertain`: a write may have partially or fully succeeded;
  **inspect canonical state before retrying**. Never falsely claim undo.

## Limits

The lock `.school-year.write.lock` is created inside the selected **existing
workspace root** and removed after the participating writer completes. It
only coordinates new C3B2 writers sharing that local filesystem. Existing
uncoordinated CLI calls, independent processes, and cloud synchronization
do not participate in a distributed CAS transaction. No API claims
cross-machine atomicity or protects against a race by an uncoordinated
legacy writer after the final fingerprint check.

No programmatic review/commit token is an authentication credential.
The future teacher menu must retain both tokens internally, show exact
before/after values, secure one explicit confirmation, then return a truthful
`SCHOOL_YEAR` changed scope and force all producer context to be revalidated.

## Synthetic acceptance

`tests/test_issue242_school_year_commit.py` validates 17 scenarios:
first open and readback; timestamp-bound review tokens; true same-year
no-op; close preserving class/producer data; no-confirmation and bad-token
refusals; changed candidate year or time; stale current state before and
after lock acquisition; lock contention; invalid closure and naive
timestamps; closed-year history protection; refusal to relabel preexisting
class directories; injected failure **after** open and close replacing the
canonical state, with appropriate uncertain outcomes and lock cleanup.

Qualify with focused existing school-year, C3B1 and classroom discovery
tests, Ruff format/lint, strict mypy, exact SHA and clean Windows checkout.

**Next:** C3B3 adds strictly noninteractive school-year preview/commit CLI
parity to this qualified service, preserving old commands. Class creation
and its partial-write recovery remain a separate qualification stage.
Public classroom-management entry stays gated until the full #242
contract is satisfied and consolidated #244 release acceptance passes.
