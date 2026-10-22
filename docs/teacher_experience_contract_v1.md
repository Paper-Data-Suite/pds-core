# Core Teacher-Experience Interface Contract v1

**Contract ID:** `pds_core.teacher_experience/1`

**Status:** Proposed Core #236 contract freeze (Slices 2â€“3); not implemented or release-qualified

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

## 4. Planned v1 return/context and in-process shared-menu contract — exact public shapes

> **Specified only.** The names below are design-frozen targets in `pds_core.teacher_context` and `pds_core.teacher_menus`; **none** is an importable Core 0.6.6 API. Runtime implementation, private-service design and installed-consumer qualification belong to Core #238–#244. This section supplements, and does not supersede, the header/command contract in §2.

### 4.1 `pds_core.teacher_context`: caller hints, not authority

```python
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

@dataclass(frozen=True, slots=True)
class TeacherWorkReference:
    module_id: str            # installed component label is not trust evidence
    work_kind: str            # e.g. "assignment", "activity", "portfolio"
    work_id: str              # exact opaque non-student work reference

@dataclass(frozen=True, slots=True)
class TeacherContextHint:
    workspace_root: Path | None = None
    class_id: str | None = None
    work: TeacherWorkReference | None = None
    display_label: str | None = None

@dataclass(frozen=True, slots=True)
class SharedTeacherMenuRequest:
    caller_application: str
    return_token: str
    context: TeacherContextHint = field(default_factory=TeacherContextHint)
```

- `TeacherContextHint` is an **ephemeral, process-local navigation hint**. The workspace root is a path to resolve/check, **not** the stable Notes collection identifier, proof of ownership or a request to silently change workspace preferences. `class_id` and `work_id` are exact references, never fuzzy name matches. The caller supplies a permitted display label only after its own currentness/access checks; Core cannot derive student names from a hint.
- `TeacherWorkReference` accepts only an **eligible non-student work object**. No student ID, student/submission selector, student-specific review, Grade, Score, scan payload, behavior-support case, credentials, record bodies or arbitrary serialized state may be placed here. Semantic suitability is **caller-owned** and must be checked again by Core before any Notes metadata is stored; basic string/type validation alone is not authorization.
- Context fields are optional. Invalidation is hierarchical: changing workspace invalidates class and work; changing class invalidates incompatible work; a stale/absent/unpermitted work reference cannot be used or guessed. Shared utilities may discard hints without preventing safe standalone operation. No automatic student association is allowed.
- `caller_application` is a nonblank presentation/routing identifier, not verified installed identity. `return_token` is a nonblank **opaque session-local** string generated and interpreted by the caller (maximum 128 Unicode code points, no control characters or line breaks); it is echoed exactly in the result. Do not place passwords, bearer credentials, serialized page state or student identifiers in a token. Neither Core nor Notes persists/logs this token. Core never executes a token as a command or resolves it as a filesystem path.
- All strings are checked for correct types, nonblank values where required and terminal controls; `workspace_root` must be a `Path` or `None`; nested dataclasses must be the declared types. Invalid request shapes raise `TypeError`/`ValueError` **before** an interactive prompt or durable mutation. No coercion from arbitrary producer objects. In particular the type constructor cannot be treated as authorization.

The **caller** holds its actual screen controller, local work selection and any safe in-memory draft. It is not passed into Core. A token promises at most return to that caller's still-live process and its own bounded navigation target. It does **not** promise restoring a nested screen after a subprocess or application restart. Suite foreground application launching is an independent qualified process boundary and must not invent a cross-process callback/transaction guarantee.

### 4.2 `pds_core.teacher_context`: orthogonal navigation, durability and revalidation results

```python
class TeacherMenuExit(str, Enum):
    BACK = "back"                    # B; return to the caller's saved boundary
    MAIN_MENU = "main_menu"          # M; caller decides its own main menu
    QUIT = "quit"                    # Q; caller owns final process exit
    CANCELLED = "cancelled"          # stopped/EOF/Ctrl-C at a safe boundary
    UNAVAILABLE = "unavailable"      # required Core capability not qualified
    FAILED = "failed"                # an operation failed; inspect durability

class TeacherDurability(str, Enum):
    NO_CHANGE = "no_change"          # no durable writes from this invocation
    COMMITTED = "committed"          # at least one confirmed change; all reported operations completed
    PARTIAL = "partial"              # some confirmed durable work, some not
    INDETERMINATE = "indeterminate"  # safety cannot establish complete write outcome

class TeacherChangeScope(str, Enum):
    WORKSPACE = "workspace"
    SCHOOL_YEAR = "school_year"
    CLASS = "class"
    ROSTER = "roster"
    STANDARDS = "standards"
    NOTES = "notes"

@dataclass(frozen=True, slots=True)
class SharedTeacherMenuResult:
    return_token: str
    exit: TeacherMenuExit
    durability: TeacherDurability
    change_scopes: frozenset[TeacherChangeScope]
    message: str
```

