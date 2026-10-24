# Core #237 — Slice 1: Implementation baseline and truthful capability declaration

**Status:** Source-level Slice 1; not an accepted release artifact, installed Core qualification, or producer adoption
**Issue:** [#237](https://github.com/Paper-Data-Suite/pds-core/issues/237), under [#235](https://github.com/Paper-Data-Suite/pds-core/issues/235)
**Baseline:** Core `main` and issue branch at `bc9cff916733904f0971128d8c39cca8a8cc6132` after #236 / PR #245
**Binding design:** [Contract v1](../teacher_experience_contract_v1.md), [ADR 0005](../decisions/0005-adopt-versioned-teacher-experience-public-interfaces.md), [conformance vectors](../teacher_experience_conformance_v1.md)

## 1. Existing implementation boundaries pinned at Slice 1

| Surface | Existing baseline | Preservation rule |
| --- | --- | --- |
| `pds_core.menu_navigation` | `NavigationChoice.BACK`, optional `ALL`, `ReturnToMainMenu`, `QuitPDS`, navigation labels/hints | Do not change semantics, defaults, exceptions or local-command ownership in #237 |
| `pds_core.cli_support.screen` | Core-menu-specific fixed `PDS Core` header; ANSI heuristic tests `isatty()`; clearing is a separate helper | Do not treat this legacy helper as public v1 or rewrite all existing Core screens |
| `pds_core.core_menu` and Standards submenus | Existing main/submenu loops, paths, confirmation prompts and EOF behavior | Do not globally intercept `input()`, change number/B/M/Q commands or claim Notes is active |
| `pds_core.module_operations` | Independent provider interface for module readiness and attention | Do not conflate installation trust or producer attention with teacher-experience capabilities |
| `docs/teacher_experience_contract_v1.md` | D0 accepted public Python shapes and independent capability tokens | Implementation must match names, defaults and behavior exactly; D0 does not establish D1/D2 |
| Core packaging / CLI | `pyproject.toml` version `0.6.6`, Python >=3.11, `core` and `pds-core` existing entrypoints | Do not bump version, create a release, or change CLI behavior in Slice 1 |

The initial source-pinned [#236 audit](issue-236-slice1-teacher-experience-baseline.md) is a **sample** of producer menu behavior; it is not a complete Quillan/ScoreForm/Concord/Meridian/Vitrine/Portia collision census. No producer or Suite release is qualified by this slice.

## 2. Actual Slice 1 public implementation

New public module: `pds_core.teacher_experience`.

```python
TEACHER_EXPERIENCE_CONTRACT_VERSION: Final[str] = "1"

def get_teacher_experience_capabilities() -> frozenset[str]: ...
```

**Current exact return:** `frozenset()`; it advertises **no** capability. The version string identifies the accepted contract major version, **not** Core package v0.6.6, a released feature, a consumer adoption, or an installed composition. An immutable empty set is essential here: neither the full header **print** interface nor the `:notes` parser is implemented in Slice 1. No Notes service, private store, shared Core menu or roster editor exists because of this module.

The frozen token list is: `terminal.header.v1`, `terminal.notes_command.v1`, `notes.records.v1`, `notes.menu.v1`, `notes.cli.v1`, `classroom.roster_edits.v1`, `classroom.menu.v1`, `notes.portability.v1`. **None** may be returned solely because the contract or this module exists. The two terminal tokens become eligible to be added only when the corresponding public implementation is complete and tests pass; later Notes/classroom tokens remain separately gated under #238–#243.

In-process import, version inspection and capability querying perform no terminal IO, Notes/file initialization, current workspace lookup, producer import, or Suite launch qualification. A separately released, exactly tested Core distribution is needed before downstream consumers can rely on these newly defined symbols.

## 3. Planned subsequent implementation and documentation edits

| Slice | Planned scope | Capability effect |
| --- | --- | --- |
| 2 | `teacher_ui.py`: validated immutable header and pure render; deterministic rendering tests | `terminal.header.v1` **not yet** announced until streamed printing also qualifies |
| 3 | Streamed printer plus read-only conservative ANSI/Windows/NO_COLOR detection | Announce `terminal.header.v1` **after** tests qualify the implemented Core facility |
| 4 | `teacher_commands.py`: exact caller-opt-in `MENU_CHOICE` `:notes` parser and C01–C13 vectors | Announce `terminal.notes_command.v1` **after** pure parser and tests qualify; still **no Notes menu** |
| 5 | Synthetic owner-routing harness, compatibility vectors and `README.md`/contract implementation-status reconciliation | No unearned capability or producer adoption |
| 6 | Candidate installed-wheel acceptance from outside checkout, full checks and reviewed issue PR | Record source/installed evidence and any qualified package version separately; no guessed release |

No change is planned to `pds_core.menu_navigation` public semantics, `pds_core.cli_support.screen` API, `core`/`pds-core` parsing, `.github/workflows/ci.yml` merely to add documentation, or producer repositories as part of this first slice. Future work may add bounded integration tests and explicit documentation without asserting a full old-menu migration.

## 4. Slice 1 test evidence and limits

New `tests/test_teacher_experience.py` exercises the exact version and frozen return type, absence of all eight unimplemented capability claims, explicit public exports and a fresh child-process import under a disposable directory with stdout/stderr and filesystem side-effect checks.

The guarded runner must also re-execute pre-existing `tests/test_menu_navigation.py`, `tests/test_core_menu.py`, `tests/cli_menu/test_menu_structure.py`, and `tests/cli_menu/test_batch_cli_equivalence.py`, plus Ruff and strict mypy for the new production module. The runner reports actual results; this source audit does not claim those results in advance.

**Not proven here:** actual green headers, ANSI fallback, prompt-scope command parsing, real Notes use, full test suite, installed wheel, Windows ARM64 physical console, consumer D3 integration or Suite D4 composition. Those are later issue/slice gates.
