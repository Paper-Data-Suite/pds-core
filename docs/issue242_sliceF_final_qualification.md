# Core #242 F — final development candidate qualification

E accepted at 14697d8a416755586bc8bdaec0cdab29c3d114ae (279 passed).
This branch candidate now advertises classroom.menu.v1 alongside
classroom.roster_edits.v1. The real integrated entry point is exercised
without substituting capability discovery. Earlier unqualified scenarios
use an explicit test fixture that removes only classroom.menu.v1.
The installed #241 probe no longer requires absence of a compatible
later capability.

Candidate qualification order:

1. Existing Git-tracked scoped Ruff safe-fix/format/lint/mypy and focused
   integration regression. Publish only exact mechanical changes after
   all gates. Record the resulting exact synchronized SHA.
2. One complete local Core source regression at the resulting clean SHA.
   Repository-wide lint and strict mypy; prior legacy formatting debt is
   not silently rewritten.
3. Run scripts/qualify_issue242_installed_artifacts.py --expected-head SHA
   from a clean checkout. Build from git archive in a disposable directory;
   check wheel/sdist metadata with twine; record hashes; install each into
   its own venv; run isolated installed capability/menu/roster checks from
   outside the source checkout. No production workspace, user preference,
   release tag, artifact upload or PyPI operation.
4. PR review and existing full Windows/Ubuntu CI matrix; exact-head
   installed acceptance on both OSes; Ubuntu gate requires all four
   redirected roster-path tests to execute without skips. Windows local
   symlink skips are environmental, not evidence of passing those vectors.
5. Maintainer reviews evidence and explicitly approves merge. No release
   until #244; no downstream producer adoption implied by Core capability.

The shared menu returns immediately after a durable operation, rather than
holding a potentially stale caller context for more writes. Confirm C once
after exact review. Existing standalone Standards and Workspace Settings
remain available with their established behavior; guarded shared menu scope
is narrower. Local writer coordination is not a distributed transaction.
All acceptance data must remain synthetic.

Capability publication here is development-candidate only, not a released
or fully qualified distribution until all above gates pass.
