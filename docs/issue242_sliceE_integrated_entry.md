# Core #242 E — integrated entry points and caller-owned handoff

D2 accepted at 1ca72f81d871b990b780fd2ca47c3bb96336e63a (226 passed,
4 existing symlink tests skipped on Windows). The automatic safe Ruff
fix and interrupted recovery workflow is qualified.

The public callable now routes to the complete D2 controller when both
classroom.menu.v1 and classroom.roster_edits.v1 are reported by Core.
Neither capability publication nor any actual producer adoption is
authorized by E; classroom.menu.v1 remains absent. The earlier private
test gates remain available for the slice-specific regression tests.
Synthetic E tests substitute capability discovery only.

Core main menu adds option 6, retaining options 1–5 and :notes. A gated
build visibly labels option 6 unavailable. Core uses the same callable
as the new explicit pds-core workspace menu route. The latter checks
stdin and stdout TTY status, returns 5 when unavailable/noninteractive,
7 for uncertain or partial writes, 1 for other failure, and 0 for normal
navigation. It performs no workspace lookup before the callable gate.
Core main menu preserves its existing injected stream convention.

Both standalone entry points generate an opaque session token and verify
the echoed receipt. Core holds no selected producer work or student,
and resolves workspace/library anew on subsequent actions. Durable
receipts and failures remain visible before Core redraws.

The fictional caller tests reload canonical workspace, active year,
class and roster/student identity plus caller-owned work revision and
permission after every return, independent of empty scopes or matching
token. A changed selection requires refresh/reselect, never automatic
producer writes or artifact regeneration. This is not actual ScoreForm,
Quillan or Suite integration.

F retains full source/installed and Windows/Ubuntu CI qualification,
explicit symlink coverage, capability publication and maintainer approval.
No release or merge at E.
