# ADR 0005: Adopt Versioned Core Teacher-Experience Public Interfaces

**Status:** Accepted — public teacher-experience architecture and interface contract; runtime and consumer capabilities not yet qualified

**Date:** October 21, 2026

**Decision owners:** Paper Data Suite maintainers

**Applies to:** `pds-core` public UI/navigation/teacher-service contracts and their Suite/producer consumers

**Related issue:** [Core #236](https://github.com/Paper-Data-Suite/pds-core/issues/236)

**Umbrella:** [Core #235](https://github.com/Paper-Data-Suite/pds-core/issues/235)

**Design authority:** [Suite teacher-experience design specification v0.2](https://github.com/Paper-Data-Suite/pds-paper-data-suite/blob/49-evergreen-launch-and-supported-composition-upgrades/docs/design/teacher-experience-design-specification.md), decisions D-01–D-08

**Detailed API contract:** [`teacher_experience_contract_v1.md`](../teacher_experience_contract_v1.md)

## Context

Core 0.6.6 already exposes neutral, public school/workspace/roster services and `pds_core.menu_navigation` for opt-in `A`, `B/M/Q`, labels and unwind exceptions. Its `cli_support.screen` prints a fixed Core header using an incomplete terminal capability heuristic. Producer menus vary: ScoreForm, Concord, Meridian, Vitrine and Portia use Core navigation directly or through adapters; Quillan keeps its own parser and has meaningful `N/W` student-review operations. Most modules also have field, path, confirmation and pause prompts which reuse generic input helpers.

The accepted Suite design needs consistent green application identity, an exact Notes & Tasks command, safe resume, and a callable Core-owned classroom administration menu **without** changing domain authority or hijacking a producer's input loop. A global parser or UI rewrite would be both unsafe and backward-incompatible. A one-shot conversion of all producer releases is unrealistic and unnecessary.

The detailed baseline, including source-pinned producer examples and explicit unreviewed nested menus, is [Core #236 Slice 1 audit](../audits/issue-236-slice1-teacher-experience-baseline.md). It is a source inspection, not installed-module qualification.

## Decision

Define `pds_core.teacher_experience/1` as a **versioned, capability-scoped public integration contract**, separate from the Core package version, Suite specification version and exact installed-composition trust/qualification. Core publishes the API; Suite and producers adopt only released, qualified capabilities and keep existing functional menus until adopted.

### 1. Narrow, explicit public module boundaries

The first planned stable import paths are:

- `pds_core.teacher_experience` — contract version and **implemented** Core capability declaration.
- `pds_core.teacher_ui` — pure header rendering and explicitly streamed printing.
- `pds_core.teacher_commands` — pure parser of an opt-in shared command on a declared eligible prompt.

The exact signatures, fields, enums, defaults and capability tokens are specified in [`teacher_experience_contract_v1.md`](../teacher_experience_contract_v1.md). All are **planned until individually implemented, tested and published** under Core #237 and later issues. No source documentation, ADR status or import-name choice makes them available in Core 0.6.6.

### 2. Header is presentation only

One three-field header carries validated display labels: application name, task/screen title and optional context line. It does **not** establish application trust, actor ownership, class authorization, academic provenance, or a current selected work item. The renderer may format caller-approved labels but must not query producer records or export a student's context to Notes.

ANSI green is a **terminal-capability-dependent enhancement**. A safe plain header is mandatory for `NO_COLOR`, non-TTY and unsupported Windows terminals. Neither import nor render/print may clear a screen, change the process's output stream, set console modes as a side effect, or solicit input. The caller decides when to redraw and what context remains valid.

### 3. Shared command is explicitly prompt-scoped

Only exact `:notes` is reserved, case-insensitively, at an **interactive, caller-declared `MENU_CHOICE` prompt** whose owning module explicitly opts in. Core returns a typed `SharedTeacherCommand.NOTES` indication and does not itself open a menu or persist anything.

Fields (including note bodies, search terms, timestamps, paths, free text), confirmations, and pauses are never eligible, even if they contain the same characters. Quillan's `N/W`, local `H`, numbers, and existing `B/M/Q` plus opt-in `A` remain unchanged. No global interception, monkeypatch, `input()` hook or inferred prompt kind is permitted.

### 4. Capability separation and independent adoption

Advertising `terminal.notes_command.v1` means the pure parser exists; **it is not evidence** of `notes.records.v1`, `notes.menu.v1`, `notes.cli.v1` or safe teacher-private ownership. An installed release may support the header without Notes. An independently launchable producer may remain usable when shared Notes or administration is unavailable. A later Core release must qualify its own capabilities, and each consuming module must separately qualify actual integration and teacher journeys.

Core `paper_data_suite.module_operations` remains a distinct readiness/attention provider. Suite #49 independently owns authenticated module discovery, launch eligibility, update trust and exact integration qualification. Neither interface contract assumes or grants those facts.

### 5. Shared utilities return control; caller still owns currentness

The normative in-process, typed seam is specified in contract v1 §4:

- `pds_core.teacher_context` — immutable `TeacherWorkReference`, `TeacherContextHint`, `SharedTeacherMenuRequest`, `TeacherMenuExit`, `TeacherDurability`, `TeacherChangeScope` and `SharedTeacherMenuResult`. Display/context hints and opaque process-local return tokens **never** constitute teacher identity, currentness or authorization.
- `pds_core.teacher_menus.run_notes_tasks_menu` and `run_workspace_classroom_menu` — separately qualified public Core entry points with caller-injected `read_line`, `output`, `error_output` and explicit `interactive` gating. They call Core-owned services **in-process** and return a structured result; they never spawn Core as a subprocess, take over the caller's input loop or import Suite/producers.
- Navigation (`BACK`, `MAIN_MENU`, `QUIT`, cancellation/unavailable/failure) is **orthogonal** to durable changes (`NO_CHANGE`, `COMMITTED`, `PARTIAL`, `INDETERMINATE`). A canceled session may still have earlier confirmed writes, and an error may follow a partial commit. Results truthfully report affected Core domains; they never promise transactional rollback or prove the caller's producer context remains valid.

The **calling module** owns its suspension/continuation and exact revalidation of workspace, class, roster, student/work selection, producer revision and permissions after return. Core resolves its own canonical authority; an empty change scope does not exempt a caller from reload before consequential action. Switching workspaces invalidates subordinate selections, and `M/Q` requests are handled by the caller's existing menu/quit conventions. See the synthetic Quillan→Notes→Quillan and caller→Core administration→caller traces in contract §4.7–4.8.

The shared-menu public signatures are **planned, not importable in Core 0.6.6**. Core #238–#242 must qualify the actual service and menu capabilities before a consumer enables them. Future durable operations also require deterministic direct `pds-core` CLI routes over the same services. No cross-process return or Suite launch trust is implied.

### 6. Private Notes are not academic records

Initial Notes & Tasks types are **Idea / Task / Reflection**. The store is teacher-private, workspace-associated and OS-user protected as qualified in Core #238, with no first-release structured student IDs or automatic student links. Note bodies are not module attention or canonical evidence, an overdue personal Task is not a module warning, and ordinary workspace backup does **not** include teacher-private application-data Notes. Storage, service, menu/CLI, guarded administration and portability remain Core #238–#243; they are not supplied by this ADR.

### 7. Direct CLI and historical behavior remain compatible

The existing `parse_navigation_choice` signature, flags, `B` enum result and `M/Q` exception behavior remain stable. `core` and `pds-core` are not repurposed; Suite `pds` and producer explicit CLI commands retain their meaning. Any future **meaningful durable menu action** requires equivalent public noninteractive `pds-core` operations with the same underlying validation and atomicity/concurrency behavior. Navigation alone does not require a CLI fake action.

## Invariants

1. Core does not import producer modules or the Suite shell.
2. Existing published navigation commands and exceptions remain unchanged.
3. Exact `:notes` is never intercepted in a field, path, search, confirmation, free-text note or pause.
4. Existing Quillan `N/W`, local `H`, numeric choices and conditional `A` cannot be stolen by a shared parser.
5. No notes or classroom records are created by import, header render or shared-command parse.
6. A menu caller must explicitly enable the shared command at a verified safe prompt, with an accessible exception path when it cannot.
7. An application name or header context is a display hint, not authority, authentication or installation verification.
8. `NO_COLOR`/unsupported output remain readable without terminal escape codes or color-only meaning.
9. Shared Core capability, module adoption, and exact Suite integration qualification are separate facts.
10. Modules revalidate canonical and producer-owned currentness before consequential actions after shared utilities return.
11. Private Notes and Tasks do not mutate or establish module-owned academic, support or publication state.
12. Existing Core workspace/roster/Standards services remain canonical; no second Suite or Notes roster editor appears.
13. No contract is claimed implemented until the relevant Core release actually exports it and its required tests pass.

## Consequences

### Benefits

- Reuses accepted Core infrastructure rather than building a second menu system.
- Lets Core #237 implement header/command primitives independently of later private storage, records, and classroom administration.
- Gives producers a stable opt-in interface without coordinated simultaneous major releases.
- Prevents shared command interception of consequential literal teacher input and preserves Quillan's review navigation.
- Makes missing Core capabilities/consumer qualification visible instead of misclassifying an entire producer as unusable.
- Gives Suite #51 a concrete public contract to adopt while retaining Suite's ownership of overall UX specification and launcher policy.

### Costs and risks

- Producer modules must audit individual nested menu prompts and add narrow adapters; a source-level shared primitive does not automatically modernize their UI.
- A future Core capability list needs careful, release-specific maintenance; it cannot substitute for integration or installed-wheel tests.
- Terminal color capability across Windows/ARM64 and injected streams requires representative runtime qualification.
- Context handoff, Notes private storage/owner isolation, roster edits and portability need separate threat models and contract/test gates before publication.
- Architectural acceptance must not be represented as an implemented or release-qualified capability. The exact Core APIs and each producer adoption remain separate qualification work.

## Alternatives considered

**Patch every producer independently.** Rejected for reusable header/choice mechanics; it preserves divergence and multiplies collision/safety requirements. Producer-specific workflow decisions still remain local.

**Replace `pds_core.menu_navigation` and reinterpret `N`, `B/M/Q`.** Rejected because published downstream semantics and unwind exceptions already exist, and Quillan uses `N/W` for domain navigation.

**Monkeypatch/global `input()` interception.** Rejected because input prompts include student writing, filesystem paths, confirmation phrases and exact IDs; it would silently capture legitimate user data.

**One all-or-nothing Notes/Admin/Core menu framework.** Rejected because it couples unrelated capability release cycles and creates pressure to invent availability when dependencies are missing.

**Use suite-owned application registry/provider data as proof of display/Notes ownership.** Rejected: display labels cannot grant access; Core `module_operations` covers readiness and attention, and Suite #49 owns installed trust independently.

**Force every terminal to output ANSI.** Rejected due to captured tests, redirection, `NO_COLOR`, and Windows VT variability.

## Required follow-up

1. **Core #236 Slice 3:** Typed context, return/outcome, shared in-process menu and private-custody seams specified; runtime and installed acceptance remain Core #238â€“#244.
2. **Core #236 owner sign-off:** ADR 0005 and the precise technical public interfaces are accepted as D0 architecture. Core #237–#244 still own implementation, runtime and installed-artifact qualification.
3. **Core #237:** implement and qualify `teacher_experience`, `teacher_ui`, `teacher_commands` as designed, without touching producers.
4. **Core #238–#244:** independently qualify private Notes ownership/storage, Notes services/menu/CLI/portability, guarded roster editing, callable administration, installed acceptance.
5. **Suite #51/#15 and producers:** independently adopt qualified Core interfaces, with source and installed-screen collision checks and truthful unavailable states.

## References

- [Core #235 shared-experience umbrella](https://github.com/Paper-Data-Suite/pds-core/issues/235)
- [Core #236 contract freeze](https://github.com/Paper-Data-Suite/pds-core/issues/236)
- [Suite design spec v0.2](https://github.com/Paper-Data-Suite/pds-paper-data-suite/blob/49-evergreen-launch-and-supported-composition-upgrades/docs/design/teacher-experience-design-specification.md)
- [Core baseline audit](../audits/issue-236-slice1-teacher-experience-baseline.md)
- [Core existing menu-navigation contract](../../pds_core/menu_navigation.py)
- [Core CLI/menu parity](../cli_menu_parity.md)
- [Core current roster/workspace contract](../roster_workspace_contract.md)
- [Suite #51 design adoption](https://github.com/Paper-Data-Suite/pds-paper-data-suite/issues/51)
