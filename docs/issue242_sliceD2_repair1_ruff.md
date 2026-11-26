# Core #242 D2 Repair 1 — automatic safe Ruff fixes

D2 candidate 848818d483314e7ff9a66a3f4b20fcb5f69fc803 stopped at one
F401 unused test import after four files were formatted. No mypy or pytest
ran. No manual change to the student-edit code or test logic is needed.

The tracked runner now reproduces the same per-file transform from exact
HEAD bytes for application and verification: Ruff format, Ruff check --fix
--no-unsafe-fixes --exit-zero, Ruff format. The stdin filename preserves
file-specific configuration. --exit-zero permits collecting the source
output even when a remaining lint error cannot be automatically fixed;
the subsequent ordinary Ruff check must pass. No unsafe fixes are enabled.
All changed Python files still pass strict lint and mypy; the focused suite
must pass before any automatic commit or push.

Recovery accepts only exact formatting-only, intermediate safe lint, or
final Ruff output for unstaged, in-scope changes. Final publication accepts
only the final output. Existing legacy format exclusions also exclude safe
fixes, but not lint or mypy checks. Unexpected paths, staged or untracked
changes, unrelated edits, incorrect SHA or remote changes remain refusals.
An exact interrupted predecessor may be specified with --resume-from,
which must be between the original qualified base and candidate in ancestry.
No unrelated Ruff configuration changes may occur across that transition.

Bootstrap from the verified candidate's Git blob because the checked-out
runner is the old version and four local files are already formatted.
No downloaded scripts, unsafe fix flags or execution-policy changes.
D2 service and private gate remain otherwise unchanged.
