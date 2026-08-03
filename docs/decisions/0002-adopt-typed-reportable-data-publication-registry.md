# ADR 0002: Adopt a Typed Work and Reportable-Data Publication Registry

**Status:** Accepted
**Date:** July 26, 2026
**Decision owners:** Paper Data Suite maintainers
**Applies to:** `pds-core` and all Paper Data Suite modules that publish data for cross-module grading or reporting
**Related issue:** `Paper-Data-Suite/pds-core#155`
**Umbrella issue:** `Paper-Data-Suite/pds-core#154`

## Context

Paper Data Suite modules create different kinds of authoritative records.

Current and planned examples include:

* ScoreForm selected-response results, points, question responses, correctness evidence, provenance, and multiple attempts;
* Quillan submission-review state, teacher-confirmed Focus Standard ratings, feedback exports, and assignment-local reports;
* Concord teacher-approved criterion and standards Score Records, evidence links, Moderation state, non-score dispositions, and supersession history;
* and Portia Events, Supports, Interventions, implementation records, Follow-Ups, and Outcomes.

A grading and reporting module such as Meridian must be able to discover selected data from those modules across:

* assignments;
* Activities;
* Supports and Interventions;
* classes;
* academic periods;
* and time.

That discovery must not require Meridian to understand every sibling module’s internal filesystem layout or import its private Python implementation.

The current Core 0.5 architecture already provides two shared identities that are relevant to this problem.

A module-owned top-level work context is identified by:

```text
ModuleWorkRef
├── module_id
├── class_id
└── work_id
```

A typed reference to a module-owned record is identified by:

```text
ModuleRecordRef
├── module_id
├── record_kind
├── record_id
└── optional contract_version
```

Those identities are deliberately module-neutral.

For example, `work_id` may identify:

* a ScoreForm assignment;
* a Quillan assignment;
* a Concord Activity;
* a Portia Event;
* or a Portia Support Process.

The existence of a `ModuleWorkRef` does not assert that the work is:

* academic;
* graded;
* student-specific;
* reportable;
* or associated with a grading period.

Core also owns immutable PDS2 route registrations, but route registrations solve a different problem.

A PDS2 route registration identifies the relationship:

```text
expected physical page route
    -> module-owned page record
```

It does not announce that a module has produced:

* assignment results;
* Score Records;
* standards ratings;
* intervention history;
* or another reportable record set.

Physical-page routing and reportable-data publication therefore require separate Core contracts.

### Current producer differences

The producing modules do not share one universal result model.

#### ScoreForm

ScoreForm writes append-preserving result histories containing:

* points earned;
* total available points;
* responses;
* question correctness;
* attempt numbers;
* result origin;
* print issuance identity;
* scan provenance;
* and question-level standards alignment.

ScoreForm does not choose which attempt becomes the official Grade.

#### Quillan

Quillan records teacher-reviewed written-response outcomes, including:

* assignment Focus Standards;
* assignment-local rating scales;
* overall Focus Standard ratings;
* missing ratings;
* returned-without-full-review state;
* review progress;
* minimum-requirement state;
* warnings;
* and feedback-export state.

A missing Quillan rating is not zero or the lowest rating.

Quillan’s assignment-reporting design already anticipates an assignment-local JSON handoff artifact, but that artifact is not yet an immutable, revision-addressable Core publication.

#### Concord

Concord distinguishes:

* evidence;
* Review;
* Moderation;
* Scoring;
* Grading;
* and Reporting.

A Concord Score Record is one teacher-approved judgment about one Criterion and one explicit target under one exact Scoring Scale revision.

A Concord Score is not a Grade.

Concord also preserves non-score dispositions such as:

* insufficient evidence;
* absent;
* excused;
* not observed;
* not applicable;
* and deferred.

Those dispositions must not be converted automatically into zero or low performance.

#### Portia

Portia owns behavior-support and intervention records.

Portia data may be relevant to authorized reports describing:

* what support was planned;
* what intervention was implemented;
* what follow-up occurred;
* and what outcome was recorded.

Portia records must not automatically:

* become academic Scores;
* become Grades;
* alter academic results;
* or influence academic weighting.

A report may include both academic information and an intervention summary while preserving their different meanings.

### Discovery approaches that do not satisfy the suite

Meridian could recursively crawl every module work directory and inspect files that appear relevant.

That approach is rejected because it would:

* depend on undocumented module layouts;
* require module-specific filename assumptions;
* make discovery slow and implicit;
* make compatibility difficult to determine;
* make partial or corrupt work trees difficult to distinguish from unpublished work;
* and tightly couple Meridian to every producer’s storage implementation.

The suite could instead maintain one shared mutable manifest containing all available results.

That approach is rejected because it would:

* create a shared write-contention point;
* allow one failed producer write to damage suite-wide discovery;
* make independent publication difficult;
* obscure module ownership;
* lose exact historical revisions;
* and combine academic and intervention data in one mutable document.

Each module could expose only a mutable file such as:

```text
latest.json
```

or:

```text
assignment_results_manifest.json
```

That approach is insufficient because an old publication record could later resolve to different bytes after the producer overwrites the file.

Core could define one universal student-result schema.

That approach is rejected because ScoreForm attempts, Quillan ratings, Concord Scores, and Portia interventions have materially different:

* identities;
* scales;
* dispositions;
* subjects;
* targets;
* provenance;
* privacy;
* and educational meaning.

Paper Data Suite therefore requires a shared discovery envelope without a shared native-result schema.

## Decision

Paper Data Suite will adopt a **typed work and reportable-data publication registry** owned by `pds-core`.

The foundational rule is:

