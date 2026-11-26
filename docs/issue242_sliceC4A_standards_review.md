# Core #242 C4A — guarded Standards snapshots and profile membership

C3B7 qualified at d292874b267d8f4d6c47b6117cccc1ffd202d45b.
The existing StandardsMenu uses a cached StandardsLibrary and its existing
writers do not consume exact reviewed-state tokens. Do not expose that
unmodified writer through the shared classroom menu.

C4A establishes a guarded authority boundary over the canonical Standards
Library. Read-only inspection distinguishes an absent library from an
invalid, redirected or oversized library. Decode bounded exact bytes
(32 MiB maximum) with the existing Core deserializer and validator and
recheck the raw fingerprint. Missing means empty; it does not create files.

Profile membership preview uses the existing add/remove/set membership
operations. It binds the canonical root, exact current bytes, operation,
profile and requested IDs, and complete validated candidate. Review exposes
before/after membership. Commit requires explicit confirmation and both
review tokens, rechecks under the shared local administrative/year lock,
uses the existing atomic Standards writer, then verifies persisted state.
No-op preserves bytes. Removing membership never deletes standard
definitions; unrelated profile metadata, frameworks and usage records
are preserved. Ambiguous write failures require inspection before retry.

The lock coordinates only participating guarded administrative writers;
legacy Standards writers and sync providers do not share this lock. This
is not a filesystem compare-and-swap or distributed transaction. Do not
claim stronger guarantees or silently retry after uncertainty.

Scope: existing profile membership add/remove/set only; no public menu,
new CLI commands, definition creation/import/export, release or merge
in this slice. Next: CLI parity and private Standards browsing and profile
membership menu composition. Existing standalone Standards functionality
is not removed or altered. Further mutation routes must satisfy the same
review/confirmation/freshness contract before exposure in the shared menu.

Qualification: Git-tracked runner, automatic scoped Ruff formatting,
lint, strict mypy and focused Standards and prior classroom regressions.
