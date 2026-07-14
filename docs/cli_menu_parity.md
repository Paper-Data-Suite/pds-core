# CLI and Teacher-Menu Parity

## Policy

PDS Core maintains parity from the teacher-facing `core` menu to the
non-interactive `pds-core` namespace:

> Every meaningful teacher-facing menu operation must have a non-interactive
> CLI route that can reach the same durable state with equivalent validation,
> storage ownership, overwrite protection, and failure behavior.

Parity is about capability and safety, not presentation. A menu may use
numbered choices and confirmations while the CLI uses durable IDs and explicit
flags. Wording, screen layout, prompts, command names, and internal call counts
may differ. A CLI route is not adequate if it requires editing canonical JSON,
calling private Python, simulating keystrokes, or launching the menu.

Several CLI invocations provide parity only when they preserve atomicity,
ordering, metadata, duplicate handling, overwrite protection, and recovery
after failure. A sequence that can leave an accepted prefix of a compound
request written is not equivalent to one atomic menu write.

Classifications used below are:

- **Exact parity**: both interfaces use the same handler or the same shared
  operation with equivalent inputs, outputs, storage, and safety.
- **Relative parity**: presentation or invocation differs, but the same durable
  result and important safety guarantees are available.
- **Partial parity**: the CLI can reach some or all of the state, but loses an
  important safety or scope guarantee.
- **Gap**: no adequate non-interactive route exists.
- **CLI-only**: an intentional power-user capability without a teacher-menu
  expectation.
- **Navigation only**: terminal navigation with no durable application state.

The four compound-mutation gaps identified by the audit are closed. The direct
CLI and menu now use the same shared in-memory transformations followed by one
atomic canonical-library write. The current teacher-menu capability surface
therefore has complete non-interactive CLI parity.

## Shared behavior and storage

Standards and profile mutations construct an immutable `StandardsLibrary` and
write `<workspace>/standards/library.json` through
`write_workspace_standards_library`. The underlying `write_standards_library`
serializes first, writes and fsyncs a temporary file beside the target, then
uses `os.replace`; each individual library write is atomic. Exports and
standalone profile exports use the same temporary-file replacement pattern.

Read-only standards commands load a missing library as empty and do not create
workspace artifacts. Standards-library mutations do not create usage ledgers,
workspace markers, or module-owned files. Workspace validation is intentionally
different: it creates the workspace marker and documented baseline directories.

Normal command success is exit `0`. Domain, read, write, missing-record, and
overwrite-refusal failures are exit `1` with the error on stderr. Parser and
invalid mode errors are exit `2`. Menu workflows normally remain in the menu
after a handled validation error; a failure escaping the delegated menu returns
`1`. These presentation differences do not change the classifications where
the underlying operation is equivalent.

## Top-level inventory

| Teacher operation | Menu implementation | Non-interactive route | Classification | Evidence |
| --- | --- | --- | --- | --- |
| Standards Management | `CoreMenu._run_standards_menu` delegates to `handle_standards_menu` / `StandardsMenu` | `pds-core standards ...` | Relative parity | The submenu capabilities are classified individually below. Opening a submenu is presentation, not a durable operation. |
| Workspace Settings | `CoreMenu.run` delegates to `handle_workspace_menu` / `WorkspaceSettingsMenu` | `pds-core workspace ...` | Exact parity | Each workspace operation maps to the same handler or shared printer below. |
| Help | `CoreMenu._print_help` | `core --help`; `pds-core --help`; subcommand `--help` | Relative parity | Both provide non-mutating route and capability guidance; menu prose is shorter and context-specific. Exit `0`, no files. |
| Back, Main Menu, Quit, EOF, pause, clear screen | `menu_navigation`, `_pause`, and screen helpers | Shell/process control | Navigation only | No application state is read or written; no product command is required. |

## Standards and profiles parity matrix

All menu paths below start at `core -> Standards Management -> Standards
Library`. `pds-core standards menu` reaches the same interactive menu and is
not counted as a non-interactive equivalent.