> Producing modules remain authoritative for their native records and manifests. Core records that an exact, typed manifest revision was published and makes that publication discoverable without interpreting its educational meaning.

The normal relationship is:

```text
module-owned work
    -> optional Core Academic Work Registration
    -> module-owned authoritative records
    -> immutable module-owned manifest revision
    -> immutable Core Publication Record
    -> derived Core publication catalog
    -> Meridian or another authorized consumer
```

The publication flow is:

```text
Module creates or updates authoritative native records
    -> module creates an immutable, revision-addressable manifest
    -> module asks Core to publish that exact manifest revision
    -> Core validates the shared publication envelope
    -> Core verifies the manifest path and digest
    -> Core creates an immutable canonical Publication Record
    -> the derived catalog is updated or later rebuilt
    -> Meridian discovers compatible publications
    -> Meridian imports the exact published manifest revision
    -> Meridian applies its own grading or reporting policy
```

It is not:

```text
Module result
    -> Core converts it to a generic score
    -> Core calculates a Grade
```

It is also not:

```text
Meridian
    -> recursively scan every module work directory
    -> infer which files contain current results
```

## Core Concepts

### Module work remains neutral

The existing `ModuleWorkRef` remains the shared identity for one module-owned top-level work context:

```text
module_id + class_id + work_id
```

A module work unit is not automatically:

* an assignment;
* academic work;
* graded work;
* registered work;
* reportable work;
* or published work.

The following may all be valid module work units:

```text
scoreform / english10_p2 / short_story_quiz
quillan   / english10_p2 / literary_analysis
concord   / apcsp_p1     / collaborative_debugging
portia    / english10_p2 / sup_<opaque-id>
```

Their shared identity shape does not make their domain meanings equivalent.

### Academic Work Registration

An **Academic Work Registration** is a Core-owned shared record declaring that one existing `ModuleWorkRef` represents work that may participate in academic grading or academic reporting.

Registration is explicit.

Core must not infer academic intent from:

* `module_id`;
* `work_id`;
* a directory name;
* a result file;
* the presence of standards;
* the existence of a Score;
* or the fact that a work unit produced printable pages.

Academic Work Registration is separate from publication.

A registered work item may have no published results.

A published intervention record set may have no Academic Work Registration.

An Academic Work Registration may expose a small shared metadata envelope such as:

* the complete `ModuleWorkRef`;
* a teacher-readable title snapshot;
* producer contract information;
* work kind;
* academic intent;
* lifecycle state;
* creation timestamp;
* update timestamp;
* and registration revision.

This metadata must not become a duplicate assignment, Activity, rubric, or grading-policy schema.

Academic Work Registration does not determine:

* whether the work counts toward a Grade;
* grading category;
* weight;
* point value;
* attempt-selection policy;
* academic-period membership;
* lateness;
* reassessment policy;
* mastery;
* or reporting audience.

Those decisions belong to Meridian or another authorized downstream system.

#### Registration identity and revision

The identity of an Academic Work Registration is the complete `ModuleWorkRef`.

The identity fields:

```text
module_id
class_id
work_id
```

are immutable.

Permitted metadata changes must be revisioned and auditable.

A later implementation may use immutable registration revisions with a current pointer or another append-preserving representation, but it must not silently overwrite registration history.

The exact serialized registration schema and persistence layout belong to later implementation work.

### Module-owned manifest

A **module-owned manifest** is the producer’s machine-readable handoff artifact for one exact revision of one reportable record set.

The manifest remains owned by the producing module.

Core does not define one universal manifest body.

A manifest may contain producer-specific information such as:

* ScoreForm attempts, points, responses, correctness, and question evidence;
* Quillan review state, Focus Standard ratings, feedback-export state, and warnings;
* Concord Score targets, Criteria, standards, Scoring Scale revisions, dispositions, evidence links, and Moderation state;
* or Portia intervention implementation, follow-up, and outcome projections.

The producer remains authoritative for:

* manifest meaning;
* native record identity;
* native validation;
* source-record relationships;
* privacy;
* and whether a native change warrants a new manifest revision.

Core validates only the shared requirements needed to publish and locate the manifest safely.

### Publication Record

A **Publication Record** is an immutable Core-owned registry record announcing one exact module-owned manifest revision.

A Publication Record conceptually identifies:

* Core publication schema version;
* durable Core publication ID;
* producing module;
* source `ModuleWorkRef`;
* optional source `ModuleRecordRef`;
* publication kind;
* producer-declared shared capabilities;
* stable producer-owned record-set identity;
* record-set revision;
* producer manifest contract version;
* safe workspace-relative manifest path;
* manifest digest algorithm;
* manifest digest;
* publication timestamp;
* optional Academic Work Registration relationship;
* optional superseded Publication Record;
* and limited nonauthoritative module details where required.

The exact serialized schema belongs to later implementation work.

A Publication Record is not:

* the producer manifest;
* the native result set;
* a Grade;
* a grading calculation;
* a report;
* a report subscription;
* a route registration;
* a mutable current-state record;
* or an authorization grant.

Publication Records are created exclusively and never overwritten.

### Source work scope

The initial publication contract requires every Publication Record to identify exactly one `ModuleWorkRef`.

The published manifest must belong to that work context and must be stored beneath the corresponding module-owned work root.

Conceptually:

```text
classes/
  <class_id>/
    modules/
      <module_id>/
        work/
          <work_id>/
            ...
            exports/
              manifests/
                <record_set_id>/
                  <revision>.json
```

The exact module-owned manifest path may vary by producer, but it must be:

* workspace-relative;
* safely normalized;
* inside the workspace;
* inside the referenced module work root;
* and outside Core-owned registry storage.

