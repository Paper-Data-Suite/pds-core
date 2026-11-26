# Core teacher-experience v1 — Source integration and release/adoption boundaries

**Issue:** [Core #237](https://github.com/Paper-Data-Suite/pds-core/issues/237) · **Contract:** [`pds_core.teacher_experience/1`](teacher_experience_contract_v1.md) · **Decision:** [ADR 0005](decisions/0005-adopt-versioned-teacher-experience-public-interfaces.md)

**Status:** Core #237, #239–#242 implemented and merged. Core #244 owns consolidated official release qualification. This is not evidence of producer/Suite adoption.

## 1. Capabilities and what they mean

| Contract surface | Merged Core source capability |
| --- | --- |
| `pds_core.teacher_experience` | Contract version `"1"`, immutable capability inquiry |
| `pds_core.teacher_ui` | `terminal.header.v1` |
| `pds_core.teacher_commands` | `terminal.notes_command.v1` |
| Workspace Notes records | `notes.records.v1` |
| Callable Notes and CLI | `notes.menu.v1`, `notes.cli.v1` |
| Guarded roster edits and classroom menu | `classroom.roster_edits.v1`, `classroom.menu.v1` |
| Separate Notes portability | Reserved, not implemented or advertised |

The seven non-reserved tokens are implemented in merged source. They do
not attest publisher provenance, workspace authorization, released
availability, or independent consumer adoption. Published Core 0.6.6
predates these modules. Use #244 for exact candidate/release evidence
and the [Notes CLI](notes_cli_240.md) for direct commands. Notes follows
the selected shared workspace and its permissions; there is no OS-local
owner store or separate export service.

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

## 3. Safe recognition and qualified dispatch

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

# Synthetic, caller-audited menu-choice demonstration only.
# Real consumers must pass installed/session qualification and collision checks.
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

In the historical #237-only build, `notes_menu_ready` was false. In merged source the tokens are present; the sample still does not implement a caller's dispatch, persistence or context restoration. Seeing `SharedTeacherCommand.NOTES` in a pure parser test is not authorization to open anything. **Do not set `allow_notes=True` globally** or advertise a functioning Notes shortcut merely because the parser exists.

Input provenance matters. Supply `PromptKind.MENU_CHOICE` only for an explicitly audited interactive **choice**. Use `DATA_ENTRY` for note bodies, search, paths, filenames, IDs and teacher prose; use `CONFIRMATION` for exact approvals and `PAUSE` for press-to-continue. Those types never recognize `:notes`, regardless of flags. Neither Core nor the producer should monkeypatch `input()` or the caller's loop. A screen with a preexisting local `:notes` action disables shared interception and preserves its existing behavior; after the full Notes menu qualifies, it may expose a clearly labeled choice on another safe screen.

## 4. D0–D4 evidence and next qualification

- D0: accepted #236 contract and ADR.
- D1/D2: merged #237, #239–#242 source and historical candidate evidence; #244 requalifies the versioned integrated wheel/sdist, actual work/home sync and Suite backup/restore.
- D3: every independent consumer must qualify its own installed Core, adopted prompts, N/W collisions and private work/student/revision/permission refresh on every return.
- D4: Suite composition and physical classroom journeys remain separate; synthetic producer-like Core tests do not prove actual adoption.

The classroom menu returns immediately after a durable operation. Callers must inspect durability and change scopes, reload all relevant authority and handle B/M/Q in their own process. No implicit producer write, cross-process return, distributed lock, academic mutation or personal-task-to-attention conversion. See the [classroom final qualification](issue242_sliceF_final_qualification.md), [Notes acceptance](notes_240_acceptance.md), and [provider diagnosis boundary](issue249_exact_owner_provider_diagnosis.md).