| Menu path and operation | Menu method / domain operation | Non-interactive CLI / handler | Mode, files, atomicity, overwrite | Exit/output contract | Class | Follow-up |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Standards -> Browse standards | `browse_standards` -> `handle_standards_list` with `MenuFilterMixin` arguments | `standards list [filters]` -> `handle_standards_list` | Read-only; no files. Menu enumerates values; CLI accepts literals. | `0`; rows on stdout. | Relative parity | None. |
| Standards -> Search standards | `search_standards` -> `handle_standards_search` | `standards search <query> [filters]` -> same handler | Read-only; no files. | `0`; matches on stdout. | Exact parity | None. |
| Standards -> View standard | `view_standard` -> `handle_standards_show` | `standards show <standard_id>` -> same handler | Read-only; no files. Menu also normalizes typographic dashes. | `0` found; `1` missing on stderr. | Relative parity | None; input convenience is not durable behavior. |
| Standards -> Add standard, no subparts | `add_standard` -> `StandardDefinition`, `add_standard_definition`, `_write_library` | `standards add` -> `handle_standards_add` -> same model/mutator/writer | Mutates only `standards/library.json`; one atomic write; duplicates refused. Menu confirms, CLI invocation is explicit. | `0` success; `1` validation/duplicate/write error. | Relative parity | None for the single record. |
| Standards -> Add standard with one or more lettered subparts | `add_standard` -> `add_standard_definitions` -> `_write_library` once | `standards add-batch <path>` -> same transformation and canonical writer | Both validate the complete ordered definition set before one atomic write. The request remains a flat model with no inferred hierarchy. | `0` success; `1` read/validation/duplicate/write error; no partial success. | Relative parity | None. |
| Profiles -> Browse profiles | `browse_profiles` -> `handle_standards_profiles` with `MenuFilterMixin` arguments | `standards profiles [filters]` -> same handler | Read-only; no files. Menu enumerates filter choices; CLI accepts literals. | `0`; rows on stdout. | Relative parity | None. |
| Profiles -> View profile | `view_profile` -> `handle_profile_show` | `standards profile show <profile_id>` -> same handler | Read-only; no files. | `0` resolved; `1` missing or unresolved membership. | Exact parity | None. |
| Profiles -> Create Standard Profile | `create_profile` -> `StandardsProfile`, `add_standards_profile`, `_write_library` | `standards profile create --profile-id ... [--standard ...]` -> `handle_profile_create` -> same model/mutator/writer | All ordered membership is validated before one atomic library write; duplicate profile/member and missing member are refused. | `0` success; `1` validation/conflict/write error. | Exact parity | None. |
| Profiles -> Edit -> Add standard to profile (one selected) | `add_standard_to_profile` -> `replace_standards_profile`, `_write_library` | `standards profile add-standard <profile_id> <standard_id>` -> `handle_profile_add_standard` -> same domain/writer | One membership-only atomic write; metadata preserved; missing/duplicate refused. | `0` success; `1` missing/duplicate/write error. | Exact parity | None for one member. |
| Profiles -> Edit -> Add standards to profile (several selected) | `add_standard_to_profile` -> `add_standards_to_profile` -> `_write_library` | `profile add-standards <profile_id> <standard_id>...` -> same transformation and writer | Both validate all members, preserve metadata and caller order, and write once. | `0` success; `1` validation/conflict/write error. | Relative parity | None. |
| Profiles -> Edit -> Remove standard from profile (one selected) | `remove_standard_from_profile` -> `replace_standards_profile`, `_write_library` | `standards profile remove-standard <profile_id> <standard_id>` -> `handle_profile_remove_standard` | One membership-only atomic write; metadata preserved; missing membership refused. | `0` success; `1` missing/write error. | Exact parity | None for one member. |
| Profiles -> Edit -> Remove standards from profile (several selected) | `remove_standard_from_profile` -> `remove_standards_from_profile` -> `_write_library` | `profile remove-standards <profile_id> <standard_id>...` -> same transformation and writer | Both validate the complete removal, preserve remaining order and metadata, and write once. | `0` success; `1` validation/conflict/write error. | Relative parity | None. |
| Profiles -> Edit -> Replace profile standards | `replace_profile_standards` -> `set_profile_standards` -> `_write_library` | `profile set-standards <profile_id> [--standard ...]` -> same transformation and writer | Both replace membership only, preserve all metadata and requested order, allow an empty membership, and write once. | `0` success; `1` validation/missing/write error. | Relative parity | None. |
| Profiles -> Import profile; Import / Export -> Import profile | `import_profile` validates in memory, confirms add/replace, then `handle_profile_import` | `standards profile import <path> --add` or `--replace --overwrite` -> same handler | One atomic library write. Add refuses conflicts; replace requires explicit overwrite. Malformed/unresolved input is rejected before writing. | `0` success; `1` data/conflict/write failure; `2` missing/conflicting mode. | Exact parity | None. |
| Profiles -> Export profile; Import / Export -> Export profile | `export_profile` -> `handle_profile_export` | `standards profile export <profile_id> <path> [--overwrite]` -> same handler | Atomic target-file write. Existing target refused unless menu confirms / CLI flag supplied. Workspace library is read-only. | `0` success; `1` missing/refusal/write error. | Exact parity | None. |
| Import / Export -> Import full standards library | `import_full_library` preloads/validates, confirms, then `handle_standards_import` | `standards import <path> --replace [--overwrite]` -> same handler | Entire source validates before one atomic replacement of `standards/library.json`; existing target protected. | `0` success; `1` malformed/refusal/write error; `2` without `--replace`. | Exact parity | None. |
| Import / Export -> Export full standards library | `export_full_library` -> `handle_standards_export` | `standards export <path> [--overwrite]` -> same handler | Atomic target-file write; existing target protected. No workspace mutation. | `0` success; `1` refusal/write error. | Exact parity | None. |
| Validate library | `validate_standards_library` -> `handle_standards_validate` | `standards validate` -> same handler | Read-only; missing library is a valid empty library and is not created. Invalid library fails during command/menu loading. | `0` valid/missing; `1` invalid/read error on stderr. | Exact parity | None. |
| Starter Standards -> List packs | `list_starter_standards` -> `list_starter_standards_packs` | `standards starter list` -> `handle_starter_standards_list` -> same package operation | Read-only; does not load or create workspace data. | `0`; pack metadata on stdout. | Relative parity | Formatting only. |
| Starter Standards -> Preview pack | `preview_starter_standards` -> `handle_starter_standards_preview` | `standards starter preview <pack_id>` -> same handler | Read-only; menu selects a displayed number, CLI uses pack ID. | `0`; `1` unknown/invalid pack. | Relative parity | None. |
| Starter Standards -> Validate one or all packs | `validate_starter_standards` -> `handle_starter_standards_validate` | `standards starter validate [pack_id]` -> same handler | Read-only; validates complete bundled libraries; no workspace files. | `0` all selected valid; `1` validation failure. | Exact parity | None. |
| Starter Standards -> Install pack | `install_starter_standards` -> `handle_starter_standards_install` | `standards starter install <pack_id> [--overwrite]` -> same handler | Validates and merges in memory, then one atomic library write. Identical records skip; conflicts refuse unless explicit overwrite. No usage events. | `0` success/idempotent; `1` conflict/validation/write error. | Exact parity | None. |