This work-scoped initial rule prevents one publication from becoming an implicit cross-work or cross-class aggregate.

Cross-work, class-wide, course-wide, or school-year producer publications require a later architectural decision if a concrete use case justifies them.

Meridian may aggregate several work-scoped publications under its own contracts.

## Publication Kinds

The initial shared publication-kind vocabulary is:

```text
academic_result_set
intervention_record_set
```

Publication kind is part of the shared Core envelope.

It is not free-form producer metadata.

Adding or materially changing a shared publication kind requires an explicit Core compatibility decision and publication-contract version change.

### `academic_result_set`

An `academic_result_set` announces module-owned academic results or academic evidence that may be considered by Meridian for:

* assignment grading;
* standards reporting;
* progress reporting;
* or another explicitly configured academic purpose.

An `academic_result_set` requires an applicable Academic Work Registration.

The existence of an academic result publication does not mean:

* every result must count toward a Grade;
* every result is summative;
* every result has a numeric value;
* a result has been selected for use;
* a Grade has been calculated;
* or a particular academic period applies.

A producer may publish:

* formative;
* diagnostic;
* practice;
* feedback-only;
* standards-based;
* points-based;
* criterion-based;
* or locally informational

academic results.

Meridian decides whether and how a selected publication participates in grading or reporting.

### `intervention_record_set`

An `intervention_record_set` announces a producer-owned projection of intervention, support, implementation, follow-up, or outcome records suitable for an authorized reporting use.

An `intervention_record_set` does not require an Academic Work Registration.

It must not claim an Academic Work Registration merely because:

* an intervention occurred during an assignment;
* an Event surfaced while work was being completed;
* a student’s academic performance was discussed;
* or Meridian may include the information in a broader report.

An intervention publication must not automatically:

* become an academic Score;
* become a Grade;
* change an academic Grade;
* select a ScoreForm attempt;
* alter a Quillan rating;
* alter a Concord Score;
* create a grading exclusion;
* or influence weighting.

The foundational distinction is:

```text
intervention record != academic result
```

A report may display both kinds of information in separate, clearly identified sections without merging their semantics.

## Publication Capabilities

A Publication Record may advertise shared capabilities for compatibility and discovery.

Initial capabilities may include:

```text
points
question_evidence
multiple_attempts
standards_ratings
criterion_scores
moderated_scores
intervention_history
intervention_status
intervention_outcomes
```

The final initial vocabulary will be specified by the publication-record implementation contract.

Capabilities are shared discovery metadata.

They communicate that a compatible producer manifest may expose a particular general class of information.

Capabilities do not:

* define the manifest body;
* guarantee that every student or native record has that information;
* authorize access to sensitive records;
* define educational equivalence;
* authorize Core to interpret values;
* convert a result into a Grade;
* or authorize Meridian to combine unlike result types.

For example:

```text
points
```

does not specify:

* maximum points;
* grading weight;
* whether the result is formative;
* which attempt counts;
* or how points become a percentage.

Likewise:

```text
standards_ratings
```

does not specify:

* one universal rating scale;
* mastery;
* numeric equivalence;
* or whether ratings may be averaged.

The shared capability vocabulary is Core-owned and versioned.

Producers must not invent uncoordinated shared capability values and expect consumers to interpret them as equivalent.

Producer-specific details remain inside the producer manifest.

## Manifest Identity and Immutability

A published manifest must be immutable and revision-addressable.

A producer may maintain a mutable convenience path such as:

```text
exports/assignment_results_manifest.json
```

or:

```text
exports/latest.json
```

for teacher use or local workflow convenience.

A mutable convenience path must not be the sole canonical target of a Publication Record.

The immutable publication target should use a revision-addressable form conceptually equivalent to:

```text
exports/manifests/<record_set_id>/<revision>.json
```

After Core creates a Publication Record:

* the manifest bytes at the published path must not change;
* the manifest path must not be repointed;
* and the digest must continue to match.

A later native change requires:

1. a new immutable manifest revision;
2. a new record-set revision;
3. and a new Core Publication Record.

A digest mismatch is an integrity failure.

It must not be interpreted as an implicit update.

Core references the producer-owned manifest rather than copying the complete manifest into the registry.

This preserves module ownership and avoids duplicating potentially sensitive student-level content.

## Independent Identity and Versioning Axes

The following concepts are distinct.

### Core publication schema version

The version of Core’s shared Publication Record envelope.

### Producer manifest contract version

The version of the producer-owned manifest schema.

### Source-record contract version

The contract version of a referenced `ModuleRecordRef`, where applicable.

### Record-set identity

A stable producer-owned identifier for one logical publication series.

The shared conceptual name is:

```text
record_set_id
```

A record-set ID must be:

* durable;
* opaque or nonsemantic;
* path-safe;
* free of student names and direct personal information;
* and unique within the producing module work context.

Record-set identity is intentionally generic.

It does not assume that every publication represents:

* a Grade;
* an assignment;
* one student;
* or one kind of academic result.

### Record-set revision

A producer-declared positive integer identifying one exact revision of a record set.

Revisions must increase within one record-set series.

Revision numbers need not be contiguous.

Gaps may occur because a producer prepared but abandoned a manifest or because publication failed before a canonical Publication Record was created.

A revision number is not:

* a ScoreForm attempt number;
* a Quillan review-record revision;
* a Concord Score revision;
* a Portia lifecycle revision;
* or a Core package version.

### Publication ID

A Core-owned durable identity for one immutable Publication Record.

Publication ID does not replace:

* the source `ModuleWorkRef`;
* `record_set_id`;
* record-set revision;
* or manifest digest.

### Manifest digest

A content digest binding the Publication Record to exact manifest bytes.

