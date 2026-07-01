# Shared Standards Library and Usage Contract

## Purpose

This document defines the shared Paper Data Suite contract for a standards
library and standards-usage tracking.

For the practical module integration guide covering `pds-quillan`,
`pds-scoreform`, future modules, durable ID storage, teacher-facing display,
and missing/deprecated standards behavior, see
[`module_standards_integration.md`](module_standards_integration.md).
For the smoke-tested standards management workflow across CLI commands,
teacher menus, import/export, and module-facing selection APIs, see
[`standards_management_workflow.md`](standards_management_workflow.md).
For optional bundled starter standards packs, see
[`starter_standards.md`](starter_standards.md).

The central architecture decision is:

```text
pds-core owns shared standards library workspace-storage behavior and the
standards usage ledger file contracts.
Modules own module-specific standards behavior and interpretation.
```

For module integration, this means `pds-core` is the canonical source of truth
for Paper Data Suite standards definitions, reusable standards profiles,
workspace standards storage, module-neutral browsing/filtering helpers, and
module-neutral standards usage events. ScoreForm, Quillan, and future modules
must not create independent standards universes that teachers have to maintain
separately.

Machine-readable module data should store shared `standard_id` values, not
display `code` values. User-facing module screens and reports may show
`code`, `short_name`, `description`, domain, grade band, source, and other
descriptive metadata from the shared library. `code` is not durable enough to
serve as the internal key because codes may be reformatted, duplicated across
sources, or reused across jurisdictions.

A module assignment that uses shared standards should follow this pattern:

```json
{
  "standards_profile_id": "nj_ela_2023_11_12",
  "focus_standards": [
    "nj_ela_2023_rl_cr_11_12_1",
    "nj_ela_2023_w_aw_11_12_1"
  ]
}
```

The selected `standards_profile_id` must exist in the workspace standards
library. When `focus_standards` is present, each entry should be a known
`standard_id`; when an assignment supplies both fields, the focus standards
should normally be a subset of the selected profile. PDS Core provides a
module-neutral `validate_profile_standard_selection(...)` helper for that
profile-plus-focus validation.

This document began as a design contract. Focused implementation issues have
since added shared standards models, JSON-compatible conversion helpers,
explicit-path JSON file helpers, the canonical workspace library path, and a
shared in-memory usage event model with JSON-compatible dictionary conversion
and explicit-path JSON Lines file helpers. Canonical workspace usage-ledger
paths and convenience helpers are also implemented, along with read-only
usage summary helpers. PDS Core also owns shared active school-year workspace
state so modules can use one selected school year when recording usage events.
The workspace standards library convenience loader returns an empty library
when `<PDS workspace root>/standards/library.json` is missing, and that missing
load does not create files or directories. PDS Core also provides read-only
standards browsing and filtering helpers over existing in-memory
`StandardsLibrary` objects.
CLI commands, migrations, module adapters, and
automated educational judgment remain future work unless explicitly added by
later issues.

## Design Principles

The standards subsystem should be:

* local-first and usable without a network service;
* teacher-controlled;
* shared across Paper Data Suite modules without coupling those modules to
  each other;
* explicit about durable definitions versus year-specific usage;
* conservative about shared vocabulary;
* compatible with module-specific assignment models;
* auditable without treating stored metadata as educational judgment;
* designed so future schema changes can be versioned and migrated
  deliberately.

Teacher judgment remains primary. Shared standards infrastructure may store,
organize, validate, filter, and report teacher-controlled records. It must not
perform AI grading, automatic standards judgment, automatic feedback,
automatic scoring, or automatic determination that a student met or missed a
standard.

The dependency direction remains:

```text
pds-scoreform -> pds-core
pds-quillan   -> pds-core
```

ScoreForm and Quillan must not depend on each other.

## Existing Module Behavior

### ScoreForm

ScoreForm currently supports assignment-local standards alignment in
`assignment.json`.

Current behavior:

* `assignment.json` may include a `standards` object;
* the object is keyed by question number;
* each value must be a list;
* each listed standard must be a non-empty string;
* missing question keys are allowed;
* empty lists are allowed;
* assignment creation initializes every question with an empty standards
  list.

Approximate current shape:

```json
{
  "assignment_id": "rj_act1_quiz",
  "title": "Romeo and Juliet Act 1 Quiz",
  "question_count": 10,
  "choices": ["A", "B", "C", "D"],
  "answer_key": {
    "1": "A",
    "2": "C"
  },
  "standards": {
    "1": ["RL.CR.11-12.1"],
    "2": [],
    "3": ["L.VI.11-12.4"]
  }
}
```

This alignment associates questions with standard codes. It does not by
itself create a shared standard definition, record a usage event, or determine
whether a student met a standard.

ScoreForm continues to own:

* answer keys;
* choices;
* question counts;
* the ScoreForm assignment JSON format;
* OMR scoring;
* question-level standards alignment behavior;
* ScoreForm result exports.

### Quillan

Quillan currently has a more developed standards profile concept. Its profile
data may include:

* `profile_id`;
* `subject`;
* `course`;
* `standards`;
* standard `code`;
* standard `short_name`;
* standard `description`;
* standard `comments`;
* comment `comment_id`;
* comment `label`;
* comment `polarity`;
* optional `severity_default`;
* optional `feedback_template`;
* optional `subskills`;
* optional `hotwords`.

Quillan assignment configs reference standards through:

* `standards_profile_id`;
* `tagging_mode`;
* `focus_standards`.

Quillan tag records connect teacher-reviewed writing evidence to:

* `standard_code`;
* `comment_id`;
* `label`;
* `polarity`.

Quillan continues to own:

* writing assignment configuration;
* tagging modes;
* focus standards behavior;
* teacher tags;
* teacher comments;
* teacher notes;
* teacher-entered or teacher-confirmed scores;
* feedback records;
* writing reports;
* Quillan-specific interpretation of comments, `hotwords`, `subskills`,
  polarity, severity defaults, feedback templates, and review metadata.

