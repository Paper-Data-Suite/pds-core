# Core Teacher-Experience Interface Contract v1

**Contract ID:** `pds_core.teacher_experience/1`

**Status:** Proposed technical contract freeze for Core #236, Slice 2; not an implemented or release-qualified API

**Source baseline:** Core `main` `bf3e6c08dd3f51e47cdbe56b11a3873a9d4491b3` (`pds-core` 0.6.6)

**Design authority:** [Suite teacher-experience specification v0.2](https://github.com/Paper-Data-Suite/pds-paper-data-suite/blob/49-evergreen-launch-and-supported-composition-upgrades/docs/design/teacher-experience-design-specification.md), owner-accepted decisions D-01–D-08

**Architecture decision:** [ADR 0005](decisions/0005-adopt-versioned-teacher-experience-public-interfaces.md)

**Evidence:** [Slice 1 baseline and ownership audit](audits/issue-236-slice1-teacher-experience-baseline.md)

**Implementing issues:** Core #237–#244; consuming Suite #51/#15 and separately qualified producers

> **Specification, not implementation.** Every symbol specified under **Planned v1 public surface** is **absent from Core 0.6.6** unless explicitly marked as an existing API. No producer or Suite release may claim v1 capability on the strength of this document or the proposed ADR. This is the binding proposed shape for subsequent implementation/review, subject to deliberate change control before Core #236 closes.

## 1. Contract identity, authority and release boundaries

`pds_core.teacher_experience/1` is a **Python, in-process Core integration contract**, not a JSON schema version, a package version, a Suite installation/composition attestation, or a version for a particular module's menus. One Core release may implement only a subset of its distinct optional capabilities. Do not infer Notes storage, shared-menu availability or producer adoption from the mere existence of version `1`.

Dependency direction stays `Suite -> Core` and `producer -> Core`. Core must not import Suite, producer packages, or their private records. Existing neutral Core authority (workspace, classes, rosters, Standards, registry) remains unchanged. UI objects have no academic, teacher-identity, access-control or installed-application authority.

### Existing, published v0.6.6 APIs — explicitly **not superseded**

- `pds_core.menu_navigation.NavigationChoice`, `ReturnToMainMenu`, `QuitPDS`, `parse_navigation_choice`, `navigation_labels`, `print_navigation_options`, `navigation_hint`.
- `pds_core.workspace`, `pds_core.rosters`, `pds_core.roster_imports`, `pds_core.classes`, `pds_core.school_years`, `pds_core.standards`, and current direct CLI behaviors.
- `pds_core.cli_support.screen` is a **Core menu implementation helper**, not the new cross-module UI contract; its fixed `PDS Core` header and current ANSI behavior are not a v1 conformance claim.
- `paper_data_suite.module_operations` is a **different** versioned Core provider protocol for readiness/attention, not Notes or a shared menu launcher.

The existing `parse_navigation_choice(...)` continues to strip/casefold a one-letter value, **return** `NavigationChoice.BACK`, **raise** `ReturnToMainMenu` for enabled `M` and **raise** `QuitPDS` for enabled `Q`; `A` is opt-in. New parsing does **not** insert a value into `NavigationChoice`, wrap its exceptions, or change its default flags.

## 2. Planned v1 public surface — exact symbols and signatures

These names are normative **design targets**, not importable now. `TextIO`, `Literal`, `Enum`, and `dataclass` have their usual Python 3.11 meanings. Static types below define the API boundary; implementations may use private helpers without changing these public shapes.

### 2.1 `pds_core.teacher_experience`: version and capability declaration

```python
TEACHER_EXPERIENCE_CONTRACT_VERSION: Final[str] = "1"

def get_teacher_experience_capabilities() -> frozenset[str]: ...
```

The advertised capability tokens are exact, independent strings:

| Token | Core capability; when legitimately advertised | Implementing issue |
| --- | --- | --- |
| `terminal.header.v1` | Reusable header rendering and print path, including safe color fallback | #237 |
| `terminal.notes_command.v1` | Pure, explicit, prompt-scoped `:notes` recognition (not a Notes service) | #237 |
| `notes.records.v1` | Qualified private record service on qualified owner/workspace association | #238–#239 |
| `notes.menu.v1` | Callable Core Notes & Tasks interactive menu | #240 |
| `notes.cli.v1` | Supported noninteractive Core Notes command family | #240 |
| `classroom.roster_edits.v1` | Guarded per-student preview/commit services | #241 |
| `classroom.menu.v1` | Callable Core Workspace & Classroom Management menu | #242 |
| `notes.portability.v1` | Qualified private Notes backup/transfer/recovery | #243 |

`get_teacher_experience_capabilities()` MUST return an immutable set of **only the Core facilities actually implemented, tested and exposed by that installed distribution**. Tokens are monotonic within one contract major version after publication, except where an explicitly documented security withdrawal prevents continued safe use. Advertising `terminal.notes_command.v1` does not mean Notes storage or a Notes menu is usable. The version and tokens convey **Core implementation**, not Suite's authenticated launch status, a producer's adoption, or an integration attestation.

A Core version lacking the `pds_core.teacher_experience` module is pre-contract. Consumers must distinguish that from a **broken import** in a supposedly conformant Core release; do not catch and disguise arbitrary nested `ImportError`, disable another module's healthy launcher, or claim cross-module qualification without installed acceptance.

### 2.2 `pds_core.teacher_ui`: identity and header renderer

```python
@dataclass(frozen=True, slots=True)
class TeacherScreenHeader:
    application_name: str
    screen_title: str
    context_line: str | None = None

def render_teacher_header(
    header: TeacherScreenHeader,
    *,
    ansi: bool = False,
) -> str: ...

def print_teacher_header(
    header: TeacherScreenHeader,
    *,
    output: TextIO,
    color: Literal["auto", "never"] = "auto",
) -> None: ...
```

**Input and validation.** `application_name` and `screen_title` must be nonblank, single-line, already teacher-safe display strings. `context_line` is optional and omitted entirely when `None`/empty. The dataclass validation must reject embedded CR/LF, NUL, ESC and other terminal control codes; it must not silently paste arbitrary module-produced bytes into an ANSI sequence. No global display-name registry is made an authorization or installed-component trust oracle. The recognized display names in specification §5 are **Paper Data Suite**, **PDS Core**, **ScoreForm**, **Quillan**, **Concord**, **Meridian**, **Vitrine**, **Portia**. A future approved module may provide its own verified label; the renderer itself does not validate its installation.

**Pure render semantics.** `render_teacher_header` returns exactly two or three lines joined by `\n`, **without** a final newline or clearing the terminal:

```text
Quillan
Review Student Work
English 12 · Period 2 · Personal Narrative Revision
```

With `ansi=True`, **only** the application-name line is wrapped with green SGR (`\x1b[32m` and `\x1b[0m`) and the remaining text/line order is identical. A two-line header has no blank placeholder third line. No student, work, actor or authorization identity is discovered or persisted by the renderer.

**Printing and capability.** `print_teacher_header` writes the one rendered header followed by exactly one output newline to **only** the supplied `output` stream. `color="never"` always writes plain text. In `color="auto"`, ANSI is permitted only for an interactive stream with demonstrable ANSI/VT capability **and when `NO_COLOR` is absent/disabled by policy**. Mere existence of a Windows TTY is not proof that ANSI/VT is usable. Probe errors, non-TTY, redirected/captured output, unsupported Windows console modes, `TERM=dumb`, and `NO_COLOR` must produce plain text. The implementation may use a narrow internal capability helper and injected synthetic streams in tests, but it may not silently turn on terminal VT mode, clear the screen, change global stdout, or manipulate global input. Color adds emphasis only and never conveys the sole meaning of a status.

Callers own screen clearing (if any), active context validation, and appropriate placement of a fresh header **at the start of each PDS-owned interactive screen**: nested pages, task screens, results, recoverable errors. External file dialogs and viewers are outside Core's control. No additional compact-mode user preference is introduced.

**Example after a qualified Core release** (not runnable against Core 0.6.6):

```python
from pds_core.teacher_ui import TeacherScreenHeader, print_teacher_header

header = TeacherScreenHeader(
    application_name="Quillan",
    screen_title="Review Student Work",
    context_line="English 12 · Period 2 · Personal Narrative Revision",
)
print_teacher_header(header, output=menu_stdout)
```

### 2.3 `pds_core.teacher_commands`: one explicit shared-command parser

```python
class PromptKind(str, Enum):
    MENU_CHOICE = "menu_choice"
    DATA_ENTRY = "data_entry"       # includes path, filename, text and search
    CONFIRMATION = "confirmation"   # exact approval or refusal
    PAUSE = "pause"

class SharedTeacherCommand(str, Enum):
    NOTES = "notes"

def parse_shared_teacher_command(
    value: str,
    *,
    prompt_kind: PromptKind,
    interactive: bool,
    allow_notes: bool = False,
) -> SharedTeacherCommand | None: ...
```

This function is **pure**, does not read input, print output, launch a submenu, mutate state, or raise `ReturnToMainMenu` / `QuitPDS`. It returns `SharedTeacherCommand.NOTES` **iff all** of the following are true:

1. `prompt_kind is PromptKind.MENU_CHOICE` (exact Enum member, not heuristically inferred from an input string);
2. `interactive is True` (caller is operating a genuine interactive menu, not an explicit direct CLI invocation);
3. `allow_notes is True` (caller has explicitly qualified and enabled this safe choice boundary); and
4. `value.strip().casefold() == ":notes"` exactly.

In every other case the function returns `None`. It does **not** parse `B/M/Q`, `H`, `A`, `N`, `W`, any numeric choices, partial prefixes like `:not`, or arbitrary colon commands. Those remain caller/local navigation responsibilities. For unexpected *argument types* it raises `TypeError` or `ValueError` without side effects; it does not coerce objects to strings. `PromptKind` values other than `MENU_CHOICE` are never treated as command-enabled merely because they happen to carry the token.

**Caller integration order** at an explicitly eligible *choice* prompt:

```python
command = parse_shared_teacher_command(
    choice,
    prompt_kind=PromptKind.MENU_CHOICE,
    interactive=True,  # established by the owning menu/session
    allow_notes=notes_menu_is_qualified_for_this_screen,
)
if command is SharedTeacherCommand.NOTES:
    # Owning controller invokes the separately qualified Core Notes menu.
    # It owns suspension/return, reevaluation and normal command availability.
    ...
else:
    # Existing local actions and parse_navigation_choice remain unchanged.
    ...
```

The explicit caller flag ensures the existing local command namespace cannot be stolen silently. A screen which uses `:notes` for a preexisting local action must **not** enable the shared parser at that site; it must offer a clearly labeled **Notes & Tasks** choice at a safe boundary instead. A Notes menu may only be called when `notes.menu.v1` and dependent private-storage capabilities exist, are compatible and are qualified for the consuming screen. `terminal.notes_command.v1` alone is insufficient. A screen may advertise a **disabled/unavailable** Notes option with an honest reason; it cannot claim to save Notes without the separate service.

This v1 parser **does not** implicitly wire commands into Core's existing `parse_navigation_choice`. Existing Quillan `N` (Next Student) and `W` (Next Student Needing Review) remain reserved in Quillan. `H` remains conditional/local. `M/Q` exception/unwind behavior remains as already published. Do not monkeypatch builtins, `input`, `sys.stdin`, `argparse`, or a producer's menu loop.

### 2.4 Required parsing vectors for #237 (specified now, not yet executable)

| Input | Prompt kind | Interactive | `allow_notes` | Expected result |
| --- | --- | --- | --- | --- |
| `:notes` | MENU_CHOICE | true | true | NOTES |
| ` :NoTeS ` | MENU_CHOICE | true | true | NOTES |
| `:notes` | MENU_CHOICE | true | false | `None` |
| `:notes` | MENU_CHOICE | false | true | `None` |
| `:notes` | DATA_ENTRY | true | true | `None` (literal text) |
| `:notes` | CONFIRMATION | true | true | `None` (not approval) |
| `:notes` | PAUSE | true | true | `None` |
| `n`, `N`, `w`, `W` | MENU_CHOICE | true | true | `None`; owned locally |
| `b`, `m`, `q`, `a`, `h`, `1` | MENU_CHOICE | true | true | `None`; owned locally |
| `:notes anything`, `:note`, `:debug`, `::notes` | MENU_CHOICE | true | true | `None` |
| blank, whitespace | MENU_CHOICE | true | true | `None` |

A real producer adoption test must additionally exercise local N/W/number/H/B/M/Q behavior and review-side text entry, not just this isolated table. Core #237 owns implementation-level contract tests; producer repos retain their own menu-journey and installed-wheel tests.

## 3. Compatibility, capability and migration policy

1. **Contract version is explicit.** The `"1"` designation is independent of Core distribution `0.6.6`, future Core package releases, and Suite's historical release manifest. A breaking Python API semantic/signature change requires a reviewed major contract revision, not a silent import-path rewrite.
2. **Feature tokens indicate Core only.** Consumers check the capability they need; missing capability means that **specific** feature is unavailable or a documented local fallback applies. No blanket refusal to launch an otherwise healthy module. Capability checks are not authentication, Core workspace access checks, Suite integrated-release attestations, or an endorsement of an installed producer workflow.
3. **No import-time takeover.** Importing any v1 Core module must not clear the screen, prompt, register commands globally, create workspace/private Note files, access producer stores, or install terminal signal handlers.
4. **Additive public evolution.** Once released and documented, public symbols and default behavior remain stable within contract v1. New optional APIs get explicit capability identifiers as necessary; no family-wide upgrade lock or forced one-day producer migration.
5. **Fallback.** Existing releases use their present headers, menus and CLI safely until separately adopted. If a required Notes/storage/admin service is absent, the consumer must not pretend it exists; preserve existing local workflows and label unsupported shared choices appropriately.
6. **CLI parity.** The shared `:notes` command is not a shell command or positional shortcut. Meaningful future Core Notes/admin operations require their own deterministic, explicit noninteractive `pds-core` routes using the same guarded services. Existing `core`, `pds-core`, `pds`, and producer scripts retain their established behavior.
7. **Qualification.** Source contract acceptance does not grant a feature to an installed component. Reuse exact release artifact/entry-point eligibility and integration gates owned by Suite #49; independently test installed consumer actions before claiming module-level UX conformance.

## 4. Remaining frozen seams in Slice 3 (must not be inferred yet)

This slice **does not** create placeholder importable stubs for the following. Core #236 Slice 3 will append concrete public Python signatures and exact result/error semantics before #239–#242 implement any of them:

- caller-owned active context, opaque return token, process-bound return, revalidation statuses after Notes/admin utilities;
- Core Notes & Tasks menu public service invocation, Core's stable private workspace/owner association, and cancellation/failure outcomes;
- shared in-process Workspace & Classroom Management invocation, injected streams and structured changes/revalidation signals;
- service/CLI/menu parity, partial-commit reporting, privacy and private backup/transfer contract seams.

Those seams must **not** infer student identity from context, treat navigation as an authorization proof, claim a cross-producer transaction, or change Core's current workspace/roster/Standards ownership. Core #238 defines private storage and threat-model specifics; #241 defines guarded single-student mutation semantics. The v1 contract must never prescribe their schemas without their subsequent reviews.

## 5. Downstream obligations and evidence

| Owner / issue | Implementation responsibility | Release-qualified proof still needed |
| --- | --- | --- |
| Core #237 | Implement `teacher_experience`, `teacher_ui`, `teacher_commands`; maintain existing navigation behavior | API/TTY/NO_COLOR/Windows fallback and collision tests |
| Core #238–#240 | Safe Notes owner/storage and records; guarded Notes menu plus explicit CLI | Private-store isolation, true capabilities and CLI/menu equivalence |
| Core #241–#242 | Guarded student edits; in-process classroom administration | Concurrency, confirmation, revalidation and authoritative roster parity |
| Core #243–#244 | Deliberate private Notes portability; integrated release/installed qualification | Backup exclusions, portability, consumer matrix, installed-wheel checks |
| Suite #51 / #15 | Adopt/qualify Suite-owned design; consume public Core contracts in teacher home | Feature-availability truthfulness and direct-CLI parity |
| ScoreForm / Quillan / Concord / Meridian / Vitrine / Portia | Adopt approved header and safe menu-choice parser at audited prompts | Each producer's collision census, context-return tests and installed distribution acceptance |

**References:** [Core #235](https://github.com/Paper-Data-Suite/pds-core/issues/235), [Core #236](https://github.com/Paper-Data-Suite/pds-core/issues/236), [Core #237](https://github.com/Paper-Data-Suite/pds-core/issues/237), [Suite #51](https://github.com/Paper-Data-Suite/pds-paper-data-suite/issues/51), [Suite #49](https://github.com/Paper-Data-Suite/pds-paper-data-suite/issues/49).