**Invariant and meaning:** `exit` is a **navigation/error disposition**; `durability` independently reports confirmed persistence and is never inferred from whether the teacher pressed `B`, `M`, or `Q`. A teacher may make a durable change and then return with `BACK` or `QUIT`; `CANCELLED` **after** earlier confirmed work must likewise retain a truthful `COMMITTED` or `PARTIAL` report. For `NO_CHANGE`, `change_scopes` must be empty. After `COMMITTED` or `PARTIAL`, each affected Core domain must appear in `change_scopes`. `INDETERMINATE` must conservatively enumerate plausible affected scopes and direct the teacher to authoritative inspection rather than claim rollback. `UNAVAILABLE` is `NO_CHANGE` for that utility invocation; opening a utility, displaying a header or recognizing a command never silently creates records.

`message` is concise, safe-to-display outcome text: what happened, what is known saved, and the safe next action. It must not include note bodies, student records, credentials, raw private exceptions, or opaque tokens. Canonical service-level error types/revision receipts remain owned by their implementing issues and must **not** be flattened away; this result summarizes a menu invocation, not an audit log or proof of transaction atomicity. An unavailable Notes service must not be represented as an empty Notes collection.

**Navigation mapping:** In the hosted shared-menu controller, `B` produces `BACK`, `M` produces `MAIN_MENU`, `Q` produces `QUIT`; the **caller** performs the corresponding navigation/exit. Existing `parse_navigation_choice` and its `M/Q` exceptions remain unchanged for existing menus: an implementation may catch them **at its own shared-menu boundary** solely to construct this result and must not swallow an unrelated module's unwind. Plain noninteractive `pds-core` command exit codes are separate and remain meaningful to scripts. EOF/Ctrl-C before any write returns `CANCELLED`/`NO_CHANGE`; after a durable change, report it truthfully. A validation refusal before mutation is `FAILED`/`NO_CHANGE`, with the reason and safe remedy.

**Caller-owned revalidation is unconditional before consequential continuation**, even with `NO_CHANGE`: another process may have modified a roster, workspace, assignment, authorization, or revision while Notes was open. Inspect result scopes to prioritize refresh, but do not treat an empty scope set or a matching return token as an authorization or version proof. Core can validate its own workspace/class/roster state. The owning producer must separately reload its work item, student selection and private revision, recheck permission and discard/refresh incompatible local selections. A remembered teacher name or display string never substitutes for exact identity/currentness.

### 4.3 `pds_core.teacher_menus`: callable, bounded in-process entry points

```python
from collections.abc import Callable
from typing import TextIO
from pds_core.teacher_context import SharedTeacherMenuRequest, SharedTeacherMenuResult

def run_notes_tasks_menu(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    interactive: bool,
    error_output: TextIO | None = None,
) -> SharedTeacherMenuResult: ...

def run_workspace_classroom_menu(
    request: SharedTeacherMenuRequest,
    *,
    read_line: Callable[[], str],
    output: TextIO,
    interactive: bool,
    error_output: TextIO | None = None,
) -> SharedTeacherMenuResult: ...
```

Both are **public in-process** Core menu boundaries. `read_line` is injected and takes **no arguments**: Core writes the full prompt to the supplied output stream, flushes it when a response is needed, then reads one line. A producer need not surrender its global `input`, `sys.stdin`, `sys.stdout`, clear-screen helper, session loop, or logging configuration. Tests can inject an iterator-backed `read_line` and `StringIO` streams. `error_output=None` means sanitized failures go to `output`; non-`None` directs sanitized diagnostics there, never secrets. `interactive=False` returns `UNAVAILABLE`/`NO_CHANGE` without calling `read_line`, opening a prompt or mutating private/canonical data. The caller must set `interactive=True` only for a qualified active interactive session (test injection is allowed); this parameter does not grant teacher identity, workspace access or security rights.