Those richer fields must not be generalized into `pds-core` merely because
they are standards-adjacent.

## Core/Module Ownership Boundary

`pds-core` should eventually own shared, module-neutral concepts:

* durable standard identity;
* durable standard definitions;
* reusable standards profiles;
* module availability metadata;
* shared storage locations and file contracts;
* usage-event identity and common fields;
* canonical shared usage types;
* class/year usage scoping;
* module-neutral loading, validation, and reporting contracts.

Assignment modules continue to own:

* their assignment schemas;
* how standards are selected or displayed in assignment workflows;
* how assignments align to standards;
* module-specific tagging and review records;
* scoring and feedback behavior;
* module-specific exports and reports;
* interpretation of any namespaced extension metadata.

This mirrors the existing assignment-folder boundary:

```text
pds-core owns where assignment folders live.
Modules own what assignments mean.
```

For standards:

```text
pds-core owns shared standards identity, storage, availability, and usage
tracking.
Modules own what standards mean inside their assignment workflows.
```

The roster and workspace contracts remain relevant because usage records refer
to shared class and assignment identifiers. See
[`roster_workspace_contract.md`](roster_workspace_contract.md).

Module-facing standards selection, editing, browsing, creation, import, and
attachment workflows remain future work for focused module or suite issues.

## Why Standards Begin in `pds-core`

Standards should begin in `pds-core` because:

* standards are suite-level educational metadata;
* the same standard may be used by multiple modules;
* standards interact with classes, assignments, rosters, reporting, and
  workspace storage;
* `pds-core` already owns shared identifiers and workspace layout;
* a common owner prevents ScoreForm and Quillan from developing incompatible
  definitions and usage ledgers;
* a separate `pds-standards` package would add packaging, dependency, and
  versioning complexity before the boundary is proven.

Future extraction into a separate package may be considered if the standards
subsystem becomes large enough to need independent releases, dependencies, or
versioning. Extraction is not justified by the current design alone.

## Proposed Storage Direction

Standards should be stored under the resolved Paper Data Suite workspace, not
inside an installed package or source checkout.

The canonical shared standards library location is:

```text
<PDS workspace root>/standards/library.json
```

The `standards/` directory is suite-level shared metadata. The library is not
class-specific, school-year-specific, assignment-specific, or module-specific.

The current implemented standards storage commitments are:

```text
<PDS workspace root>/
  standards/
    library.json
    usage/
      <school_year>/
        <class_id>/
          events.jsonl
```

The shared library file at `standards/library.json` stores durable reusable
standard definitions and reusable standards profiles. Loading a missing
workspace standards library returns an empty `StandardsLibrary` and does not
create `standards/`, `library.json`, usage ledgers, settings, class folders,
assignment folders, reports, rosters, or module-specific folders. Writing the
workspace standards library creates only the `standards/` parent directory and
`standards/library.json`.

Usage events remain separate from definitions and profiles. Creating or
writing the standards library does not create standards usage ledgers and does
not record usage.

Installing starter standards is also library setup, not usage. Starter
installation may merge shared definitions and profiles into
`standards/library.json`, but it must not create usage ledgers or
module-specific files.

`settings/school_year.json` stores the suite-level active school-year state
owned by `pds-core`. It records the currently opened school year, when it was
opened, and an optional close timestamp. A closed state preserves the last
school year for auditability while making the active school year unavailable
to callers.

`standards/library.json` and
`standards/usage/<school_year>/<class_id>/events.jsonl` are current storage
commitments. A future profile path such as
`standards/profiles/<profile_id>.json` remains directional future work, not a
final file-format commitment.

The durable library and reusable profiles must be separate from the
school-year usage ledger. Shared usage data should not be embedded only in
module assignment folders because it must support cross-assignment,
cross-module, class-specific, and historical reporting.

Whatever storage shape is chosen, it should support efficient browsing by
source, subject, domain, strand, category, or `category_path` without requiring
modules to duplicate the standards taxonomy in their own files.

Storage should remain:

* local-first;
* inspectable and exportable;
* writable through explicit APIs;
* protected from accidental overwrite where practical;
* versioned at the schema level before migrations are introduced;
* independent of the current working directory.

Standard codes must not be interpolated directly into file paths. Profiles and
usage partitions may use existing safe `profile_id`, `school_year`, and
`class_id` path rules after their exact validation contracts are defined.

## Shared Concept: Standard Definition

A standard definition is a durable description of an educational standard. It
does not reset at the end of a school year.

An illustrative record is:

```json
{
  "standard_id": "njsls-ela:RL.CR.11-12.1",
  "code": "RL.CR.11-12.1",
  "source": "NJSLS-ELA",
  "grade_band": "11-12",
  "subject": "English Language Arts",
  "course": "English 12",
  "domain": "Reading Literature",
  "category_path": [
    "English Language Arts",
    "Reading Literature",
    "Close Reading"
  ],
  "short_name": "Close Reading Evidence",
  "description": "Cite strong and thorough textual evidence...",
  "tags": ["close_reading", "textual_evidence"],
  "active": true,
  "available_modules": ["pds-scoreform", "pds-quillan"]
}
```

This is not a final schema. At minimum, implementation should distinguish:

* stable suite identity;
* the source's public/display code;
* source or issuing authority;
* teacher-facing descriptive metadata;
* navigation and grouping metadata;
* active or retired status;
* module availability.

Shared standard definitions should preserve enough grouping metadata for
efficient teacher-facing menus. Teachers may need to move quickly across
multiple standards sets and subjects, then narrow to a subdivision such as
domain, strand, concept, practice, cluster, category, or other source-defined
grouping.

The shared contract should support menu paths such as:

```text
English Language Arts
  Reading Literature
    RL.CR.11-12.1 - Close Reading Evidence

English Language Arts
  Reading Informational Text
    RI.CR.11-12.1 - Informational Text Evidence

Computer Science
  Algorithms and Programming
    AP-AL-01 - Algorithm Design

Career Readiness / Life Literacies
  Digital Citizenship
    9.4.12.DC.1 - Digital Identity
```

