# Core teacher-experience v1 — Source integration and release/adoption boundaries

**Issue:** [Core #237](https://github.com/Paper-Data-Suite/pds-core/issues/237) · **Contract:** [`pds_core.teacher_experience/1`](teacher_experience_contract_v1.md) · **Decision:** [ADR 0005](decisions/0005-adopt-versioned-teacher-experience-public-interfaces.md)

**Status:** Core #237 **source-implemented**, D1 testing in progress; **not yet a published, installed, qualified release**. Producer/Suite adoption and real Notes & Tasks are **not** implied. This document accompanies the accepted D0 contract; it does not change public signatures.

## 1. Capabilities and what they mean

| Contract surface | State in Core #237 source branch | Capability truth | Next owner |
| --- | --- | --- | --- |
| `pds_core.teacher_experience` | Public contract version `"1"`, immutable capability inquiry | Reports **only** implemented Core functionality | Core #237 |
| `pds_core.teacher_ui` | `TeacherScreenHeader`, pure `render_teacher_header`, and safe streamed `print_teacher_header` | `terminal.header.v1` | Core #237 |
| `pds_core.teacher_commands` | Pure typed `PromptKind`, `SharedTeacherCommand` and prompt-scoped parser | `terminal.notes_command.v1` | Core #237 |
| `pds_core.teacher_context`, `pds_core.teacher_menus` | **Not implemented** by #237 | No menu/context capability | Core #238–#242 |
| Notes records / Notes menu / Notes CLI | **Not implemented** by #237 | No `notes.records.v1`, `notes.menu.v1`, or `notes.cli.v1` | Core #238–#240 |
| Individual roster editing / callable classroom menu | **Not implemented** by #237 | No `classroom.roster_edits.v1` or `classroom.menu.v1` | Core #241–#242 |
| Private Notes export/restore | **Not implemented** by #237 | No `notes.portability.v1` | Core #243 |

The implemented source module currently reports exactly:

```python
frozenset({"terminal.header.v1", "terminal.notes_command.v1"})
```

These tokens are **not** equivalent to installed-wheel qualification, a valid actor/workspace identity, Suite launcher trust, a consumer release's adoption, or a working `:notes` action. Published Core **0.6.6** predates these modules; do not import these functions from a released 0.6.6 wheel. A later **separately qualified and published** Core release must be identified before prescribing a minimum consumer version.

## 2. Safe header use (after installed Core qualification)

```python
from pds_core.teacher_experience import get_teacher_experience_capabilities
from pds_core.teacher_ui import TeacherScreenHeader, print_teacher_header

if "terminal.header.v1" in get_teacher_experience_capabilities():
    # These labels are fictitious, caller-approved display information.
    header = TeacherScreenHeader(
        application_name="Quillan",
        screen_title="Review Student Work",
        context_line="Fictional English 12 Assignment",
    )
    print_teacher_header(header, output=menu_stdout)
```

`print_teacher_header` writes only to the injected stream, using a plain fallback for non-TTY, `NO_COLOR`, `TERM=dumb`, and terminals without proved ANSI capability. The caller—not the renderer—chooses the current validated display context, whether to clear the screen, and when to redraw nested pages. The application label grants **no** installed-application trust, actor identity, student/work permissions, or Note association. Do not copy student-linked context into shared Notes metadata.

## 3. Safe recognition versus unavailable dispatch

```python
from pds_core.teacher_commands import (
    PromptKind,
    SharedTeacherCommand,
    parse_shared_teacher_command,
)
from pds_core.teacher_experience import get_teacher_experience_capabilities

capabilities = get_teacher_experience_capabilities()
recognizer_installed = "terminal.notes_command.v1" in capabilities
notes_menu_ready = all(
    token in capabilities for token in ("notes.records.v1", "notes.menu.v1")
)

# Synthetic, caller-audited menu-choice demonstration only; #237 cannot
# dispatch Notes. A real consumer must also pass its own installed/session
# qualification and collision checks before offering this command.
shared = parse_shared_teacher_command(
    choice,
    prompt_kind=PromptKind.MENU_CHOICE,
    interactive=True,
    allow_notes=recognizer_installed and notes_menu_ready,
)
if shared is SharedTeacherCommand.NOTES:
    # A future qualified consuming controller will own the menu handoff,
    # result processing and canonical/producer currentness revalidation.
    ...
else:
    # Existing module-local actions and parse_navigation_choice still own
    # N/W, B/M/Q, conditional A/H, numbers, invalid inputs and unwind.
    ...
```

`notes_menu_ready` is **false** in Core #237. The sample has no working dispatch, persistence, context restoration, or fake Notes menu. Seeing `SharedTeacherCommand.NOTES` in a pure parser test is not authorization to open anything. **Do not set `allow_notes=True` globally** or advertise a functioning Notes shortcut merely because the parser exists.

Input provenance matters. Supply `PromptKind.MENU_CHOICE` only for an explicitly audited interactive **choice**. Use `DATA_ENTRY` for note bodies, search, paths, filenames, IDs and teacher prose; use `CONFIRMATION` for exact approvals and `PAUSE` for press-to-continue. Those types never recognize `:notes`, regardless of flags. Neither Core nor the producer should monkeypatch `input()` or the caller's loop. A screen with a preexisting local `:notes` action disables shared interception and preserves its existing behavior; after the full Notes menu qualifies, it may expose a clearly labeled choice on another safe screen.

## 4. D0–D4 evidence and next qualification

- **D0 accepted:** [`teacher_experience_contract_v1.md`](teacher_experience_contract_v1.md), [`teacher_experience_conformance_v1.md`](teacher_experience_conformance_v1.md) and accepted ADR 0005 (Core #236 / PR #245).
- **D1 source:** #237 Slices 1–4 implement the three public modules with contract and regression tests. **Slice 5** adds a synthetic caller integration harness, tests local Quillan-like `N/W`, `B/M/Q`, `H`, numeric commands, opt-in, literal fields, unavailable Notes, and stream ownership. Record passing counts only from actual executions.
- **D2 installed artifact:** **Not established by source tests**. Core #237 Slice 6 must build and test a candidate wheel from outside the checkout, check actual package exports/CLI behavior and document exact candidate hash, operating systems and Python versions. Publishing a Core release is a separate approval decision.
- **D3 independent consumer:** Each producer must audit *all adopted nested prompts*, preserve its private academic record/selection semantics, verify safe Notes-menu handoff when later available and test exact installed-Core compatibility. Core's synthetic Quillan-like harness **is not** a Quillan test.
- **D4 Suite/classroom:** Suite #51/#15 and Core #244 coordinate trusted composition, physical Windows ARM64 trials, screen-level usability and unqualified-fallback scenarios. Core #237 tests do not establish these claims.

**Explicit exclusions:** This issue creates no Notes data, no teacher-private Notes ownership, no student link, no roster edit, no `pds-core notes` route, no callable shared admin menu, no new producer imports and no new public Core release number. Core's present `core` and `pds-core` menus and `pds_core.menu_navigation` keep their established behavior. In particular, an overdue personal Task will not become module attention or a Grade.