Core implementations must obtain **Core-owned, validated services** through their public/service boundaries (including the owner/workspace protection designed in #238 and guarded roster operations in #241); caller-injected I/O is **not** injected authority. Test service substitutes must be wired by the Core implementation under its own test contracts and may not become an undocumented consumer dependency. Importing these functions must not read a workspace, instantiate records, prompt or change global terminal state. These functions do not run `subprocess.run("core")`, call a private Core menu class or import any producer/Suite module.

`run_notes_tasks_menu` becomes callable only when **`notes.menu.v1` and required `notes.records.v1` are qualified** for the installed distribution and current OS-user/workspace association. `run_workspace_classroom_menu` becomes callable only with **`classroom.menu.v1`**, including qualified guarded edit operations before exposing individual-student mutations. A Core implementation may expose the API symbol earlier but must return an honest `UNAVAILABLE` result rather than display unsupported operations. Merely having `terminal.notes_command.v1` or a displayable `Notes & Tasks` label is never sufficient. Each producer and Suite caller separately qualifies its own safe handoff.

The menus own normal Core prompts and Core-side validation, not the caller's producer-specific academic data or screen controller. The Core menu and standalone `core`/`pds-core` menu entry points should compose the **same guarded Core services**, not create a second implementation of workspace, roster, Standards or Notes semantics. The first qualified admin menu covers workspace/year/class/roster/Standards through existing Core authority; roster adds/edits/removals require #241's reviewed preview/commit/freshness checks. Any menu action that is only read-only remains read-only. No automatic rewrite or regeneration of producer-owned artifacts after a roster update.

### 4.4 Caller handoff/resumption, failure and nested navigation

1. The initiating producer first validates its workspace/class/work revision and decides that the current menu-choice prompt is safe. It obtains qualified Core capabilities, creates a short opaque return token for **its own** in-memory continuation, and calls the public Core menu with only minimal permitted hints.
2. It records how any **uncommitted** local draft will be handled: retained in caller memory if safe, or disclosed as **not preserved** before leaving the screen. **Confirmed durable producer work is never discarded** merely by visiting a shared utility.
3. Core owns the utility operation. Every consequential write uses its own authoritative preview/confirmation/guarded commit; cancellation before that decision makes no new canonical work. Later partial changes remain real and are truthfully reported. A Core result cannot make a producer revision current, nor does it roll back producer state.
4. On return, the caller checks that the token belongs to its still-live session. It then **reloads** workspace and school year; validates class and roster; reloads the module work item, any selected student, current revision and permission before consequential continuation; and invalidates subordinate selections after switches. If scope hints are insufficient, **revalidate broadly**.
5. If the initiating work is stale, missing, moved, ambiguous or unauthorized, the caller presents a bounded refresh/reselect/safe-return path. It must not silently reuse the old submission, student, roster revision or saved authorization. A return result is information, not a command to perform a producer write.
6. `MAIN_MENU` means the **caller's** main menu. `QUIT` asks the caller to perform its own appropriate shutdown/unwind. The shared Core menu cannot change Suite foreground process-launching guarantees or restore a suspended subprocess by itself.

### 4.5 Private Notes custody and service boundary (Core #238–#240, #243)

- The Core Notes record service is a **single logical collection associated with one PDS workspace and scoped to the qualified local OS user/owner**. Initial categories are **Idea / Task / Reflection**. Core #238 must first choose a stable workspace association across moved/copied/renamed workspaces; the existing workspace marker is not silently promoted into a stable private-store UUID. The caller's `workspace_root` and `caller_application` hints cannot establish ownership.
- Initial private note bodies reside in an **OS-user-protected application-data location**, not the ordinary shared classroom workspace. Protection, effective owner derivation, read/write isolation and limits for shared OS logins require #238 tests and an explicit threat model. Self-declared `actor_reference` is attribution only. No guarantee of multi-user/shared-login security, cloud synchronization or end-to-end encryption is made here.
- Automatic Notes context may carry an eligible **validated module/class/non-student work reference only**. It must not persist a structured student identifier or student-linked work, scans, Grades, Scores, review evidence, Portia support case or private producer data in context metadata. Teacher-authored free text may itself contain personal information; it remains protected private data and is never copied into diagnostics or classroom exports by default.
- Opening a menu or starting a quick capture does not write a Note. Recording an entry requires a Core-authorized explicit save and guarded update/revision semantics. Producer student-specific notes remain in the producer. A personal Task/due date is **not** a notification, producer attention warning, academic decision, delivered response, Grade or published record. No automatic producer mutation or PDS2/registry publication is allowed.
- Normal Core/Suite whole-workspace backup/restore does **not** include the external teacher-private Notes store. Core #243 owns explicit, owner-reviewed export/transfer/backup/restore with conflict rules and truthful receipts. A failed/partial portability operation cannot be disguised as a complete workspace backup.

### 4.6 Direct-CLI parity and supported-adoption boundary

For **each meaningful Core-owned durable action** exposed via shared menus, the implementation issue must supply an explicit script-safe, noninteractive `pds-core` invocation of the **same guarded Core service** with equivalent validation, access scope, stale-revision handling and useful exit status. Existing `pds-core roster import-preview`/`import-commit` and other direct commands retain their prior public spelling. The planned Notes command family is rooted at `pds-core notes` (#240), with distinct create, read/search, update/status and archive operations; #243 adds qualified portability. The eventual exact argument names, data formats and flags remain **owned by the corresponding implementation issue** and cannot be claimed available under #236. Guarded single-student roster operations under #241 similarly need CLI parity before #242 exposes them in a menu; no duplicate Core roster database is permitted.

The `:notes` token is **not** a new shell alias, argument value, global CLI parser intercept, or unattended data-entry escape sequence. Pure menu navigation, help, display and return paths require **no invented CLI mutation**. No routine menu call or import may cause a non-TTY session to wait for input or silently write anything. The Suite `pds` executable and separate Suite #49 installed-trust/launch/update qualification are unchanged by this interface freeze.

### 4.7 Synthetic successful journey: Quillan review → Notes → Quillan review

1. Quillan is reviewing a *fictional* English 12 assignment, with local student selection, exact submission revision and a confirmed review previously saved. Its next prompt is a declared `MENU_CHOICE`, with `N` = Next Student and `W` = Next Student Needing Review. It has verified `terminal.notes_command.v1`, `notes.menu.v1` and `notes.records.v1` **and consumer-level qualification**.
2. Teacher enters ` :NoTeS `; only the pure shared parser returns `SharedTeacherCommand.NOTES`. Quillan retains its private submission/student identity **locally**, not in `TeacherContextHint`. It calls `run_notes_tasks_menu` with a fresh caller-local return token and, at most, the permitted class and assignment reference.
3. Core resolves its own qualified OS-user/workspace Notes scope, receives **Task** plus teacher-entered text, previews/guards and saves a personal Task. Its result contains `exit=BACK`, `durability=COMMITTED`, `change_scopes={NOTES}` and the same opaque return token. The Task has **not** altered Quillan review, student work, a Grade, or a module attention item.
4. Quillan checks the token and **reloads** workspace, roster, assignment, exact student/submission/revision and permissions. If all are current, it restores its screen and N/W behavior; it did not discard its previously confirmed work. No new Quillan write occurs just because Core returned.
5. **Stale variation:** while Core was open, another process revises or removes the assignment/submission. Quillan refuses to continue on a stale selection and offers refresh/reselection/safe return. The saved personal Task remains saved; the Quillan workflow does not silently roll it back or impersonate the old submission revision.

### 4.8 Synthetic successful and conflict journeys: caller → Core classroom administration → caller

1. From Suite or a fictional ScoreForm main menu, the teacher invokes `run_workspace_classroom_menu` using a local return token and an optional workspace/class hint, **after** #241–#242 qualify the guarded services and consuming menu. Core shows the same authoritative workspace/class/roster/Standards options as its own menu.
2. Teacher previews an individual roster update. Core verifies exact student/class identity and freshness, obtains meaningful confirmation, and commits using the guarded Core roster service. The returned `BACK` result has `durability=COMMITTED` and `change_scopes={ROSTER}` (plus another scope if actually changed).
3. The caller reloads Core workspace/class/roster and its **own** active work and student context before resuming. If the selected student was removed/changed or a prepared assessment references an outdated roster, caller offers refresh/reselect; no implicit regenerated pages, changed student assignment or producer write occurs.
4. **Workspace-switch variation:** Core changes the selected workspace. Result includes `change_scopes={WORKSPACE}`. On return the caller invalidates class, roster, selected assignment and student context and requires fresh resolution. An old class ID from the previous workspace cannot be carried forward, even if its display name matches.
5. **Conflict/partial variation:** another process changes a roster after preview. The guarded commit refuses as stale: `FAILED`/`NO_CHANGE`, with refresh/review advice. If separate, explicitly authorized operations had already committed before a later failure, use `FAILED`/`PARTIAL`, list known changed scopes and show exactly what persisted; there is **no** cross-repository atomicity claim.

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