The initial digest algorithm is SHA-256.

The digest representation must distinguish the algorithm from the hexadecimal digest value so a later contract may add another algorithm without ambiguity.

Changing one version axis does not imply that every other version axis changes.

For example:

* a new manifest revision does not require a new Core publication schema;
* a new Core publication schema does not rewrite native results;
* and a new Concord Score does not automatically require a new publication kind.

## Publication Idempotency and Conflicts

The logical publication key is conceptually:

```text
producing module
+ ModuleWorkRef
+ record_set_id
+ record_set_revision
```

Publication services must be idempotent.

Repeating a publication request with:

* the same logical publication key;
* the same manifest path;
* the same manifest contract version;
* and the same manifest digest

must return the existing successful publication rather than create a duplicate logical publication.

Reusing the same logical publication key with different manifest bytes, a different digest, a different manifest path, or a contradictory contract version is an integrity conflict.

Core must not:

* overwrite the earlier Publication Record;
* silently accept the changed manifest;
* assign the same revision to different bytes;
* or infer that the later filesystem modification is authoritative.

A changed record set requires a new explicit revision.

## Supersession and Current State

Publication history is append-preserving.

A new Publication Record may name zero or one prior Publication Record that it supersedes.

The first publication in a record-set series has no predecessor.

A later publication in the same series must name the current applicable predecessor.

The superseded publication remains immutable and available for:

* provenance;
* audit;
* historical reproduction;
* and explanation of earlier Meridian imports or reports.

Supersession must remain within the same:

* producing module;
* `ModuleWorkRef`;
* publication kind;
* and `record_set_id`.

A publication must not supersede an unrelated record set.

The current publication state must be derived from explicit publication relationships.

It must not be inferred from:

* filename;
* directory ordering;
* file modification time;
* publication timestamp alone;
* or highest revision alone.

A valid record-set series should have at most one unsuperseded, unwithdrawn current head.

Competing current heads are an integrity failure.

### Withdrawal

Withdrawal is represented by a separate immutable Core registry event or record.

A withdrawal identifies:

* the affected Publication Record;
* withdrawal time;
* reason;
* and any required provenance.

Withdrawal means that consumers should not newly rely on the affected publication as current data.

Withdrawal does not:

* delete the Publication Record;
* delete the producer manifest;
* delete native producer records;
* alter an earlier Meridian snapshot;
* or erase historical use.

A withdrawn publication cannot be restored by mutating its record.

A producer that needs to publish usable data again creates a new record-set revision and new Publication Record.

The exact serialized withdrawal contract belongs to implementation work.

### Native-record supersession remains separate

Publication supersession and producer-record supersession are different relationships.

For example:

```text
Concord Score Record 2
    -> supersedes Concord Score Record 1
```

is a Concord-owned source-record relationship.

A later Concord manifest publication may separately supersede an earlier Concord manifest publication.

Core must not infer one relationship from the other.

The producer manifest explains native source-record state.

The Core publication registry explains manifest-publication state.

## Canonical Registry and Derived Catalog

Core will maintain canonical registry records as local, inspectable JSON.

The registry will use a Core-owned workspace namespace outside module-owned work directories.

The conceptual layout is:

```text
<workspace>/
  <core-owned-registry-root>/
    work/
    publications/
    withdrawals/
    catalog.sqlite
```

The exact directory names, sharding rules, filenames, and path helpers belong to implementation work.

The registry root must not be named or structured as though every publication is academic.

Canonical registry records include:

* Academic Work Registration records and revisions;
* Publication Records;
* publication withdrawal records;
* and any minimal append-preserving lifecycle records required by the shared contract.

Producer manifests remain beneath producer-owned work roots.

### Canonical authority

Canonical JSON registry records are authoritative for:

* registration existence;
* publication existence;
* publication identity;
* manifest binding;
* revision;
* supersession;
* withdrawal;
* and publication metadata.

The derived catalog is not authoritative.

### Derived catalog

Core will maintain a local derived catalog, initially expected to use SQLite, for efficient discovery.

The catalog may index fields such as:

* school year where resolvable;
* class ID;
* module ID;
* work ID;
* registration state;
* publication kind;
* capability;
* manifest contract version;
* publication time;
* record-set identity;
* revision;
* current state;
* and compatibility status.

The catalog must be:

* nonauthoritative;
* replaceable;
* deletable;
* and rebuildable from canonical Core registry records.

The catalog must not contain the only copy of:

* an Academic Work Registration;
* a Publication Record;
* a withdrawal;
* a manifest path;
* a manifest digest;
* or publication history.

A missing, stale, or corrupt catalog must not invalidate otherwise valid canonical registry records.

Catalog repair must not:

* rewrite producer manifests;
* modify producer records;
* invent missing publications;
* infer unpublished work;
* or alter canonical registry history.

## Discovery Without Recursive Crawling

Normal publication discovery must query:

* the derived catalog;
* or bounded canonical Core registry locations.

Normal discovery must not recursively traverse:

```text
classes/<class_id>/modules/<module_id>/work/
```

to infer publication state.

Catalog rebuild must read canonical Core registry records.

It must not scan every module work root looking for possible manifests.

A later migration tool may perform an explicit, bounded scan of documented producer locations to help register pre-registry data.

Such a migration is:

* exceptional;
* user-invoked;
* producer-aware;
* and not part of normal publication or discovery behavior.

The absence of a Core Publication Record means that Core does not consider a manifest published, even when a file with a familiar name exists inside a producer work root.

## Separation From PDS2 Routing

PDS2 route registrations and reportable-data Publication Records are separate Core domains.

A route registration answers:

```text
Which module-owned page record does this expected physical-page locator identify?
```