These grouping fields are for navigation, filtering, reporting, and faster
assignment construction. They should not determine scoring, mastery, feedback,
or module-specific interpretation.

Deactivating or replacing a definition must not erase historical usage.
Changes to official wording, source editions, and local corrections require an
explicit versioning or revision policy before implementation.

## Standard Code and Identifier Strategy

Official standard codes are source and display identifiers first. They must be
preserved without forcing them through the route identifier rules used for
`class_id`, `assignment_id`, or `student_id`.

Codes such as:

```text
RL.CR.11-12.1
W.AW.11-12.1
```

contain punctuation and grade-band notation that are legitimate in the
educational source. Replacing that punctuation for display would lose fidelity,
while treating the code as a path component would couple identity to filesystem
rules.

The proposed identity split is:

* `code` stores the exact official or teacher-facing code;
* `source` identifies the authority or local collection that issued the code;
* `standard_id` is the stable suite-level reference used by profiles and usage
  events;
* `standard_id` is a logical identifier, not a route or filename;
* a separate storage-safe key may be introduced only if a storage backend
  requires per-record filenames.

A namespaced logical ID such as
`njsls-ela:RL.CR.11-12.1` illustrates the intended separation. The exact
namespace and generation rules must be settled before implementation.
Uniqueness cannot rely on `code` alone because different sources may publish
the same code.

Teacher-defined standards should use a local source namespace and a stable
teacher-controlled or generated identity. They should not imitate an official
source code in a way that obscures provenance.

Storage-safe keys, if needed, must be generated without lossy ad hoc
normalization. They are implementation details and must not replace the
official code in teacher-facing output.

## Menu Navigation and Grouping Strategy

Shared standards records should support fast teacher-facing navigation across
multiple standards sets.

A teacher may need to access standards from different subjects or frameworks
in the same workspace. For example, one teacher may need English Language Arts
standards, Computer Science standards, and Career Readiness / Life Literacies
standards. Another teacher may need local department skills or rubric-aligned
course criteria.

The shared contract should support a general navigation pattern:

```text
standards set or subject
  source-defined subdivision
    individual standard
```

The middle level should not be hard-coded to one subject area's terminology.
Different standards sets may use different grouping names, such as:

* domain;
* strand;
* concept;
* practice;
* cluster;
* category;
* topic;
* performance expectation.

For that reason, implementations should preserve source-specific grouping
metadata and may also expose a generic ordered `category_path` or equivalent
menu path.

Examples:

```text
English Language Arts
  Reading Literature
    RL.CR.11-12.1 - Close Reading Evidence

English Language Arts
  Reading Informational Text
    RI.CR.11-12.1 - Informational Text Evidence

Computer Science
  Algorithms and Programming
    AP-AL-01 - Algorithm Design

Career Readiness / Life Literacies
  Digital Citizenship
    9.4.12.DC.1 - Digital Identity

Local Writing Rubric
  Evidence and Reasoning
    evidence_explanation - Evidence Explanation
```

This menu structure is a navigation aid, not a scoring model. Modules such as
ScoreForm and Quillan may present these groupings in their own interfaces, but
the grouping itself must not imply that software can judge mastery, generate
feedback, or calculate scores.

The shared library should make it possible for modules to filter or browse
standards efficiently without each module inventing a separate standards
taxonomy.

Implemented browsing helpers operate only on an existing in-memory
`StandardsLibrary`. They can find a standard by `standard_id`, filter
standards by subject, source, domain, active status, available module, and
category-path prefix, and list available subjects, sources, domains, and
category paths. They preserve library order for filtered standards and return
deterministically sorted tuples for list views.

These helpers are side-effect free. They do not read files, write files,
create directories, create standards, edit standards, delete standards, import
standards, migrate data, inspect workspace state, or record standards usage.
Modules may use them to build teacher-facing standards selection workflows,
but modules still own their own UI, CLI, assignment schemas, selection flows,
assignment attachment behavior, and standards interpretation.

Implemented mutation helpers also operate only on an existing in-memory
`StandardsLibrary`. They can add, replace, or upsert a
`StandardDefinition`, and add, replace, or upsert a `StandardsProfile`. Each
helper returns a new `StandardsLibrary`, preserves predictable ordering,
validates the requested input, and validates the resulting library. These
helpers do not read files, write files, create directories, inspect workspace
state, record standards usage, add module UI, or alter assignment behavior.

Delete and remove helpers are intentionally out of scope until profile
references, historical usage events, inactive standards, auditability, and
migration policy are resolved. A standard can be retired without deleting it
by replacing its definition with `active` set to `false`.

## Shared Concept: Standards Profile

A standards profile is a reusable grouping of shared standard definitions.

Illustrative shape:

```json
{
  "profile_id": "english_12_njsls",
  "subject": "English Language Arts",
  "course": "English 12",
  "source": "NJSLS-ELA",
  "standards": [
    "njsls-ela:RL.CR.11-12.1",
    "njsls-ela:W.AW.11-12.1"
  ]
}
```

Profiles should contain references to shared definitions rather than duplicate
full standard records. This allows one corrected definition to remain
consistent across profiles and modules.

Modules may reference a shared profile by `profile_id` and may select a
smaller set of focus standards from that profile for a specific assignment or
workflow. The profile remains reusable shared library data; the assignment's
focus list remains module-owned assignment data.

Profiles may provide useful grouping metadata, but they must not become
assignment schemas. Modules decide how a profile is selected, filtered, and
used in an assignment workflow.

Implemented profile browsing helpers operate on `StandardsLibrary.profiles`.
They can find a profile by `profile_id` and filter profiles by subject,
course, and source while preserving the profile order stored in the library.
They do not add active status, module availability, assignment behavior, or
usage recording to profiles.

