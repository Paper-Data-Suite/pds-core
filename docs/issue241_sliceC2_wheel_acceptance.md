# Core #241 — Slice C2: isolated installed-wheel acceptance

**Status:** Installed-wheel C2 harness passed at the prior candidate SHA; this
updated harness verifies final candidate capability advertisement. No release.

## Objective

Demonstrate that a wheel built from an exact Git SHA and installed into a
disposable virtual environment exposes the same guarded student roster CLI
as the source checkout, without relying on the checkout's import path or
modifying the teacher's configured workspace.

The harness is `scripts/issue241_installed_wheel_acceptance.py`. It runs
with the wheel virtual environment's Python in isolated mode (`-I`) and
creates its own temporary synthetic class and roster. It refuses to run
outside a virtual environment, verifies the imported package is within
that environment, and checks the installed `pds-core` entry-point metadata.

## Acceptance vectors

- Student-scoped, read-only JSON preview (counts, before/after, state tokens)
  with byte-identical canonical roster before and after.
- Explicitly confirmed commit preserving IDs, other students and optional
  columns.
- Replayed stale token refusal with unchanged canonical bytes.
- Parser refusal when `--confirm` is omitted.
- No-op commit receipt without rewriting canonical bytes.
- Duplicate-key change JSON refusal without a write.
- Legacy `roster import-preview` compatibility.
- Final candidate advertises `classroom.roster_edits.v1` while still
  withholding `classroom.menu.v1` until Core #242.

## Windows acceptance boundary

Build from a `git archive` of the exact feature SHA in an independent
temporary source tree; **do not build in the working checkout**.
Create a fresh venv, install only the candidate wheel with
`pip install --no-index --no-deps`, then execute the harness using
the candidate interpreter with `-I`. Verify the local working tree
remains clean. The local qualification command supplied with this slice
is the canonical Windows entry point for these operations.

Passing this harness proves the candidate wheel's tested behavior,
**not** release readiness. Full Core regression, CI, dependency review,
and final approval remain gated.

## Next after final-candidate acceptance

Confirm the final wheel advertises exactly the accepted roster-edit
capability while withholding `classroom.menu.v1`, then complete Core
#241 full-repository regression, checks, CI and review gates.
Core #242 owns the later menu and interactive student editing experience.

No official release before Core #244.