A Publication Record answers:

```text
Which exact typed manifest revision has a module deliberately made available for compatible cross-module use?
```

A route registration may exist without any publication.

A publication may exist for work that generated no paper pages.

The same `ModuleWorkRef` may participate in both domains without making the records equivalent.

Core must not:

* reuse route IDs as publication IDs;
* store Publication Records beneath `routes/`;
* treat a successful scan as an automatic publication;
* treat an active route as proof that results exist;
* or use publication state to redirect a printed page.

ADR 0001 continues to govern PDS2 page-locator routing.

This ADR does not redefine the PDS2 QR grammar, route-registration target, or physical-page lifecycle.

## Core and Module Ownership

### Core owns

Core owns:

* the Academic Work Registration envelope;
* publication schema versioning;
* Publication Record identity;
* publication-kind vocabulary;
* shared capability vocabulary;
* record-set publication identity requirements;
* manifest path and digest binding;
* publication idempotency rules;
* publication supersession rules;
* publication withdrawal rules;
* canonical registry persistence requirements;
* deterministic registry lookup;
* derived-catalog authority boundaries;
* shared validation expectations;
* and module-neutral publication discovery.

### Producing modules own

The producing module owns:

* the meaning of its work unit;
* native canonical records;
* assignment, Activity, Event, Support, or Intervention semantics;
* attempt semantics;
* Review semantics;
* Score semantics;
* disposition semantics;
* native lifecycle and supersession;
* manifest schema;
* manifest generation;
* deciding when a new manifest revision is required;
* module-specific validation;
* module-specific republication workflows;
* source-record privacy;
* and the educational meaning of every manifest value.

### Meridian owns

Meridian owns:

* source subscriptions;
* publication selection;
* exact imported-source revision tracking;
* grade items;
* reporting selections;
* attempt selection;
* exclusions;
* overrides;
* native-result projection;
* grading policies;
* weighting;
* categories;
* academic-period membership;
* Grade calculations;
* Grade history;
* reproducible snapshots;
* cross-module aggregation;
* audience-specific reports;
* and teacher-controlled academic judgments.

### Core does not own

Core does not own:

* Grade calculations;
* point-to-percentage conversion;
* rating-to-points conversion;
* mastery calculation;
* attempt selection;
* criterion aggregation;
* marking-period assignment of Grade items;
* intervention-effectiveness judgment;
* report-card policy;
* or the educational interpretation of producer data.

## Producer Compatibility

Publication compatibility is a separate concern from PDS2 routing compatibility.

The current Core `ModuleProfile` is primarily a routing and dispatch contract.

This ADR does not silently expand its meaning to include reportable-data publication.

Later implementation will define a separate publication-producer compatibility contract.

That contract may be exposed through installed module metadata or a dedicated entry point, but it must remain conceptually distinct from route dispatch.

Core’s foundational Publication Record validation must not require importing sibling-module implementation code.

Core must be able to:

* load canonical publication records;
* validate the shared envelope;
* verify safe paths and digests;
* and rebuild the derived catalog

even when the producing package is not currently installed.

An installed producer profile or optional adapter may additionally confirm:

* supported publication kinds;
* supported manifest contract versions;
* supported shared capabilities;
* and producer-specific compatibility.

Absence or incompatibility must be reported explicitly.

It must not transfer ownership of the manifest to Core.

The dependency direction remains:

```text
pds-scoreform -> pds-core
pds-quillan   -> pds-core
pds-concord   -> pds-core
pds-portia    -> pds-core
pds-meridian  -> pds-core
```

Core must not depend directly on:

* ScoreForm;
* Quillan;
* Concord;
* Portia;
* or Meridian.

Sibling modules must not import each other’s private implementation merely to interpret publications.

Cross-module use should rely on:

* Core identities;
* Core Publication Records;
* documented producer manifests;
* public producer contracts;
* and optional adapters.

## Cross-Repository Application

### ScoreForm

ScoreForm may publish an `academic_result_set` for one registered ScoreForm assignment.

Its module-owned manifest may preserve:

* points;
* total points;
* responses;
* question correctness;
* question-level standards evidence;
* attempts;
* result origins;
* issuance identity;
* source-scan identity;
* and retained-source provenance.

Core does not select an attempt.

Meridian may later apply an explicit policy such as:

* teacher-selected attempt;
* latest eligible attempt;
* highest eligible attempt;
* first attempt;
* or another configured rule.

That policy must not rewrite ScoreForm’s append-preserved result history.

ScoreForm’s current `results.csv` remains a ScoreForm-owned native artifact.

A later ScoreForm integration must publish a versioned manifest around its supported native contract rather than requiring Core or Meridian to infer interoperability from arbitrary CSV files.

### Quillan

Quillan may publish an `academic_result_set` for one registered Quillan assignment.

Its module-owned manifest may preserve:

* assignment identity;
* Focus Standards;
* assignment-local rating-scale definition;
* overall Focus Standard ratings;
* review state;
* minimum-requirement state;
* returned-without-full-review state;
* missing ratings;
* feedback-export state;
* warnings;
* and source-record timestamps or references.

Core must not:

* assume a universal four-level scale;
* convert ratings to percentages;
* infer mastery;
* infer ratings from observations;
* convert missing ratings into zero;
* or convert returned-without-full-review state into low performance.

Quillan’s existing forward-looking assignment-results manifest is an input to later producer integration design.

It is not automatically the final immutable publication contract.

A publication-ready Quillan manifest must add or bind the information required by this ADR, including:

* stable record-set identity;
* explicit record-set revision;
* immutable revision-addressed storage;
* producer manifest contract version;
* and exact Core publication digest.

### Concord