The profile import/export rows appear in two menu submenus but invoke the same
methods and are one application capability each. The empty-library shortcut
under profile creation can launch Add Standard; it introduces no additional
mutation beyond the rows above.

## Workspace Settings parity matrix

All menu paths start at `core -> Workspace Settings`. Workspace handlers may
raise `WorkspaceRootError`; the direct CLI and top-level menu catch it and
return `1` with an error on stderr.

| Menu operation | Menu method | CLI / handler | Mode and affected state | Atomicity / overwrite | Class |
| --- | --- | --- | --- | --- | --- |
| Show workspace status | `show_status` -> shared `_print_workspace_status(inspect_workspace_root(...))` | `workspace show` -> `handle_workspace_show` -> same functions | Read-only; inspects root, marker, default, and config paths. Creates nothing. Exit `0`. | Not applicable. | Exact parity |
| Set workspace root | `set_workspace_root` -> `handle_workspace_set` | `workspace set <path>` -> same handler | Creates/validates root, `.pds/workspace.json`, baseline directories; atomically saves the user config preference. Does not move/delete data. | Existing valid baseline is retained; marker/config writes are atomic replacements. Exit `0`, failure `1`. | Exact parity |
| Validate/create current workspace | `validate_workspace` -> `handle_workspace_validate` | `workspace validate` -> same handler | Creates/validates resolved root, marker, and baseline directories; does not save preference or create standards/module data. | Idempotent; atomic marker write. Exit `0`, failure `1`. | Exact parity |
| Reset saved workspace preference | `reset_saved_preference` -> `handle_workspace_reset` | `workspace reset` -> same handler | Removes only the user config file if present; never deletes workspace data. Exit `0` whether set or already absent. | No data overwrite; config unlink is the single mutation. | Exact parity |
| Show workspace paths and precedence | `show_paths` -> shared `_print_workspace_paths` | `workspace paths` -> `handle_workspace_paths` -> same function | Read-only; reports explicit, environment, saved, and default precedence. Creates nothing. Exit `0`. | Not applicable. | Exact parity |

