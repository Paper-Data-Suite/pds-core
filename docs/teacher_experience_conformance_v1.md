# Core Teacher-Experience Contract v1 — Conformance Vectors

**Contract:** [`pds_core.teacher_experience/1`](teacher_experience_contract_v1.md)
**Authority:** Suite [Teacher Experience Design Specification v0.2](https://github.com/Paper-Data-Suite/pds-paper-data-suite/blob/49-evergreen-launch-and-supported-composition-upgrades/docs/design/teacher-experience-design-specification.md)
**Owner:** PDS Core for public primitives and Core-owned services; each consumer owns its own screen adoption
**Status:** Normative **design acceptance cases** for Core #236. **Not executable runtime tests, a qualified Notes store, a release, or an installed-consumer attestation.**

These vectors fix observable expectations for the exact public shapes in the contract. Values and scenarios are synthetic. Implementation tickets must turn them into actual tests and include both positive and negative cases. An isolated Core parser test **does not** qualify any real producer's menus.

## 1. Acceptance evidence levels

| Level | What it can demonstrate | What it cannot demonstrate |
| --- | --- | --- |
| D0 — contract review | Public symbols and types, owner boundaries, vector consistency, specification traceability | Importability, data protection or actual teacher interaction |
| D1 — Core source tests | Core API behavior, menu/CLI service parity, test-injected streams, deterministic results | Installed-wheel behavior in each producer |
| D2 — Core installed-artifact tests | Wheel exports, `core`/`pds-core` CLI, local-private OS protections, supported terminals | Adoption by ScoreForm, Quillan, Concord, Meridian, Vitrine, Portia or Suite |
| D3 — independent consumer tests | An opted-in menu's shortcut collisions, return/revalidation, fallback and installed-Core compatibility | A different producer or release combination |
| D4 — Suite composition and classroom trials | Exact accepted installed versions, Suite trusted launch/context boundaries, practical Windows/ARM64 and non-ANSI behavior | Future modules, arbitrary shared-OS-login isolation or unqualified feature versions |

**Gate:** Completing Core #236 establishes **D0 only**. Core #237–#244 must qualify their own D1/D2 gates. Suite #51 and module adoption issues must qualify their own D3/D4 gates. Never infer those from a Markdown checklist or a proposed contract version.

## 2. Header / stream vectors (H01–H11)

Use the **planned** `TeacherScreenHeader`, `render_teacher_header`, and `print_teacher_header` signatures in contract §2.2. Expected plain header output for a three-field call is `"Quillan\nReview Student Work\nEnglish 12 · Period 2 · Personal Narrative Revision"`, with **no trailing newline** from the pure render function.

| ID | Input or environment | Expected result / violation to prevent | Minimum gate |
| --- | --- | --- | --- |
| H01 | Three validated fields | Exactly three ordered lines; no labels or blank placeholders; `render_*` has no trailing newline | D1 |
| H02 | `context_line=None` or empty | Exactly two ordered lines; no third line or stray blank | D1 |
| H03 | Pure renderer `ansi=True` | Only application-name line has `\x1b[32m` and `\x1b[0m`; visible title/context unchanged | D1 |
| H04 | Pure renderer `ansi=False` | No ANSI escapes; same visible two/three fields | D1 |
| H05 | `print_*` with `color="never"` and injected `StringIO` | Plain header plus exactly one terminal newline; no writes to process-global stdout or stderr | D1 |
| H06 | `color="auto"` and captured, redirected or non-TTY output | Plain, readable header, no ANSI and no clear-screen call | D1/D2 |
| H07 | Supported TTY with color capability, absent `NO_COLOR` | Green application name; title/context plain, including nested and recoverable screens owned by caller | D1/D2/D3 |
| H08 | `NO_COLOR` set, `TERM=dumb`, failing `isatty`, or unsupported Windows VT capability | Plain fallback; no exception, capability forcing or leaked escape codes | D1/D2 |
| H09 | Application/title blank or any string with CR, LF, NUL, ESC or terminal controls | Explicit type/value refusal; no partial print, injection or control-sequence parsing | D1 |
| H10 | `context_line` contains sensitive/student-linked label not approved by caller | Caller must not pass it; renderer is not the context authority or a sanitizing data store | D3 |
| H11 | Windows x86-64/ARM64, terminal, pipe and file output | Repeat H05–H08 against real supported consoles and streams; no color-only meaning | D2/D4 |

`NO_COLOR` policy, Windows capability probing and sanitization are implementation tests for #237; the source-level audit did not perform these trials.

## 3. Prompt-scope/shortcut vectors (C01–C13)

All cases use the planned `parse_shared_teacher_command(value, *, prompt_kind, interactive, allow_notes=False)`. Unless otherwise indicated, inputs use `PromptKind.MENU_CHOICE`, `interactive=True`, `allow_notes=True`. The parser is **pure** and must not read, print, create records, raise Core navigation exceptions or initiate a utility call.

| ID | Input / variation | Expected parser result / producer requirement | Minimum gate |
| --- | --- | --- | --- |
| C01 | `:notes` | `SharedTeacherCommand.NOTES` | D1 |
| C02 | `  :NoTeS  ` | `SharedTeacherCommand.NOTES` (surrounding whitespace stripped) | D1 |
| C03 | `:notes` but `allow_notes=False` | `None`; local behavior unchanged and no implicit dispatch | D1/D3 |
| C04 | `:notes` but `interactive=False` | `None`; no unattended menu capture | D1 |
| C05 | `:notes` with `DATA_ENTRY` (note body, path, filename, search, timestamp or student answer) | `None`; literal field input remains under field-owner validation | D1/D3 |
| C06 | `:notes` with `CONFIRMATION` or `PAUSE` | `None`; cannot approve, refuse or escape confirmation by shared interception | D1/D3 |
| C07 | `N`, `n`, `W`, `w`, `B`, `M`, `Q`, `A`, `H` | `None`; caller retains exact local or existing Core navigation behavior | D1/D3 |
| C08 | Numbers, blank text, `:note`, `:notes 123`, `::notes`, other `:` prefixed values | `None`; no prefix/substring interception | D1 |
| C09 | Invalid Python argument types and invalid prompt-kind | `TypeError`/`ValueError`; no coercion or side effects | D1 |
| C10 | Qualified Quillan selected-student review | `N`/`W` still navigate; an opted-in safe choice intercepts only exact `:notes` | D3 |
| C11 | Quillan free-text review note contains `:notes` | Saved/validated as Quillan-owned literal text or refused by its existing rule; not Core Notes | D3 |
| C12 | A genuine pre-existing local `:notes` collision | Disable shared interception at that screen; provide accessible, labeled Notes & Tasks option at a different safe boundary | D3 |
| C13 | Parser installed, but Notes menu/storage unqualified or disabled | No functioning quick-capture claim; show unavailable/fallback or suppress command hint. Parser token alone is insufficient | D1/D3 |

**Coverage limit:** The Slice 1 audit is a **sample** of each repository's menu-entry and prompt helpers. A producer must enumerate *every adopted nested choice prompt* and its field/confirmation neighbors at its own pinned implementation revision. Unknown surfaces remain unqualified.

## 4. Handoff, return and durability vectors (R01–R12)

The request and result symbols in `pds_core.teacher_context` and menu functions in `pds_core.teacher_menus` are **planned** (contract §4). Cases use fictional Core workspace, class, and non-student assignment references; no real teacher/student data is required.

| ID | Trigger | Required result / caller action | Minimum gate |
| --- | --- | --- | --- |
| R01 | Valid `SharedTeacherMenuRequest` | Nonblank caller label, bounded opaque return token, only permitted `TeacherContextHint`; no producer data read on construction | D1 |
| R02 | Invalid token, class/work types, control characters, non-`Path` workspace | Reject before prompt or write; no partial effects | D1 |
| R03 | Standalone Notes opens without class/work context | Safe workspace/owner resolution; optional context is not invented or required | D1/D2 |
| R04 | `run_*_menu(..., interactive=False)` | `UNAVAILABLE` / `NO_CHANGE`, empty change scopes; `read_line` never called | D1 |
| R05 | Unqualified Notes/admin capability | `UNAVAILABLE` / `NO_CHANGE`; no implicit record or workspace initialization | D1/D2 |
| R06 | Teacher returns with `B`, `M`, `Q` | `BACK`, `MAIN_MENU`, `QUIT` dispositions; **caller** owns continuation/exit; current navigation exceptions elsewhere unchanged | D1/D3 |
| R07 | EOF/Ctrl-C, or cancellation before authorization | `CANCELLED` / `NO_CHANGE`; no canonical record created | D1/D3 |
| R08 | Notes Task saved, then `BACK` or `QUIT` | `COMMITTED` and `{NOTES}`; do not conflate exit and durability or modify producer state | D1/D3 |
| R09 | Several authorized Core writes; later step fails | `FAILED` / `PARTIAL` plus known scopes and accurate next action, no false rollback | D1/D3 |
| R10 | Commit outcome cannot be established after interruption | `INDETERMINATE`, plausible change scopes and inspect/reconcile guidance, not a guessed success | D1 |
| R11 | Core workspace changes while admin menu is open | `{WORKSPACE}` returned; caller invalidates class/roster/work/student selection; new workspace resolved | D1/D3 |
| R12 | No scopes changed but producer revision mutated concurrently | Caller **still** refreshes workspace, relevant Core authority, selected work/student and permissions before consequential continuation; token is not proof of currentness | D3 |

Do not pass a selected student ID or student-specific review into Notes metadata. Quillan → Notes → Quillan and caller → Core administration → caller complete synthetic traces appear in contract §§4.7–4.8, including stale review and roster conflict cases.

## 5. Persistence, CLI parity, privacy and backups (P01–P12)

| ID | Trigger / invariant | Required proof | Gate / owner |
| --- | --- | --- | --- |
| P01 | Actor label changed under same OS account | Cannot use self-declared attribution as Notes owner authentication | D1/D2 #238 |
| P02 | Different OS accounts; unsupported filesystem protections; shared OS login | Test qualified isolation; explicitly refuse to claim secure multi-teacher sharing on one OS login | D2 #238 |
| P03 | Workspace renamed, moved, copied or same-looking class label reused | Stable association and conflict behavior chosen/tested by #238; do not repurpose present workspace marker without review | D1/D2 #238 |
| P04 | Personal Idea / Task / Reflection save, edit, reopen/complete/archive | Guarded Core revision/history rules, no automatic student link or producer mutation | D1/D2 #239 |
| P05 | Note free text may contain personal data | Private store/log minimization and authorization tests; never copy bodies into diagnostics by default | D1/D2 #238–#240 |
| P06 | Caller attempts student-specific metadata or source evidence copy | Refuse structured student reference and prohibited producer payloads; no automatic Grade/Score/support/publication writes | D1/D3 #239/Suite |
| P07 | Personal Task due date is overdue | No unimplemented notification; no conversion to producer/provider attention | D1/D3 #239/Suite |
| P08 | Ordinary whole-workspace backup | Disclose private app-data Notes are **not** included; no false portability assurance | D2/D4 #243/Suite |
| P09 | Explicit private Notes export/restore | Owner-scoped, intentional, integrity/restore/conflict tests, truthful partial receipts | D2 #243 |
| P10 | Core admin menu adds/edits/removes student | Same guarded preview/teacher-confirm/fresh-state/refusal semantics as Core authoritative service, no private roster clone | D1/D2 #241–#242 |
| P11 | Core Notes/admin meaningful menu mutation | Equivalent noninteractive `pds-core` command invoking same guarded service, compatible failure codes; no `:notes` shell alias | D1/D2 #240–#242 |
| P12 | `pds`, `core`, `pds-core` direct commands and producer CLIs | Existing options/flags/exit behavior preserved; unattended invocation never prompts or writes unexpectedly | D2/D4 #237–#244/Suite |

## 6. Specification-level teacher journeys (UX-01–UX-12)

The IDs match Suite specification §12 **exactly**. Rows define eventual owner acceptance, **not** checks that Core #236 can pass by running current source tests.

| ID | Scenario acceptance family | Responsible qualification owner |
| --- | --- | --- |
| UX-01 | Green application identity/title, valid context and plain fallback in main plus three nested screens | Core #237; each producer; Suite #51 |
| UX-02 | `:notes` from Quillan review, Task save, retained N/W, safe return after revalidation | #237–#240; Quillan consumer; Suite #51 |
| UX-03 | Idea from Concord, Reflection from Portia, one permitted owner/workspace collection | #238–#240; Concord/Portia adopters |
| UX-04 | Concord Create and Use Assessment without hidden attachment or duplicate confirmation | Concord #139 and related producer UX issue; **not** Core #236 |
| UX-05 | Concord group/packet truth and guarded teacher confirmation | Concord owner; **not** Core #236 |
| UX-06 | Core-authoritative roster edit from Suite/Core/producer and safe revalidation | Core #241–#242; Suite and producer adopters |
| UX-07 | `pds` teacher home with qualified launch and explicit CLI parity | Suite #15/#51/#49 (distinct trust scope) |
| UX-08 | Cancel, stale, partial/restart receipts based on authoritative state | Core #237–#244 and domain producers |
| UX-09 | Bounded technical-details disclosure, no unrelated data leakage | Each module's adopted screens |
| UX-10 | Notes owner isolation, attribution limits, workspace moves and no structured student IDs | Core #238–#240, #243 |
| UX-11 | ScoreForm Scores, Quillan writing, Meridian Grades and Portia records remain separate | Respective producers; Suite #51 |
| UX-12 | Private backup scope and separation of My Tasks vs Module Attention | Core #239/#243; Suite #51 |

## 7. Minimum acceptance discipline

A subsequent implementation PR must record its **exact Core and producer commits / installed artifacts**, executed test names, environments, cases passed, and expressly untested cases. A test vector is neither a test run nor a guarantee of behavior. A capability is announced only by the implemented Core distribution, never by a source-only design; a consumer advertises the workflow only after its own installed qualification. Source-only Core #236 may close after documented owner review/ADR acceptance and project CI; it cannot close any D1–D4 runtime gate on behalf of later issues.