Concord may publish an `academic_result_set` for one registered Concord Activity when that Activity produces academic Scores or standards-reportable judgments.

Its module-owned manifest may preserve:

* durable Score Record identity;
* Activity context;
* optional Session context;
* explicit Score target;
* target kind;
* Criterion identity;
* Criterion kind;
* governing standard where directly standard-backed;
* exact Scoring Scale revision;
* Score disposition;
* Score value only when applicable;
* scorer provenance;
* scoring time;
* evidence links;
* Moderation state;
* current or superseded state;
* and Score supersession history.

Core must not:

* convert a Concord Score into a Grade;
* combine several Criteria;
* split a holistic Criterion Score across several standards;
* infer an individual Score from a Group Score;
* convert non-score dispositions into zero;
* or assume every Concord Activity is graded.

Concord evidence-only Activities require no Academic Work Registration merely because they exist.

A formative or reporting-relevant academic Activity may be registered without requiring Meridian to include it in a Grade.

### Portia

Portia may publish an `intervention_record_set` for one Portia Event or Support Process when Portia defines an authorized, privacy-conscious reporting projection.

Its module-owned manifest may expose safe reporting information such as:

* work identity;
* support or intervention type;
* implementation status;
* implementation occurrence;
* follow-up status;
* outcome status;
* reentry or repair status;
* and relevant time context.

The Core Publication Record must not duplicate sensitive Portia content such as:

* allegations;
* behavior narratives;
* Accounts;
* family communications;
* disability information;
* detailed intervention plans;
* private notes;
* or protected determinations.

Such data, where legitimately included in a reporting projection, remains inside the Portia-owned manifest under Portia’s privacy rules.

Portia intervention publications do not require Academic Work Registration.

Portia’s accepted module boundaries prohibit its behavior-support records from being published as academic results merely to influence a Grade.

Core should remain module-neutral rather than hard-coding a Portia-specific module-ID prohibition, but Portia’s producer contract and compatibility declaration must permit only publication kinds consistent with its accepted architecture.

### Meridian

Meridian consumes the Core registry.

Meridian may:

* discover publications by kind;
* filter by capability;
* subscribe to selected work;
* import an exact manifest revision;
* preserve the imported publication ID and digest;
* detect a later superseding publication;
* preserve an earlier calculation or report against its original source revision;
* and deliberately refresh a source when the teacher or applicable policy permits it.

Meridian must not:

* mutate producer records;
* silently replace an imported revision;
* treat publication as automatic Grade inclusion;
* interpret an intervention publication as an academic result;
* or claim that Core performed educational interpretation.

## Privacy and Data Minimization

Canonical Core registry records and the derived catalog must contain only the metadata needed for:

* identity;
* compatibility;
* deterministic discovery;
* revision tracking;
* integrity validation;
* lifecycle state;
* and repair.

They must not become duplicate student-result databases.

Ordinary Academic Work Registration records, Publication Records, withdrawal records, and catalog rows must not embed:

* full student-result arrays;
* student writing;
* question responses;
* Score values;
* private review notes;
* behavior narratives;
* intervention details;
* family communications;
* or other sensitive producer content.

Teacher-readable registration metadata should be privacy-minimized and must not function as identity.

Student names and direct personal information must not be encoded in:

* publication IDs;
* record-set IDs;
* registry filenames;
* or digest metadata.

The registry establishes discoverability.

It does not establish authorization.

The governing distinction is:

```text
discoverable publication != authorized disclosure
```

A manifest path does not authorize every installed module or every report audience to read or display the manifest’s contents.

Publication capabilities do not override:

* producer privacy rules;
* record-level restrictions;
* audience restrictions;
* or authorized-purpose requirements.

The initial teacher-local Paper Data Suite workspace does not yet provide a complete institutional authorization system.

This ADR therefore requires privacy-preserving boundaries without claiming to solve institution-wide authentication or access control.

## Failure and Recovery

The publication process must observe this order:

1. The producer creates and durably closes the immutable manifest.
2. The producer calculates or requests calculation of the manifest digest.
3. Core validates the shared publication request.
4. Core verifies that the manifest path is safe, work-scoped, present, and digest-matching.
5. Core exclusively creates the immutable Publication Record.
6. Core updates the derived catalog.
7. If catalog update fails, the canonical Publication Record remains authoritative and the catalog becomes stale.

If Publication Record creation fails, no publication exists.

The presence of an unregistered manifest file does not imply successful publication.

If canonical publication succeeds but derived-catalog update fails:

* the producer must not rewrite the manifest;
* Core must report partial success accurately;
* and catalog repair must make the publication discoverable later.

Validation and repair must be able to detect:

* malformed registry records;
* duplicate JSON keys;
* unsupported schema versions;
* unsafe paths;
* missing manifests;
* digest mismatches;
* duplicate logical publication identities;
* contradictory revision reuse;
* invalid supersession relationships;
* multiple current heads;
* invalid withdrawals;
* incompatible producer contracts;
* catalog rows without canonical records;
* and canonical records absent from the catalog.

Repair may rebuild derived state.

Repair must not:

* alter producer records;
* rewrite manifests;
* change publication identity;
* create missing publications;
* infer a new revision;
* or repair a digest mismatch by accepting changed bytes.

## Consequences

### Positive consequences