`workspace set` necessarily has more than one filesystem effect: it ensures a
usable workspace before saving the preference. A failure can leave a valid
new workspace whose preference was not saved. This behavior is identical
because the menu calls the CLI handler directly; it is documented workspace
setup behavior, not a menu/CLI gap.

## Intentional CLI-only capabilities

These routes remain power-user features. CLI/menu parity is directional, so
their absence from the teacher menu is not a defect:

| CLI route | Handler | Purpose / safety | Class |
| --- | --- | --- | --- |
| `standards validate-file <path>` | `handle_standards_validate_file` | Validate an external full-library file without workspace writes. | CLI-only |
| `standards replace <standard_id> ...` | `handle_standards_replace` | Full-record replacement; one atomic library write. | CLI-only |
| `standards upsert <standard_id> ...` | `handle_standards_upsert` | Explicit add-or-replace; one atomic library write. | CLI-only |
| `standards retire <standard_id> [--force]` | `handle_standards_retire` | Non-destructively set `active=false`; preserves references. | CLI-only |
| `standards reactivate <standard_id> [--force]` | `handle_standards_reactivate` | Non-destructively set `active=true`. | CLI-only |
| `standards profile validate <profile_id>` | `handle_profile_validate` | Validate one profile directly without writes. | CLI-only |
| `standards subjects`, `sources`, `domains`, `categories` | corresponding `handle_standards_*` value handlers | List distinct filter values without writes. The menu exposes these values inside its filter picker rather than as standalone operations. | CLI-only |

PDS2 routing, module discovery/dispatch, scan review, and other APIs without a
current teacher-menu operation are outside this audit.

## Audit evidence

The audit traced parser routes through menu and CLI handlers to their domain
transformations and writers. Existing synthetic tests exercise successful and
invalid IDs, missing references, duplicates, conflicts, overwrite refusal,
malformed imports, deterministic ordering, no-side-effect reads, atomic writes,
starter-pack conflicts, workspace isolation, and intended-file-only mutations.

Focused verification covers `tests/test_core_menu.py`, `tests/cli/`, and
`tests/cli_menu/`. In particular, the tests demonstrate that read-only commands
do not create a workspace, imports validate before replacement, exports refuse
unapproved overwrite, starter installation touches only the canonical library,
and individual mutations preserve the atomic writer contract. The partial
parity classifications follow from executing more than one requested item:
the current CLI handlers accept and write only one item per call, so a later
failure cannot roll back an earlier successful process invocation.

Future menu changes must update this matrix in the same pull request. A new
meaningful menu operation should reuse an existing non-interactive handler or
ship with a documented CLI route and equivalence tests. The matrix must not be
described as complete parity while any row remains **Partial parity** or **Gap**.