The implemented `validate_profile_standard_selection(...)` helper checks that
a profile exists, selected standard IDs exist in the library, selected IDs
belong to the selected profile, and selected IDs are not duplicated. It trims
and returns the selected IDs as a tuple. It does not read or write workspace
files, change assignment schemas, create standards, record usage, or decide
which standards a teacher should choose.

Profile versioning, ordering, local overrides, and behavior when a referenced
standard becomes inactive must be resolved before implementation.

## Module Availability

A standard may include module availability metadata:

```json
{
  "available_modules": ["pds-scoreform", "pds-quillan"]
}
```

Availability is filtering and workflow metadata. It may help a module show
only relevant standards or reject an accidental unsupported selection.

Availability is not:

* a security boundary;
* an authorization system;
* a guarantee that a module implements every possible workflow for the
  standard;
* permission to interpret another module's extension data.

An empty or missing availability list needs an explicit meaning before
implementation. The contract should choose either "available everywhere" or
"availability unspecified" and must not silently alternate between them.

## Module Extensions

Some metadata is useful only to one module. Namespaced extensions remain a
design option:

```json
{
  "standard_id": "njsls-ela:W.AW.11-12.1",
  "module_extensions": {
    "pds-quillan": {
      "comments": [
        {
          "comment_id": "evidence_needs_explanation",
          "label": "Evidence needs more explanation",
          "polarity": "developing",
          "severity_default": 2,
          "feedback_template": "Explain how the evidence supports the claim.",
          "subskills": ["reasoning", "evidence_explanation"],
          "hotwords": ["quote", "example", "this shows"]
        }
      ]
    },
    "pds-scoreform": {
      "default_alignment_notes": []
    }
  }
}
```

This example is not an implementation commitment. The core principle is:

```text
pds-core may eventually store namespaced module-extension data, but modules
validate and interpret their own extension schemas.
```

Core should preserve unknown namespaced data when a future storage contract
requires round trips, but it should not assign shared meaning to that data.
Quillan comments, polarity, severity defaults, feedback templates, subskills,
and hotwords remain Quillan-owned unless a later issue deliberately defines a
migration and namespaced extension contract.

The following do not belong directly on `StandardDefinition`:

* Quillan feedback comments or default comment banks;
* Quillan hotwords, severity defaults, subskills, or feedback templates;
* ScoreForm question templates or distractor guidance;
* AI-generated feedback language;
* grading, scoring, mastery, or proficiency rules.

Module-specific extension data should be keyed by shared `standard_id` in
module-owned storage or a later namespaced extension contract. A possible
future workspace layout is:

```text
<workspace root>/standards/library.json
<workspace root>/standards/extensions/quillan/...
<workspace root>/standards/extensions/scoreform/...
```

That extension storage layout is not implemented by this contract.

## Shared Concept: Usage Event

A usage event is separate from a standard definition. It records that a
teacher-controlled workflow marked a standard as taught, practiced, assessed,
or reviewed in a particular context.

Illustrative shape:

```json
{
  "event_id": "evt_2026_000001",
  "standard_id": "njsls-ela:RL.CR.11-12.1",
  "school_year": "2026-2027",
  "class_id": "english12_p3",
  "module": "pds-scoreform",
  "assignment_id": "villainy_final_exam",
  "usage_type": "assessed",
  "used_at": "2026-06-14T10:00:00-04:00",
  "metadata": {
    "question_numbers": [1, 3, 5]
  }
}
```

`StandardUsageEvent` now provides this shared shape in memory, with `used_at`
represented as a timezone-aware `datetime`. It converts to and from a
JSON-compatible dictionary with `used_at` represented as an ISO datetime
string. Explicit-path helpers load, append, and atomically write UTF-8 JSON
Lines files with one usage event object per nonblank line. Workspace helpers
construct, create, load, append, and atomically write the canonical
class/year-scoped usage ledger path.

Usage summaries are derived views over recorded usage events. They may count
events by standard, usage type, module, and assignment context. They do not
represent mastery, grades, scores, proficiency, feedback, or automatic
educational judgment.

A usage event:

* references a durable standard definition;
* belongs to one school-year and class scope;
* records the module and, when applicable, assignment context;
* may carry module-specific metadata;
* does not contain a mastery judgment;
* does not replace the module's assignment-level alignment data.

Assignment alignment and usage are related but distinct. The presence of a
standard in a ScoreForm question map or Quillan focus list must not silently
create historical usage during migration. Any backfill should require an
explicit migration policy and teacher-visible confirmation.

Module-level workflows should eventually record standards activity through
`StandardUsageEvent` when a teacher-controlled action uses a standard. Examples
include a ScoreForm question assessing a standard, a Quillan review tag or
comment referencing a standard, a teacher selecting a focus standard for an
assignment, or a standards-aligned export/report summarizing use. Wiring those
events belongs in module implementation tickets, not this core contract issue.

Implementation must define correction behavior. Prefer preserving an audit
trail through replacement, superseding, or voiding rather than silently
rewriting historical events.

## Usage-Type Vocabulary

The initial canonical shared vocabulary should be limited to:

```text
taught
practiced
assessed
reviewed
```

These values describe instructional use, not student performance:

* `taught` records direct instruction;
* `practiced` records student practice;
* `assessed` records an assessment opportunity aligned to the standard;
* `reviewed` records an instructional revisit or review.

None of these values means that a standard was met, mastered, missed, passed,
or failed.

Possible later terms include:

```text
introduced
reteach
spiral_review
benchmark
intervention
```

Those should remain module-specific metadata or future vocabulary proposals
until their semantics are stable across modules. Modules may add detail in
namespaced metadata, but they must not emit an unregistered value as though it
were a canonical shared usage type.

## Class/Year Usage State

Usage state is scoped by:

```text
school_year
class_id
module
assignment_id
usage_type
```

and by the referenced `standard_id`.

This allows a teacher to:

* preserve one standards library across years;
* start a new school year with fresh usage counts;
* view prior-year usage without mixing it into current-year summaries;
* track the same standard independently for different classes;
* distinguish module and assignment contexts;
* summarize usage without deleting source events.

