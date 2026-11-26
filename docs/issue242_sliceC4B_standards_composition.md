# Core #242 C4B — guarded Standards CLI and private controller

C4A accepted at e03a29fd766882ce612b73c5eae81ad78d3b9414.

New workspace subcommands (global --workspace precedes workspace):

    pds-core --workspace ROOT workspace standards-inspect --format json
    pds-core --workspace ROOT workspace standards-preview add PROFILE ID [ID ...] --format json
    pds-core --workspace ROOT workspace standards-commit add PROFILE ID [ID ...] --expected-current-state-token CURRENT --expected-candidate-state-token CANDIDATE --confirm --format json

Remove and set follow the same contract; set accepts no IDs for empty
membership. Inspect returns the canonical validated library and presence
flag; preview is read-only. Commit uses the exact C4A service; successful
writes report STANDARDS scope, no-op preserves bytes, uncertain writes
report indeterminate with exit 7 and revalidation required. Invalid
inputs exit 2, stale or conflicting state 4, storage refusal 5.
Existing standalone standards commands remain unchanged.

The private shared menu option 3 provides paginated definition/profile
browsing and reviewed existing-profile membership add/remove/set.
Use exact IDs, comma-separated for the interactive entry; unusual IDs
containing commas or reserved navigation words should use CLI parity.
The interactive review is limited to 100 IDs of 200 characters each;
larger proposals require CLI review. Before and after are exact, escaped
lists; one C confirms, B cancels, M/Q/EOF return to caller. No further
prompts after a write receipt. No profile or definition deletion, no
new definition creation, no import/export in this guarded controller.
Legacy standalone Standards workflows remain accessible independently.
The public classroom capability remains unavailable pending full #242.

Local lock limitations from C4A still apply. Qualification via the
existing Git-tracked runner, excluding wholesale formatting of legacy
parser but linting and typing every changed Python file.