* Meridian can discover published data without recursively crawling module work directories.
* Producing modules retain authority over their native records.
* Core remains module-neutral.
* Exact manifest revisions remain reproducible.
* Publication history is append-preserving.
* Academic results and intervention records remain distinguishable.
* Portia reporting becomes possible without making Portia a grading source.
* ScoreForm attempts can remain complete and unselected.
* Quillan rating scales and missing states can remain native.
* Concord Scores and non-score dispositions can remain distinct from Grades.
* Consumers can determine compatibility before interpreting a manifest.
* One producer cannot corrupt a shared mutable suite manifest.
* Canonical JSON remains locally inspectable.
* The derived catalog can be rebuilt after corruption or deletion.
* Catalog performance does not make SQLite authoritative.
* Publication and physical-page routing remain separate.
* Future modules can participate without changing Meridian’s filesystem crawler.
* Grade calculations can preserve exact source publication identity.
* Historical reports can remain explainable after producers publish newer revisions.

### Negative consequences

* Every producer must implement manifest-generation and publication workflows.
* Existing ScoreForm and Quillan outputs require adaptation before publication.
* Concord and Portia must design safe reportable projections.
* Several distinct version and identity values must be maintained.
* Immutable manifest revisions consume additional local storage.
* Producers may need explicit republication and recovery commands.
* A stale catalog becomes a possible operational condition.
* Consumers must handle unavailable or incompatible producer contracts.
* Cross-module integration becomes more explicit than reading familiar files directly.
* Privacy and audience authorization remain broader concerns beyond the registry envelope.
* The suite gains additional record types and lifecycle relationships.
* Teachers and developers must distinguish native-record revision from publication revision.

### Risks and mitigations

#### Mutable manifest referenced by an immutable publication

**Risk:** A producer overwrites a published manifest, causing an old Publication Record to resolve to different data.

**Mitigation:** Published manifests are immutable, revision-addressable, and digest-bound. A digest mismatch is an integrity failure.

#### Duplicate logical revision with different contents

**Risk:** One producer reuses a record-set revision for different manifest bytes.

**Mitigation:** Publication identity is idempotent only when the path, contract, and digest match. Contradictory reuse fails.

#### Multiple competing current publications

**Risk:** Two publications appear to be current for one record-set series.

**Mitigation:** Later publications explicitly supersede the current predecessor. Multiple unsuperseded heads are invalid.

#### Catalog treated as authoritative

**Risk:** A corrupt SQLite database causes canonical publication history to be lost or silently changed.

**Mitigation:** Canonical JSON records remain authoritative. The catalog is fully rebuildable and contains no exclusive state.

#### Registry becomes a duplicate result store

**Risk:** Producers place student results or sensitive records directly into Core Publication Records.

**Mitigation:** Core envelopes contain only minimal discovery and integrity metadata. Student-level and domain-specific data remain in producer manifests.

#### Capabilities treated as educational equivalence

**Risk:** A consumer treats all `standards_ratings` or `points` publications as interchangeable.

**Mitigation:** Capabilities provide discovery metadata only. Manifest contracts, scales, dispositions, and Meridian policies govern interpretation.

#### Intervention data affects academic Grades

**Risk:** Portia intervention records are treated as academic performance evidence merely because Meridian can discover them.

**Mitigation:** Publication kinds remain distinct. Intervention publications do not require Academic Work Registration and cannot automatically enter academic calculation.

#### Publication interpreted as authorization

**Risk:** A consumer assumes that a discoverable manifest may be displayed to every audience.

**Mitigation:** The registry provides location and compatibility, not authorization. Producer and consumer privacy rules remain applicable.

#### Direct sibling-package coupling

**Risk:** Core or Meridian imports private ScoreForm, Quillan, Concord, or Portia implementation modules.

**Mitigation:** Shared discovery uses Core records and documented producer manifest contracts. Optional adapters must use public interfaces.

#### Work identity treated as academic intent

**Risk:** Every module work root is automatically registered for grading.

**Mitigation:** Academic Work Registration is explicit and separate from `ModuleWorkRef`.

## Alternatives Considered

### Recursively crawl module work directories

Rejected because it would:

* depend on producer storage layouts;
* require filename and directory assumptions;
* make normal discovery slow and implicit;
* make publication intent indistinguishable from file presence;
* and tightly couple Meridian to every producer.

### Use one shared mutable suite manifest

Rejected because it would:

* create a write-contention point;
* allow one producer failure to affect all modules;
* obscure ownership;
* combine unrelated data kinds;
* and fail to preserve independent exact revisions.

### Publish only mutable producer `latest` files

Rejected because an old publication could resolve to changed bytes.

Mutable convenience files may exist, but immutable revision-addressed manifests are required for canonical publication.

### Define one Core-owned universal result schema

Rejected because:

* ScoreForm attempts are not Quillan standards ratings;
* Quillan ratings are not Concord Score Records;
* Concord non-score dispositions are not zero;
* and Portia interventions are not academic results.

Core transports typed publication metadata without normalizing native meaning.

### Make SQLite the authoritative registry

Rejected because:

* a corrupt or missing database would become destructive;
* local inspection would be harder;
* repair would require database recovery rather than deterministic rebuilding;
* and the database could become the only copy of publication history.

SQLite is derived state only.

### Copy complete producer manifests into Core

Rejected as the normal contract because it would:

* duplicate authoritative data;
* increase privacy exposure;
* create competing sources of truth;
* enlarge Core’s domain responsibility;
* and require Core to retain module-specific content it does not understand.

Core stores a safe path and digest instead.

### Reuse PDS2 route registrations

Rejected because route registrations identify expected returned physical pages.

They do not identify:

* result sets;
* reportable intervention records;
* manifest revisions;
* or cross-module publication state.

The two record families have different meanings and lifecycles.

### Require every publication to represent a graded assignment

Rejected because:

* Concord Activities are not universally assignments;
* some academic work is formative or reporting-only;
* Portia Events and Support Processes are not academic work;
* and intervention reporting must not fabricate grading intent.

### Require direct sibling-package imports

