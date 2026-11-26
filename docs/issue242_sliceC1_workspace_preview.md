# Core #242 — Stage C1 workspace-preference preview

**Status:** Candidate on `242-workspace-classroom-management-menu`, focused
Windows qualification pending. Scope was established in the actual #242
description before this implementation. This stage introduces **no writes,
new menu availability, or new CLI command**.

## Existing Core authority and gap

Canonical authority is `pds_core.workspace`:

- `load_workspace_config`, `inspect_workspace_root`,
  `get_default_workspace_root` and `get_workspace_config_path` read state.
- `ensure_workspace_root` validates and can **create** a workspace, its marker,
  and baseline directories.
- `save_workspace_root` writes the user preference atomically; the existing
  `pds-core workspace set` CLI invokes `ensure_workspace_root` first.
- `clear_saved_workspace_root` removes only the user preference; the existing
  `pds-core workspace reset` CLI uses it.
- A `PDS_WORKSPACE_ROOT` environment override takes precedence over the saved
  configuration. Selecting a saved preference may therefore not change the
  effective workspace until that environment override is removed.

The existing CLI is retained unchanged. It does not yet provide a portable
teacher-facing **read-only proposed change + exact state-token commit** pair.
In particular, these existing commands do **not** establish compare-and-swap
or distributed sync safety. It would be misleading to enable a new interactive
write path merely by calling `workspace set` without a review/freshness gate.

## C1 implemented contract

`pds_core.classroom_workspace_preference` provides:

```python
WorkspacePreferenceChange(operation="set", target_root=path)
WorkspacePreferenceChange(operation="reset")
plan_workspace_preference_change(change) -> WorkspacePreferencePreview
```

Its result includes:

- Existing saved preference, and the proposed saved preference.
- Existing effective workspace and its authoritative resolution source.
- Proposed effective workspace **accounting for environment precedence**.
- Existing/missing destination state, and whether a workspace **would need**
  creation later (without creating it during preview).
- Explicit `no_change` for a saved preference already equal to the proposal.
- A bounded SHA-256 snapshot of the exact current user-config bytes and path
  for a **future** guarded commit. The token is not a login credential or
  cross-device transaction guarantee and is not printed for a teacher.

C1 refuses invalid target paths, filesystem roots, non-directories,
non-writable destinations, malformed/oversized/symlinked config records,
and configuration changes detected during planning. Errors are stable,
bounded, and do not interpolate raw private filesystem exception details.

Planning uses the saved/default/environment **Core workspace authority**;
a producer's `TeacherContextHint.workspace_root` is deliberately not taken
as a new saved-preference source.

## Read-only acceptance

`tests/test_issue242_workspace_preference_preview.py` uses only synthetic
user-config and destination paths. Vectors include missing and existing
destinations, same-path no-op, reset with and without a preference, an active
environment override, unchanged config bytes, changed-state fingerprints,
malformed/oversized/redirected config paths, stale-change refusal and invalid
targets. A preview never creates a workspace, saved preference, marker,
directory baseline, lock or producer-owned artifact.

## Next Stage C2 — prerequisite before any new write UI

1. Implement an authoritative **guarded** preference commit rechecking the
   exact proposed change and original config snapshot, under an appropriate
   local coordination rule that does not falsely claim protection from
   uncoordinated legacy writers or cross-machine sync.
2. Define clear no-op/committed/stale/uncertain-write outcomes; ensure a single
   teacher confirmation **after** a readable before/after preview.
3. Provide equivalent explicit **noninteractive** Core CLI preview/commit
   routes with meaningful exit codes and matching state-token checks **before
   enabling** a new durable shared-menu action. Retain existing
   `workspace set/reset/validate/show/paths` compatibility.
4. Integrate guarded actions in the staged shared controller, accurately
   reporting changed `WORKSPACE` scope and caller revalidation obligations.
5. Qualify service/CLI/controller against synthetic race, cancellation and
   partial-write cases before advertising `classroom.menu.v1`.

Related: [Core #242](https://github.com/Paper-Data-Suite/pds-core/issues/242)
and [consolidated release #244](https://github.com/Paper-Data-Suite/pds-core/issues/244).
