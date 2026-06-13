# PDS Core

PDS Core contains shared infrastructure for Paper Data Suite modules.

Planned responsibilities include:

- identifier validation;
- QR payload construction and parsing;
- legacy ScoreForm `OMR1` compatibility;
- shared Paper Data Suite `PDS1` QR contracts;
- safe route/path construction;
- scan inbox/archive conventions;
- workspace-root conventions.

PDS Core is intended to be used by:

- `pds-scoreform`
- `pds-quillan`

Module-specific scoring, tagging, PDF layout, and reporting logic should remain in the module repositories.

## Current Status

Early setup and design.

See [`migration_plan.md`](migration_plan.md) for the current migration direction.

See [`docs/qr_payload_and_routing_contract.md`](docs/qr_payload_and_routing_contract.md) for the shared QR payload and routing contract.

See [`docs/roster_workspace_contract.md`](docs/roster_workspace_contract.md) for the shared roster and workspace contract.

## Workspace Root

The PDS workspace root is the top-level folder where Paper Data Suite modules
store user data and generated working files. It is separate from the source,
installed package, virtual environment, and current working directory.

The default is:

```text
~/Paper Data Suite
```

Resolution uses this precedence:

1. An explicit runtime argument to `resolve_workspace_root(...)`.
2. The `PDS_WORKSPACE_ROOT` environment variable.
3. The saved user configuration.
4. The default above.

Saved configuration lives outside the workspace:

- Windows: `%APPDATA%\Paper Data Suite\config.json`
- macOS: `~/Library/Application Support/Paper Data Suite/config.json`
- Linux/Unix: `$XDG_CONFIG_HOME/paper-data-suite/config.json`, falling back to
  `~/.config/paper-data-suite/config.json`

For example, a workplace OneDrive folder can be saved as the normal workspace:

```python
from pds_core.workspace import ensure_workspace_root, save_workspace_root

root = ensure_workspace_root(
    r"C:\Users\teacher\OneDrive - District Name\Paper Data Suite"
)
save_workspace_root(root)
```

Consuming modules resolve the root and pass it to the existing route helpers:

```python
from pds_core.routes import assignment_dir
from pds_core.workspace import resolve_workspace_root

workspace_root = resolve_workspace_root()
path = assignment_dir(workspace_root, "english12_p4", "personal_narrative")
```

An explicit root applies only to that call and does not change saved
configuration. `ensure_workspace_root()` can create and validate a workspace,
including a small `.pds/workspace.json` marker; it does not create
module-specific data folders.

Use `clear_saved_workspace_root()` to forget the saved workspace preference and
fall back to the environment variable or default root. Clearing the setting
does not delete the workspace folder, `.pds/` metadata, or user data.

## Development Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