`assignment_id` is optional in the shared in-memory model so non-assignment
instructional use does not require a fake assignment identity. Modules remain
responsible for supplying assignment context when an event is assignment
backed.

Usage summaries should be derived views, not the only stored record. A count
must remain explainable in terms of its underlying events.

The `school_year` format should be canonical, likely `YYYY-YYYY`, and validated
independently from general route identifiers.

## Active School-Year Workspace State

`pds-core` owns active school-year workspace state at:

```text
<PDS workspace root>/settings/school_year.json
```

Modules should use this shared state when they need the current school year for
standards usage events, rather than repeatedly asking teachers to enter the
same value across workflows. Teachers should only need to open or close a
school year once through future module or suite tooling.

The state file uses this shape:

```json
{
  "active_school_year": "2026-2027",
  "opened_at": "2026-08-28T09:00:00-04:00",
  "closed_at": null
}
```

Closing a school year sets `closed_at` and preserves `active_school_year` for
auditability. A closed state does not provide an active school year to callers.

Opening or closing a school year must not delete, archive, migrate, summarize,
report, or move data. It must not create standards usage ledgers, class
folders, assignment folders, rosters, reports, or module-specific files.

ScoreForm and Quillan CLI/menu workflows for opening, closing, selecting, or
displaying the active school year remain future module work. This contract
does not claim those commands already exist.

## Yearly Reset Semantics

A yearly reset means beginning a new school-year usage scope. It does not mean
deleting or recreating the standards library.

Starting a new year should:

* preserve standard definitions;
* preserve reusable profiles;
* preserve prior-year usage records;
* create or select a fresh school-year scope;
* produce current-year counts from only that scope unless a teacher requests a
  historical comparison.

Starting a new year must not:

* delete standard definitions;
* delete old usage events;
* mark old events as current;
* copy prior usage counts into the new year;
* infer that a standard was taught again;
* alter module assignment data.

Any future reset command should be explicit, non-destructive, and named to
reflect school-year rollover rather than data deletion.

## Migration Considerations

Migration should preserve current module behavior while introducing shared
references incrementally.

For ScoreForm:

* keep the existing `assignment.json` shape and question-number keys during the
  first migration phase;
* resolve listed strings to shared definitions without changing answer keys,
  scoring, exports, or assignment creation;
* continue allowing missing keys and empty lists;
* do not create usage events merely because an old assignment contains a
  standards map;
* use a compatibility adapter if shared IDs differ from current stored codes.

For Quillan:

* map reusable profile definitions to shared standard references without
  changing assignment config behavior;
* preserve `standards_profile_id`, `tagging_mode`, and `focus_standards`;
* preserve existing teacher tags and their standard/comment references;
* keep comments, labels, polarity, severity defaults, feedback templates,
  subskills, hotwords, and review metadata under Quillan ownership;
* do not flatten Quillan metadata into the shared standard definition;
* use a namespaced extension only after a separate extension contract exists.

Migration tools must be dry-run capable, preserve backups or source files, and
report unresolved codes and duplicate identities. Those requirements belong
to later implementation issues; no migration adapter is added by this
contract.

## Future Codex-Assisted Standards Ingestion

Future assisted ingestion should produce draft standards-library data, not
change the core standards model or mix module-specific feedback behavior into
`StandardDefinition`.

The intended high-level flow is:

1. A teacher or developer places official source documents in a standards
   source area.
2. Codex or another assisted workflow parses the official document.
3. The generated output becomes a draft `StandardsLibrary` JSON file.
4. PDS Core validation checks that generated library against the shared
   standards contract.
5. Human review and curation are required before treating the library as
   official or curated.
6. Module-specific starter packs, such as Quillan comment banks or ScoreForm
   alignment hints, may be generated separately and keyed by `standard_id`.

Generated standards data is untrusted until it has been validated and
human-reviewed. PDS Core validates and stores the shared standards contract;
Codex may help draft library data and module starter packs, but it does not
make those drafts authoritative.

A possible future source workspace is:

```text
standards_sources/
  nj/
    ela/
      2023/
        source/
          njsls_ela_2023.pdf
        generated/
          library.generated.json
        curated/
          library.json
        notes.md
```

If standards data later needs independent lifecycle management, a separate
`Paper-Data-Suite/pds-standards` repository can be reconsidered. This issue
does not create that repository, add standards-source trees, add official
standards documents, implement OCR, or implement an ingestion pipeline.

## v0.4.0 Standards Management Surface Audit

This section defines the standards management surface that later v0.4.0
implementation tickets should use. It is a design and contract inventory, not
an implementation of the CLI, teacher menu, import/export commands, mutation
commands, or module adapters.

### Existing Backend Inventory

Current `pds-core` standards backend capabilities are:

* model objects: implemented now through `StandardDefinition`,
  `StandardsProfile`, `StandardsLibrary`, `StandardUsageEvent`,
  `StandardUsageCounts`, and `StandardsUsageSummary`;
* validation helpers: implemented now for standard definitions, profiles,
  libraries, profile selections, usage events, usage counts, summaries,
  school years, and usage class IDs;
* JSON/dict conversion helpers: implemented now for standard definitions,
  standards profiles, full standards libraries, and usage events;
* explicit-path storage helpers: implemented now for UTF-8 deterministic
  standards library JSON loading and atomic writing, plus JSON Lines usage
  event loading, appending, and atomic writing;
* canonical workspace storage helpers: implemented now for
  `<PDS workspace root>/standards/library.json` and
  `<PDS workspace root>/standards/usage/<school_year>/<class_id>/events.jsonl`;
* usage ledger helpers: implemented now for explicit paths and canonical
  workspace paths, including append and overwrite-protected write behavior;
* usage summary helpers: implemented now as read-only derived counts by
  standard, usage type, module, and optional assignment ID;
* browsing/filtering helpers: implemented now for standards by ID, subject,
  source, domain, active status, available module, category path prefix, and
  for profiles by ID, subject, course, and source;
