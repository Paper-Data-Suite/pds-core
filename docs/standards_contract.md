# Shared Standards Library and Usage Contract

## Purpose

This document defines the shared Paper Data Suite contract for a standards
library and standards-usage tracking.

The central architecture decision is:

```text
pds-core owns the shared standards library and standards usage ledger.
Modules own module-specific standards behavior and interpretation.
```

This document began as a design contract. Focused implementation issues have
since added shared standards models, JSON-compatible conversion helpers,
explicit-path JSON file helpers, and the canonical workspace library path.
Usage events, usage ledgers, CLI commands, migrations, module adapters, and
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

A possible future logical layout for additional standards data is:

```text
<PDS workspace root>/
  standards/
    library.json
    profiles/
      <profile_id>.json
    usage/
      <school_year>/
        <class_id>/
          events.jsonl
```

Only `standards/library.json` is a current storage commitment. The profile and
usage paths are directional future work, not final file-format commitments.

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

Profiles may provide useful grouping metadata, but they must not become
assignment schemas. Modules decide how a profile is selected, filtered, and
used in an assignment workflow.

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

This is illustrative, not a final implemented schema.

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

`assignment_id` should be required for assignment-backed events. A future
contract may allow non-assignment instructional events, but it must represent
their context explicitly rather than inventing a fake assignment.

Usage summaries should be derived views, not the only stored record. A count
must remain explainable in terms of its underlying events.

The `school_year` format should be canonical, likely `YYYY-YYYY`, and validated
independently from general route identifiers.

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

## Explicit Non-Goals

This issue does not implement:

* standards CLI commands;
* usage event storage;
* usage summary generation;
* yearly reset commands;
* ScoreForm standards migration;
* Quillan standards migration;
* migration adapters;
* standards UI or menu workflows;
* automatic standards import from state websites;
* AI standards tagging;
* AI grading;
* automatic evaluation of whether a standard was met or missed;
* automatic standards judgment;
* automatic feedback generation;
* automatic scoring.

This contract also does not change assignment schemas, scoring behavior,
writing review behavior, result exports, workspace behavior, route behavior,
roster behavior, or package runtime behavior.

## Acceptance Criteria

This contract is complete for the current design issue when:

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
* it remains documentation-only.

## Report Back

Completion reporting for this design issue should include:

* files changed;
* standards contract sections added or updated;
* existing ScoreForm and Quillan behavior documented;
* proposed core/module boundary;
* proposed storage direction;
* proposed standard code and identifier strategy;
* proposed menu navigation and grouping strategy;
* proposed usage-type strategy;
* proposed migration sequence;
* whether any code files changed;
* validation commands and results;
* confirmation that no standards implementation was added;
* confirmation that no sibling repositories were modified;
* open design questions that should be resolved before implementation.

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

## Future Implementation Sequence

1. Review and accept this contract.
2. Resolve the open identity, storage, versioning, availability, and event
   correction questions.
3. Define versioned, module-neutral standard-definition and profile schemas in
   `pds-core`.
4. Add read-only loading and structured validation for the shared library.
5. Add explicit, atomic writing for definitions and profiles.
6. Define and implement the usage-event model and canonical usage vocabulary.
7. Add class/year-scoped usage storage and read-only summary generation.
8. Add non-destructive school-year scope selection or rollover behavior.
9. Add a ScoreForm compatibility adapter that preserves question-level
   alignment and assignment behavior.
10. Migrate ScoreForm standard references incrementally without changing
    scoring or exports.
11. Add a Quillan compatibility adapter that preserves profiles, assignment
    configuration, tags, comments, and review behavior.
12. Consider namespaced module-extension storage only after both module
    migrations demonstrate a shared need.
13. Consider package extraction only if independent standards versioning
    becomes operationally useful.

Each implementation phase should be a focused follow-up issue with tests,
migration safeguards, and no unrelated module redesign.

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
