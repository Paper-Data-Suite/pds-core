# Core #242 — C2A guarded workspace preference service

**Status:** Source and synthetic acceptance candidate committed on the dedicated
#242 branch; Windows focused qualification pending. Scope was recorded in the
actual GitHub issue **before** C2A code. No public classroom-menu write, new
CLI command, capability advertisement, merge, or Core release is authorized.

## Existing authority composed

`pds_core.classroom_workspace_commit` wraps the existing read-only C1 plan and
canonical `pds_core.workspace` functions. It does **not** create a second
settings store:

```python
review = plan_guarded_workspace_preference_change(change)
result = commit_guarded_workspace_preference_change(
    change,
    expected_current_state_token=review.current_state_token,
    expected_candidate_state_token=review.candidate_state_token,
    confirmed=True,
)
```

A `WorkspacePreferenceChange("set", path)` selects a saved workspace
preference. `WorkspacePreferenceChange("reset")` clears only the saved
preference. The current effective workspace can remain unchanged due to
`PDS_WORKSPACE_ROOT` overriding the user config.

## Guaranteed within this service

- **No prompt or implicit confirmation.** A caller must explicitly supply
  `confirmed=True` after presenting the reviewed before/after information.
- The **current token** fingerprints exact config bytes and canonical path;
  the separate **candidate token** binds operation, before/after saved root,
  effective workspace, resolution source, target existence, and current
  token. A change to the proposed target cannot reuse the original review.
- On commit the same canonical C1 plan runs before attempting coordination
  **and again under a local file lock**. Changed current/candidate state
  refuses with a stable error and requests a new preview. Existing lock
  ownership refuses rather than overriding or breaking another lock.
- `no_change` produces no preference rewrite, workspace initialization,
  settings directory or lock. A confirmed `set` may initialize the selected
  workspace *after* review; a confirmed `reset` leaves workspace files and
  producer records untouched.
- After writing, the canonical config is read back and fingerprinted. A
  post-write exception, partial workspace initialization, or unexpected
  saved preference is reported `write_outcome_uncertain`; the teacher must
  inspect before retrying. A successful result reports
  `committed` and the saved config's observed post-write state token.
- Refuse redirected config file or immediate settings directory, malformed
  tokens, stale config, unexpected proposed change, and lock contention.
  Error messages do not embed untrusted config bytes or private OS errors.

## Limits and nonclaims

The `.workspace-preference.write.lock` only coordinates this **new C2
service** in a local config directory. Existing `workspace set/reset`
commands and other uncoordinated processes do not acquire it; neither does
a cloud-sync provider. Consequently these checks are **not a distributed
transaction** and cannot promise atomicity against arbitrary external
writers or provider conflict copies. The caller must revalidate workspace,
year, class, roster, own module work, revision and permissions on menu return.

## Synthetic acceptance

`tests/test_issue242_workspace_preference_commit.py` exercises:

- Read-only reviewed tokens and confirmed set/reset.
- Missing-target initialization; preservation of existing producer data.
- Set/reset no-change paths without incidental file or lock creation.
- Missing confirmation, invalid token, stale config, changed candidate.
- Active local-writer conflict and change before locked revalidation.
- Injected failure *after* config replacement with uncertain outcome.
- Injected workspace-init error with lock cleanup.
- Redirected settings directory refusing a write.

## Required next steps

**C2A gate:** pytest focused C1/C2A and existing workspace tests, Ruff
format/lint, strict mypy, clean exact-SHA Windows checkout.

**C2B:** Introduce a separately qualified noninteractive `pds-core`
workspace preference preview/commit command pair with explicit tokens,
`--confirm`, output status/exit-code parity, and no fallback prompts.
Retain old `workspace set/reset/validate` unchanged.

**Then:** Compose the *qualified* service and CLI into the shared teacher
menu with one clear teacher confirmation, durable change-scope accounting,
and unconditional consumer revalidation. `classroom.menu.v1` remains
withheld until the completed #242 integrated qualification. Official
publication remains reserved for #244.