* profile-selection validation: implemented now by
  `validate_profile_standard_selection(...)`;
* in-memory mutation helpers: implemented now for add, replace, and upsert of
  `StandardDefinition` and `StandardsProfile`.

The following behavior exists but needs clearer user-facing documentation in
later tickets: display formatting, text search behavior, import modes,
overwrite confirmations, retire/reactivate workflows, profile editing
workflows, and readable CLI/menu validation messages.

The following behavior does not exist yet and belongs in later implementation
tickets: the `pds-core` console script, standards CLI commands, teacher-facing
interactive menu workflows, full library and profile import/export commands,
workspace-persisted mutation commands, module-facing selection APIs, smoke
tests for the full management workflow, and teacher-facing workflow
documentation.

The following behavior remains out of scope for v0.4.0: destructive standard
deletion, destructive profile deletion without profile lifecycle metadata,
ScoreForm or Quillan coupling, migrations from legacy module data, AI grading,
automatic standards judgment, automatic feedback generation, and
mastery/proficiency calculation.

### Canonical Storage Paths

The canonical shared standards library path is:

```text
<PDS workspace root>/standards/library.json
```

The canonical standards usage ledger pattern is:

```text
<PDS workspace root>/standards/usage/<school_year>/<class_id>/events.jsonl
```

Current missing-library behavior is implemented as follows:

* loading a missing workspace standards library returns an empty
  `StandardsLibrary`;
* loading a missing library does not create files or directories;
* writing the workspace standards library creates only the necessary
  standards library path;
* usage ledgers are separate from standards definitions and profiles.

### Data Ownership Boundaries for Management

`pds-core` owns durable standard identity, shared standard definitions,
reusable standards profiles, module availability metadata, shared storage
locations and file contracts, module-neutral browsing/filtering,
module-neutral selection validation, module-neutral import/export validation
rules, usage-event identity and common fields, and usage-ledger file
contracts.

ScoreForm owns answer keys, choices, question counts, assignment JSON shape,
OMR scoring, question-level standards alignment behavior, and ScoreForm
result exports.

Quillan owns writing assignment configuration, tagging modes, focus standards
behavior within writing workflows, teacher tags, teacher comments, teacher
notes, teacher-entered or teacher-confirmed scores, feedback records, writing
reports, and Quillan-specific interpretation of comments, hotwords, subskills,
polarity, severity defaults, feedback templates, and review metadata.

Quillan-specific standards-adjacent metadata must not be generalized into
`pds-core` merely because it is standards-related. The dependency direction
remains:

```text
pds-scoreform -> pds-core
pds-quillan   -> pds-core
```

ScoreForm and Quillan must not depend on each other.

### Standard Definition Shape for Management

The current `StandardDefinition` fields are:

* `standard_id`: durable internal Paper Data Suite identifier;
* `code`: teacher-facing/display-facing code, often official notation;
* `source`: issuing authority, local collection, or provenance;
* `short_name`: compact teacher-facing label;
* `description`: full teacher-facing description;
* `subject`: optional subject filter/display field;
* `course`: optional course filter/display field;
* `grade_band`: optional grade-band display field;
* `domain`: optional domain or source-defined grouping;
* `category_path`: ordered grouping path for navigation;
* `tags`: optional lightweight filter/search metadata;
* `active`: active versus retired/inactive status;
* `available_modules`: module availability/filtering metadata.

Machine-readable module data should store `standard_id`, not `code`.
`standard_id` is the durable internal key; `code` is not durable enough to
serve as the internal key because it may be reformatted, duplicated across
sources, or reused across jurisdictions. `active=false` means retired or
inactive, not deleted. Retired standards remain loadable, showable,
exportable, and valid historical references.

### Standards Profile Shape for Management

The current `StandardsProfile` fields are:

* `profile_id`: durable profile identifier;
* `standards`: ordered tuple of referenced `standard_id` values;
* `subject`: optional subject filter/display field;
* `course`: optional course filter/display field;
* `source`: optional source filter/display field;
* `title`: optional teacher-facing title;
* `description`: optional teacher-facing description.

Profiles are reusable groupings of shared `standard_id` values. Profile
entries must reference known standards, and profile standard lists must not
contain duplicates. Profiles do not replace module assignment schemas.
Modules may reference profiles and selected/focus standards, but the module
continues to own the assignment data shape and workflow behavior. Destructive
profile deletion is not part of the v0.4.0 management surface.

### Durable ID Expectations

The v0.4.0 management surface should follow these identity rules:

* module data should store `standard_id`, not `code`;
* `standard_id` should be stable once used;
* `standard_id` should not be changed as part of ordinary display-code
  cleanup;
* official code formatting changes should be handled by updating
  `code`/display metadata, not by creating incompatible IDs unless a
  deliberate migration is planned;
* teacher-created or local standards should have a clear local namespace or
  provenance convention;
* duplicate `standard_id` values are invalid;
* duplicate display `code` values may be possible across sources,
  jurisdictions, or local collections and must not be treated as globally
  durable.

Exact ID-generation syntax and namespace rules are still an open design
question. Later implementation tickets must settle that deliberately rather
than inventing incompatible behavior command by command.

### Teacher-Facing Display Fields

List and search views should use compact rows that include enough information
for fast selection: `code`, `short_name`, `subject`, `course`, `grade_band`,
`source`, `domain`, `active`, and a visible way to reveal `standard_id`.
Detail views should include `standard_id`, `code`, `short_name`,
`description`, `subject`, `course`, `grade_band`, `source`, `domain`,
`category_path`, `tags`, `active`, and `available_modules`.

Teacher-facing displays should prefer `code` and `short_name` for readability
while preserving access to `standard_id` for durable references, support
cases, imports, and exact command use. Retired/inactive standards should be
visibly marked in compact rows and detail views.

### Browsing and Filtering Needs

Implemented browsing/filtering needs include:

