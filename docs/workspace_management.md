# Workspace Management

The Paper Data Suite workspace root is the top-level folder where PDS modules
store user data and generated working files. It is separate from source
checkouts, installed packages, virtual environments, and the current terminal
directory.

The default workspace root is:

```text
~/Paper Data Suite
```

On Windows, that commonly resolves to:

```text
C:\Users\<user>\Paper Data Suite
```

Saved workspace configuration lives outside the workspace:

- Windows: `%APPDATA%\Paper Data Suite\config.json`
- macOS: `~/Library/Application Support/Paper Data Suite/config.json`
- Linux/Unix: `$XDG_CONFIG_HOME/paper-data-suite/config.json`, falling back to
  `~/.config/paper-data-suite/config.json`

Workspace resolution uses this precedence:

1. Explicit path supplied to a command, such as `--workspace`.
2. The `PDS_WORKSPACE_ROOT` environment variable.
3. Saved user configuration.
4. Default workspace root.

If `PDS_WORKSPACE_ROOT` is set, it takes precedence over the saved preference.

## Teacher Menu

Open the core menu:

```powershell
core
```

Then choose:

```text
Workspace Settings
```

The Workspace Settings menu can:

- show current workspace status;
- set and save a workspace root;
- validate or create the current workspace;
- reset the saved workspace preference;
- show workspace paths and precedence.

`Show workspace status` and `Show workspace paths and precedence` are read-only
and do not create workspace folders.

`Validate/create current workspace` creates or verifies the workspace root and
initializes the shared baseline workspace structure:

```text
<workspace>/
  .pds/
    workspace.json
  classes/
  scans_inbox/
  scans/
    source/
    review/
```

It does not create class rosters, assignments, standards libraries, usage
ledgers, review records, feedback exports, reports, generated answer sheets,
scored results, date-bucketed scan folders, Quillan files, or ScoreForm files.

`Reset saved workspace preference` clears only the saved config file. It does
not delete workspace files or move data.

## Direct CLI

The same behavior is available from direct commands:

```powershell
pds-core workspace show
pds-core workspace set "C:\Users\<user>\Paper Data Suite"
pds-core workspace validate
pds-core workspace reset
pds-core workspace paths
```

Use `--workspace` for a one-command explicit root:

```powershell
pds-core --workspace ".\tmp-pds-workspace" workspace show
pds-core --workspace ".\tmp-pds-workspace" workspace validate
```

The explicit root does not change saved configuration. To change the saved
preference, use `pds-core workspace set <path>`.

## Starting A Clean Simulation Workspace

To start from a blank simulation workspace without touching the saved
preference, use an explicit workspace:

```powershell
$workspace = "C:\Users\<user>\Paper Data Suite"
pds-core --workspace $workspace workspace show
pds-core --workspace $workspace workspace validate
```

To make that folder the saved default for future PDS commands:

```powershell
pds-core workspace set "C:\Users\<user>\Paper Data Suite"
```

To forget the saved preference later:

```powershell
pds-core workspace reset
```

Reset does not delete the workspace folder. Deleting a workspace folder is a
manual filesystem action and should be done only when the user intentionally
wants to remove local Paper Data Suite data.
