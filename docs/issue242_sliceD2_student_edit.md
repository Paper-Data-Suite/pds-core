# Core #242 D2 — individual enrollment composition

D1 accepted at 30ffe9e952b4bacb2f1360fb6e0a9946e83f2ea4 (253 passed,
4 existing symbolic-link tests skipped on Windows). Keep symlink coverage
as a final CI qualification gate.

Private staged menu only. Select Classes and rosters, then a class.
A adds enrollment; select a student by name and exact ID, then E edits
or R removes. Existing #241 student-preview/student-commit CLI and
plan_student_roster_edit/commit_student_roster_edit remain authoritative.

Required add fields are entered explicitly; edit uses field/value pairs,
DONE to review and CLEAR to empty an optional field. Existing optional
columns are supported, other records and column order preserved.
First enrollment from this menu uses the required fields only; richer
initial schema and reserved literal input values can use the existing CLI.
B/M/Q reserved for navigation. Stable IDs cannot be edited. Removal
of the final student is explicitly refused under the existing #241 contract.

Require canonical class metadata in the active year; snapshot year and
metadata and roster state at entry. Recheck after data entry, show exact
escaped before/after record, changed fields and enrollment counts, then
confirm once. Recheck class/year under the participating local year lock
and pass both reviewed roster tokens to #241. No-op preserves bytes.
Uncertain #241 write maps to INDETERMINATE with ROSTER scope, known
pre-write refusal/no change maps to NO_CHANGE. Never retry automatically.
Only canonical enrollment is changed, never historical producer files.
Every receipt requires caller revalidation. The shared menu has narrower
active-class/year and input bounds than legacy CLI; no distributed lock.

Qualification: existing Git runner, focused D2/D1 and #241 regression.
No public capability, merge, release or producer adoption.