* find standard by `standard_id`;
* filter standards by subject;
* filter standards by source;
* filter standards by domain;
* filter standards by active/inactive status;
* filter standards by available module;
* filter standards by category path prefix;
* list available subjects;
* list available sources;
* list available domains;
* list available category paths;
* find profile by `profile_id`;
* filter profiles by subject;
* filter profiles by course;
* filter profiles by source.

Text search over standard code, short name, description, tags, profile title,
and profile description remains future work. Later CLI/menu tickets should
define whether search is case-insensitive substring matching, token matching,
ranked search, or another explicit behavior.

### Import/Export Expectations

Later import/export commands should follow these rules:

* import must validate before writing;
* invalid imports must not partially write data;
* writes should be atomic where practical;
* export should produce deterministic UTF-8 JSON;
* import/export should preserve durable IDs;
* import/export should preserve inactive standards;
* import/export should preserve profiles;
* import behavior must distinguish replace, merge, and upsert behavior
  explicitly;
* no command should silently overwrite existing library data without an
  explicit flag or confirmation;
* profile import/export should be defined separately from full library
  import/export if both are planned.

The current backend already provides deterministic JSON serialization,
validation, and atomic explicit-path writes for a full `StandardsLibrary`.
It does not yet provide user-facing import/export commands, merge semantics,
profile-only file formats, confirmations, or dry-run reporting.

### Mutation Safety Rules

v0.4.0 supports adding, replacing, upserting, retiring, and reactivating
standard definitions. It does not support destructive deletion of standard
definitions. Retire/reactivate should be implemented by replacing or
upserting the definition with `active=false` or `active=true`.

For standards profiles, v0.4.0 supports adding, replacing, and upserting a
profile. It supports adding standard IDs to a profile and removing standard
IDs from a profile by replacing or upserting the complete profile. It does
not support destructive profile deletion unless a later lifecycle model is
deliberately added.

Destructive deletion is avoided because standards and profiles may be
referenced by ScoreForm assignments, Quillan assignments or review records,
future usage ledgers, exports, and historical teacher-controlled data.
Deletion risks orphaning those records. Retired standards should remain valid
historical references.

### CLI Command Plan

The accepted v0.4.0 command root is:

```text
pds-core
```

The package configuration does not currently expose a `pds-core` console
script. Adding that console script belongs in the later CLI implementation
ticket.

The proposed standards command structure is:

```text
pds-core standards list
pds-core standards show <standard_id>
pds-core standards search <query>
pds-core standards subjects
pds-core standards sources
pds-core standards domains
pds-core standards categories
pds-core standards validate
pds-core standards validate-file <path>
pds-core standards import <path>
pds-core standards export <path>
pds-core standards add ...
pds-core standards replace ...
pds-core standards upsert ...
pds-core standards retire <standard_id>
pds-core standards reactivate <standard_id>
```

The proposed profiles command structure is:

```text
pds-core standards profiles list
pds-core standards profiles show <profile_id>
pds-core standards profiles validate <profile_id>
pds-core standards profiles import <path>
pds-core standards profiles export <profile_id> <path>
pds-core standards profiles add ...
pds-core standards profiles replace ...
pds-core standards profiles upsert ...
pds-core standards profiles add-standard <profile_id> <standard_id>
pds-core standards profiles remove-standard <profile_id> <standard_id>
```

These commands are a plan only. This issue does not implement them.

### Teacher-Facing Menu Workflow Plan

A later teacher-facing menu should expose a standards management menu similar
to:

```text
Standards Library Management
1. Browse standards
2. Search standards
3. View standard details
4. Browse standards profiles
5. View profile details
6. Create standards profile
7. Edit standards profile standards
8. Import standards library/profile
9. Export standards library/profile
10. Validate standards library
11. Return to previous menu
```

Menu behavior should be conservative:

* invalid input should not corrupt data;
* destructive behavior should be avoided;
* retire/reactivate should require clear confirmation;
* imports should validate before write;
* overwrite/replace behavior should require explicit confirmation;
* menu workflows should reuse the same backend services as CLI workflows;
* menu workflows should not implement separate standards logic.

This is a workflow plan only. This issue does not implement the menu.

### Module-Facing API Plan

Later module-facing APIs for ScoreForm, Quillan, and future modules should
expose module-neutral helpers such as:

* load active workspace standards library;
* list/select standards for a module;
* list/select profiles for a module;
* find/format standard display labels;
* find/format profile display labels;
* validate selected profile and selected standard IDs;
* return readable validation errors suitable for CLI/menu use.

Module-facing tests in `pds-core` must avoid importing ScoreForm or Quillan.
Modules should store durable `standard_id` values, may display teacher-facing
`code`, `short_name`, and description from the shared library, and should not
create independent standards libraries. Modules should not silently record
standards usage merely because an assignment alignment exists. Standards
usage events are explicit teacher-controlled or module-controlled records,
not automatic grading judgments.

See [`module_standards_integration.md`](module_standards_integration.md) for
the concrete Quillan assignment-config expectations, ScoreForm question-level
alignment expectations, validation behavior, and future-module checklist.

### Missing Workflow Inventory

The current status of v0.4.0 management workflows is:

* `pds-core` console script: future work;
* standards list/show/search CLI commands: future work;
* subject/source/domain/category browsing CLI commands: future work;
* standards validate CLI commands: future work;
* standards import/export CLI commands: future work;
* standards mutation CLI commands: future work;
* standards profile management CLI commands: future work;
* teacher-facing standards management menu: future work;
* module-facing selection API: future work;
* smoke tests for full management workflow: future work;
* documentation for teacher-facing workflows: future work.

The backend helpers those workflows can build on are implemented for models,
validation, serialization, explicit-path storage, canonical workspace storage,
usage ledgers, usage summaries, browsing/filtering, profile-selection
validation, and in-memory add/replace/upsert mutation.

## Explicit Non-Goals

This issue does not implement:

