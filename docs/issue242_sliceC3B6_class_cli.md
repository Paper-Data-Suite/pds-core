# Core #242 C3B6 — noninteractive class creation parity

Source candidate; Windows qualification pending. C3B5 qualified at
868547ba529083a090810990cb229bbc1e69601e.

Commands (global --workspace precedes workspace):

    pds-core --workspace ROOT workspace class-preview CLASS YEAR --created-at ISO --format json
    pds-core --workspace ROOT workspace class-commit CLASS YEAR --created-at ISO --expected-current-state-token CURRENT --expected-candidate-state-token CANDIDATE --confirm --format json
    pds-core --workspace ROOT workspace class-recovery CLASS YEAR --created-at ISO --format json

All use C3B5's existing service, canonical workspace resolution and explicit
offset-aware timestamp; no new writer or interactive prompt. Preview returns
the exact review tokens and no-write flags; commit requires both tokens and
explicit confirmation and returns CLASS scope on success. Recovery is a
read-only observation, never authorization to adopt, delete or retry a class.
It reports absent, empty_directory, matches_review or conflict; status zero
means the observation was returned, not that class creation succeeded.

JSON envelope: schema_version 1, command, scope class, ok, data and optional
bounded error (code and message). Text uses JSON-escaped values and safe errors.
Exit codes: 0 success/observation, 2 invalid input/confirmation, 4 stale or
conflicting proposal, 5 unavailable storage, 6 incomplete write with no
canonical class change, 7 partial or indeterminate write. Write failures
carry the actual conservative service outcome, affected CLASS scope if
partial/indeterminate, and a revalidation requirement. An empty orphan
is never automatically reused. No public classroom menu, capability,
release or merge is enabled.

Qualification: automatic Ruff formatting on new handler/tests and touched
CLI entrypoint, Ruff lint and strict mypy including legacy parser, focused
C3B6/C3B5/C3B4 and earlier regressions. Avoid wholesale formatting of
the pre-existing parser, whose unrelated sections are not in this slice.
Next: staged teacher-menu class creation using the qualified service.