Rejected because it would:

* reverse the intended dependency direction;
* make installation of one module require unrelated modules;
* couple integrations to private package structure;
* and make stored publications unreadable when a producer package is absent.

### Infer revisions from timestamps

Rejected because timestamps do not provide reliable logical revision identity.

File timestamps may change because of:

* copying;
* synchronization;
* restoration;
* or metadata operations.

Revision and supersession must be explicit.

### Use manifest digests as the only revision identity

Rejected because identical bytes and logical publication history are separate concerns.

A digest proves content identity.

It does not independently express:

* publication sequence;
* supersession;
* withdrawal;
* or producer intent.

### Store report subscriptions in Core

Rejected for this ADR because publication and subscription are different responsibilities.

Core announces available producer data.

Meridian decides which publications it subscribes to and how they are used.

## Required Follow-Up

Implementation status: completed in `pds-core` v0.6.0. The issue-by-issue list
below is retained as completed implementation history under umbrella `#154`.

### `#159` — Add academic-work registration records

Define and implement the serialized Academic Work Registration model, revision behavior, persistence paths, and validation.

### `#160` — Add typed immutable publication records

Define and implement Publication Records, publication kinds, shared capabilities, record-set identity, manifest binding, supersession, withdrawal, and canonical persistence.

### `#161` — Add idempotent registration and publication services

Implement producer-facing APIs with:

* exclusive creation;
* idempotent replay;
* revision conflict detection;
* digest verification;
* and partial-success reporting.

### `#162` — Add the derived academic and reporting catalog

Implement the nonauthoritative SQLite catalog and deterministic queries.

The catalog name and schema must not imply that every publication is academic.

### `#163` — Add registry validation, audit, and catalog-repair commands

Implement validation, status, inspection, integrity reporting, and rebuild workflows.

### `#164` — Add producer-contract fixtures and cross-module compatibility tests

Add representative synthetic publications for:

* ScoreForm;
* Quillan;
* Concord;
* and Portia.

The fixtures must preserve the native distinctions established by this ADR.

### `#165` — Document the Core integration contract and release `pds-core` v0.6.0

Publish the detailed producer integration contract, migration guidance, recovery procedures, compatibility rules, and release documentation.

### Relationship to academic periods

Issue `#156` and ADR 0003 define the academic-period hierarchy.

Academic periods and publications remain separate concepts.

Core academic periods answer:

```text
Which reporting-calendar periods exist?
```

Core publications answer:

```text
Which exact producer manifest revisions are available?
```

Meridian later decides how:

* a Grade item;
* a source result;
* a calculation;
* or a report

relates to an academic period.

A publication does not infer its marking period from:

* publication time;
* scan time;
* source-record update time;
* or filesystem location.

## References

### PDS Core

* [`0001-adopt-pds2-page-locator-routing.md`](0001-adopt-pds2-page-locator-routing.md)
* [`README.md`](README.md)
* [`../pds2_module_integration.md`](../pds2_module_integration.md)
* [`../roster_workspace_contract.md`](../roster_workspace_contract.md)
* [`../standards_contract.md`](../standards_contract.md)
* [`../../pds_core/routing_models.py`](../../pds_core/routing_models.py)
* [`../../pds_core/route_registrations.py`](../../pds_core/route_registrations.py)
* `Paper-Data-Suite/pds-core#154`
* `Paper-Data-Suite/pds-core#155`

### ScoreForm

* `Paper-Data-Suite/pds-scoreform`
* `Paper-Data-Suite/pds-scoreform/docs/schema_contracts.md`

### Quillan

* `Paper-Data-Suite/pds-quillan`
* `Paper-Data-Suite/pds-quillan/docs/assignment_reporting_contract.md`
* `Paper-Data-Suite/pds-quillan/examples/exports/assignment_results_manifest_v2_synthetic.json`

### Concord

* `Paper-Data-Suite/pds-concord`
* `Paper-Data-Suite/pds-concord/docs/decisions/0008-separate-review-moderation-scoring-grading-and-reporting.md`
* `Paper-Data-Suite/pds-concord/docs/decisions/0010-exceptional-evidence-states-are-not-low-scores.md`
* `Paper-Data-Suite/pds-concord/docs/decisions/0012-link-scoreform-and-quillan-without-duplication.md`
* `Paper-Data-Suite/pds-concord/docs/decisions/0014-make-standards-based-scoring-the-primary-concord-scoring-model.md`
* `Paper-Data-Suite/pds-concord/docs/design/conceptual-data-contracts.md`

### Portia

* `Paper-Data-Suite/pds-portia`
* `Paper-Data-Suite/pds-portia/README.md`
* `Paper-Data-Suite/pds-portia/docs/design/portia-role-within-paper-data-suite.md`

### Meridian

* `Paper-Data-Suite/pds-meridian`

## Notes

This ADR establishes architecture and invariants.

It does not define:

* the complete Academic Work Registration JSON schema;
* the complete Publication Record JSON schema;
* the complete withdrawal-event schema;
* final registry directory names;
* SQLite table definitions;
* public Python APIs;
* CLI syntax;
* producer manifest schemas;
* Meridian subscription records;
* grading calculations;
* or report formats.

Those details belong to the implementation and producer-integration issues governed by this decision.

Implementation convenience must not weaken these invariants:

* module work remains neutral;
* academic registration is explicit;
* manifests remain producer-owned;
* published manifest bytes remain immutable;
* Publication Records remain immutable;
* revision and supersession remain explicit;
* Core does not normalize native educational meaning;
* intervention records remain distinct from academic results;
* canonical JSON remains authoritative;
* the catalog remains derived;
* and normal discovery does not recursively crawl module work directories.