* standards CLI commands;
* standards import or export CLI commands;
* standards mutation commands;
* profile management commands;
* yearly reset commands;
* teacher-facing interactive standards menus;
* module-facing standards selection APIs;
* ScoreForm standards migration;
* Quillan standards migration;
* migration adapters;
* standards UI or menu workflows;
* automatic standards import from state websites;
* standards ingestion from PDFs;
* OCR or AI parsing logic;
* real state standards libraries or official standards PDFs;
* generated standards libraries, except tiny synthetic test fixtures when
  needed;
* a separate `pds-standards` repository;
* AI standards tagging;
* AI grading;
* automatic evaluation of whether a standard was met or missed;
* automatic standards judgment;
* automatic feedback generation;
* automatic scoring;
* destructive standard deletion;
* destructive profile deletion.

This contract also does not change assignment schemas, scoring behavior,
writing review behavior, result exports, workspace behavior, route behavior,
roster behavior, or package runtime behavior.

## Acceptance Criteria

This contract remains useful as the standards subsystem evolves when:

* it explains why standards belong initially in `pds-core`;
* it preserves module-specific assignment identity and behavior;
* it distinguishes durable definitions from class/year-scoped usage events;
* it addresses official standards codes versus storage-safe identifiers;
* it addresses teacher-facing standards menu navigation across multiple
  subjects and standards sets;
* it describes grouping metadata such as domain, strand, category, or
  `category_path`;
* it makes clear that standards grouping is for navigation, filtering,
  reporting, and assignment construction, not scoring or mastery judgment;
* it preserves ScoreForm question-level alignment behavior;
* it preserves Quillan ownership of writing-specific standards metadata;
* it defines conservative shared usage types and non-destructive yearly reset
  semantics;
* it distinguishes implemented shared layers from future work.

## Report Back

Future standards implementation issues should report:

* files changed;
* standards contract sections updated, if any;
* implemented shared layer;
* validation commands and results;
* confirmation that unrelated module behavior was not changed;
* confirmation that no sibling repositories were modified;
* remaining open design questions.

## Open Design Questions

The following questions should be resolved before implementation:

1. What exact syntax and generation rules should `standard_id` use for
   official and teacher-defined standards?
2. How should source editions and revised official wording affect identity and
   version history?
3. Should the library use one JSON collection, per-record files, JSON Lines,
   or a small local database?
4. What schema-version and migration metadata belongs in each storage file?
5. Does missing `available_modules` mean all modules, no modules, or
   unspecified availability?
6. How should profile ordering, profile versioning, and inactive references be
   represented?
7. Should namespaced module extensions live with definitions, in separate
   module files, or remain entirely in module storage?
8. What event correction model provides a useful audit trail without making
   local maintenance cumbersome?
9. How should non-assignment usage events identify their instructional
   context?
10. What action explicitly creates a usage event, and how should duplicate
    events from repeated module operations be prevented?
11. Which module identifier vocabulary is canonical in shared records:
    package names such as `pds-scoreform` or shorter names such as
    `scoreform`?
12. How should school-year selection interact with future workspace rollover
    and archival tooling?

These are implementation prerequisites, not permission to broaden this issue
into package code.

## Implemented Shared Layers

`pds-core` now provides these shared standards layers:

* shared standard definition and standards profile models;
* standards library dictionary conversion and structured validation;
* explicit-path standards library JSON loading and atomic writing;
* canonical workspace standards library path;
* workspace standards library loading that returns an empty library when
  `standards/library.json` is missing, without creating files;
* workspace standards library writing through the canonical
  `standards/library.json` path;
* standards usage event model and dictionary conversion;
* explicit-path standards usage JSON Lines helpers;
* canonical workspace standards usage ledger helpers;
* read-only usage summaries derived from recorded usage events;
* active school-year workspace state;
* read-only in-memory standards browsing and filtering helpers;
* pure in-memory standards library mutation helpers for adding, replacing,
  and upserting standard definitions and standards profiles.

These shared layers keep durable definitions and profiles separate from
year/class-scoped usage events. They do not add module UI, standards selection,
assignment attachment workflows, automatic usage recording, scoring, grading,
mastery judgment, or feedback generation. The browsing helpers are read-only
library views and do not create, edit, delete, import, migrate, or record
usage.

The mutation helpers return new `StandardsLibrary` instances and validate the
resulting libraries. They do not read files, write files, create directories,
inspect workspace state, record standards usage, or implement module
selection/editing workflows. They also do not add delete or remove behavior;
standards that should no longer be used can be retired by replacing the
definition with `active=false`.

## Future Implementation Sequence

1. Resolve remaining identity, versioning, availability, and event-correction
   questions before adding migration behavior.
2. Add ScoreForm compatibility and standards-selection workflows while
   preserving ScoreForm assignment schemas, scoring, exports, and
   question-level alignment behavior.
3. Migrate ScoreForm standard references incrementally only through explicit,
   teacher-visible migration or adapter work.
4. Add Quillan compatibility and adapter work while preserving Quillan-owned
   profiles, assignment configuration, tags, comments, review behavior,
   scoring, feedback, subskills, hotwords, and metadata.
5. Consider namespaced module-extension storage only after both module
   integrations prove a shared need.
6. Consider package extraction only if independent standards versioning
   becomes operationally useful.

Each future implementation phase should be a focused follow-up issue with
tests, migration safeguards, and no unrelated module redesign. ScoreForm and
Quillan must continue to avoid depending on each other.

## Summary

`pds-core` should become the shared owner of durable standard definitions,
reusable profiles, module availability metadata, and class/year-scoped usage
events. ScoreForm should retain question-level selected-response alignment.
Quillan should retain its writing-specific profiles, comments, tags, scoring,
feedback, subskills, hotwords, and review interpretation.

Official standard codes should remain faithful source/display values rather
than path identifiers. Shared usage records should describe teacher-controlled
instructional use, never automated mastery or scoring judgments. Definitions
remain durable across years; a yearly reset begins a new usage scope without
deleting library or historical data.
