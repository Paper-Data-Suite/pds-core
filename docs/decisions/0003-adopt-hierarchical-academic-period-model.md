# ADR 0003: Adopt a Hierarchical Academic-Period Model

**Status:** Accepted
**Date:** July 27, 2026
**Decision owners:** Paper Data Suite maintainers
**Applies to:** `pds-core`, `pds-meridian`, and Paper Data Suite modules that reference shared academic-calendar periods
**Related issue:** `Paper-Data-Suite/pds-core#156`
**Umbrella issue:** `Paper-Data-Suite/pds-core#154`

## Context

Paper Data Suite currently has shared school-year identity but no shared academic-calendar structure beneath a school year.

Core validates school years using consecutive four-digit years:

```text
YYYY-YYYY
```

For example:

```text
2026-2027
```

Core also stores workspace active-school-year state at:

```text
<workspace>/settings/school_year.json
```

and class metadata associates each class with one school year:

```text
classes/<class_id>/class.json
    -> school_year
```

These contracts establish:

* which school year is selected for current teacher workflows;
* and which school year owns a class.

They do not define:

* exact school-year calendar dates;
* marking periods;
* semesters;
* quarters;
* trimesters;
* progress-reporting windows;
* custom reporting windows;
* parent-child term relationships;
* or stable period identities.

Meridian requires shared period identity for future:

* grade-item organization;
* marking-period calculations;
* semester calculations;
* progress reports;
* standards-progress reporting;
* Grade snapshots;
* report generation;
* and longitudinal navigation.

Without a shared Core period model, Meridian could define private period strings such as:

```text
MP1
Quarter 2
Semester One
Progress Report
```

That would create several architectural problems:

* period identity would not be shared across the suite;
* labels could be mistaken for durable identifiers;
* period definitions could be duplicated for every class;
* calendar corrections could diverge among modules;
* future reporting and archival modules could introduce competing period models;
* and downstream references could not reliably distinguish periods with similar names in different school years.

Core therefore needs to own neutral academic-period identity and calendar structure.

Core must not become the gradebook.

A shared period such as:

```text
Marking Period 1
```

does not determine:

* which assignments count in that period;
* whether one Grade item belongs to several periods;
* whether child-period results roll into a parent;
* whether a progress report includes a Grade item;
* whether a Grade is locked;
* whether late work remains in the original period;
* or how any Grade is calculated.

Those responsibilities belong to Meridian.

### Current school-year state is not a calendar

The existing active-school-year state records:

* the active school-year identifier;
* when that state was opened;
* and when it was closed.

It does not establish instructional or reporting dates.

Opening:

```text
2026-2027
```

must not imply that the year:

* begins on July 1, August 1, or September 1;
* ends on June 30;
* contains four marking periods;
* contains two semesters;
* or follows one district’s schedule.

Likewise, closing the active school year is a workspace workflow action.

It must not automatically:

* close academic periods;
* lock Grades;
* finalize reports;
* alter period dates;
* or archive class data.

### Class school-year metadata is not a period calendar

Class metadata records one `school_year` for the class.

The calendar is normally shared by several classes in the same school year.

Copying period definitions into every `class.json` would:

* duplicate shared state;
* create conflicting calendar authorities;
* require synchronized updates;
* and turn class metadata into a grading-calendar schema.

The academic-period calendar therefore needs its own Core-owned representation.

### Producer records do not own period membership

Paper Data Suite producer modules own different native records:

* ScoreForm owns selected-response assignments, attempts, and results.
* Quillan owns writing assignments, reviews, ratings, and assignment-level reports.
* Concord owns Activities, evidence, Moderation, and Score Records.
* Portia owns Events, Supports, Interventions, Follow-Ups, and Outcomes.

Those modules may record native dates such as:

* assignment dates;
* attempt timestamps;
* scan timestamps;
* review timestamps;
* Score timestamps;
* Event occurrence dates;
* or intervention implementation dates.

Those dates do not by themselves determine academic-period membership.

A ScoreForm attempt completed after the end of a marking period might still belong to the original marking period under a reassessment or late-work policy.

A Quillan assignment due during one period might be intentionally graded in another.

A Concord Activity may span several periods.

A Portia intervention record may be reportable without being an academic Grade input at all.

Period membership therefore must not be inferred universally from producer dates.

### Relationship to ADR 0002

ADR 0002 establishes:

* neutral module work;
* explicit Academic Work Registration;
* module-owned immutable manifests;
* typed Publication Records;
* and publication discovery.

Publication and academic-period structure answer different questions.

ADR 0002 answers:

```text
Which exact producer manifest revisions are available?
```

This ADR answers:

```text
Which shared academic-calendar periods exist?
```

Neither decision assigns a publication, assignment, result, or Grade item to a period.

Meridian owns those membership decisions.

## Decision

Paper Data Suite will adopt a **school-year-scoped hierarchical academic-period model** owned by `pds-core`.

The foundational relationship is:

```text
validated Core school year
    -> one Academic Period Calendar
    -> zero or more root Academic Periods
    -> optional child Academic Periods
    -> stable period references consumed by Meridian
```

A representative calendar may be:

```text
2026-2027
├── Semester 1
│   ├── Marking Period 1
│   │   └── Progress Window 1
│   └── Marking Period 2
│       └── Progress Window 2
└── Semester 2
    ├── Marking Period 3
    └── Marking Period 4
```

Another valid calendar may be:

```text
2026-2027
├── Trimester 1
├── Trimester 2
└── Trimester 3
```

A school year may also contain parallel structures:

```text
2026-2027
├── Semester 1
├── Semester 2
├── Quarter 1
├── Quarter 2
├── Quarter 3
├── Quarter 4
└── Midyear Progress Window
```

Core does not require one district structure.

Core does not require every period to belong to one universal partition of the school year.

## Academic Period Calendar

Core will define one logical **Academic Period Calendar** for each configured school year.

The calendar is scoped to:

```text
workspace + school_year
```

The calendar is not scoped to:

* one class;
* one module;
* one assignment;
* or Meridian.

The calendar contains the shared period definitions for that school year.

Conceptually:

```text
AcademicPeriodCalendar
├── schema_version
├── school_year
├── calendar_revision
├── created_at
├── updated_at
└── periods
```

The exact serialized field names and schema belong to later implementation work.

### One calendar per school year

At most one current Core calendar exists for one school year in one workspace.

For example:

```text
workspace A + 2026-2027
```

has its own calendar.

Another workspace may define a different calendar for the same school-year string.

The school-year string is therefore shared identity within a workspace, not a global institutional calendar identifier.

### Missing and empty calendars

A missing calendar and an empty calendar are different states.

A **missing calendar** means that no period calendar has been configured for the school year.

An **empty valid calendar** means that a canonical calendar exists but currently contains no periods.

Both states are valid.

A class remains valid when its school year has:

* no configured calendar;
* or an empty calendar.

Core must not fabricate default periods merely because a calendar is missing.

## School Year as the Containing Context

The existing Core school-year value remains the containing calendar context.

The school year is not itself represented as an `AcademicPeriod`.

Conceptually:

```text
school_year = 2026-2027
```

contains periods such as:

```text
semester_1
mp1
progress_1
```

This avoids two competing representations of the school year:

* one existing Core school-year identity;
* and one duplicate year-long Academic Period.

### School-year validation

Academic periods must reuse Core’s existing school-year validation.

Valid school-year identity remains:

```text
YYYY-YYYY
```

where the second year is exactly one greater than the first.

Examples:

```text
2026-2027
2027-2028
```

Invalid examples include:

```text
2026
2026-27
2026-2028
2027-2026
```

Academic-period implementation must not introduce a competing validator or school-year format.

### Calendar-date boundary

For a calendar identified as:

```text
2026-2027
```

period dates may use calendar year:

```text
2026
```

or:

```text
2027
```

They must not use a calendar year outside those two named years.

This is a broad validation boundary.

It does not assert:

* the school year starts on January 1, July 1, or September 1;
* the school year ends on a fixed date;
* or every day within those two calendar years belongs to the school year.

Explicit period definitions provide the actual configured dates.

## Academic Period Identity

Each Academic Period has one durable `period_id`.

The complete shared identity is:

```text
school_year + period_id
```

A bare `period_id` is not globally meaningful.

For example:

```text
2026-2027 + mp1
2027-2028 + mp1
```

identify different Academic Periods.

### Period ID requirements

A `period_id` must be:

* non-empty;
* validated through Core’s safe identifier rules;
* unique within its school year;
* stable;
* immutable after first canonical publication;
* free of direct personal information;
* and independent of mutable display or calendar fields.

A period ID must not derive its identity from:

* label;
* type;
* start date;
* end date;
* parent;
* sequence;
* or lifecycle state.

For example:

```text
period_id: mp1
label: Marking Period 1
```

may later become:

```text
period_id: mp1
label: First Marking Period
```

without changing identity.

### Academic Period reference

Core will provide or define a module-neutral Academic Period reference equivalent to:

```text
AcademicPeriodRef
├── school_year
└── period_id
```

Downstream records must use the complete reference or another representation that resolves unambiguously to both values.

Modules must not store an unqualified label such as:

```text
MP1
```

as though it were a durable shared reference.

## Academic Period Fields

An Academic Period conceptually contains:

```text
AcademicPeriod
├── period_id
├── period_type
├── label
├── start_date
├── end_date
├── parent_period_id
├── sequence
└── lifecycle
```

The detailed serialized schema may also include:

* optional descriptive metadata;
* creation metadata;
* or compatible extension data.

The shared model must remain small and module-neutral.

It must not become a Grade-calculation record.

## Period Types

The initial Core period-type vocabulary is:

```text
marking_period
semester
quarter
trimester
progress_window
custom
```

Period type is shared calendar metadata.

It does not impose:

* a fixed number of periods;
* equal duration;
* one required hierarchy;
* Grade weighting;
* Grade aggregation;
* report generation;
* or membership policy.

### `marking_period`

Represents a locally defined marking or grading period.

Core does not assume:

* exactly four marking periods;
* that a marking period is equivalent to a quarter;
* or that marking periods are equal in length.

### `semester`

Represents a semester calendar or reporting period.

Core does not assume:

* exactly two semesters;
* that every semester contains marking periods;
* or that a semester Grade is calculated from child periods.

### `quarter`

Represents a quarter calendar or reporting period.

Core does not assume that every school uses quarters or that four quarters must exist.

### `trimester`

Represents a trimester calendar or reporting period.

Core does not assume that all trimesters are equal or that exactly three must exist merely because one trimester exists.

### `progress_window`

Represents an interim, progress-reporting, or checkpoint window.

A progress window may:

* be a child of a marking period;
* be a root period;
* overlap other periods;
* or use the same date range as another reporting concept.

### `custom`

Represents a legitimate local period that does not fit another shared type.

Examples include:

* Midyear Examination Window;
* Capstone Reporting Window;
* Summer Session;
* Cycle 1;
* Interim Report A;
* or another locally meaningful period.

A custom period still uses all normal Core rules for:

* identity;
* dates;
* hierarchy;
* sequence;
* lifecycle;
* revision;
* and validation.

The `custom` type does not authorize arbitrary top-level schema fields.

Its local meaning is communicated through normal teacher-readable metadata.

### Type stability

A period’s `period_type` is part of its durable semantic identity.

After a period first appears in a canonical calendar revision, its type must not change.

If a period was incorrectly defined as one type but actually represents another institutional concept, the correction requires:

1. cancellation of the incorrect period;
2. creation of a new period ID with the correct type;
3. and explicit downstream reconciliation where necessary.

This prevents a period previously understood as a progress window from silently becoming a semester under the same reference.

## Date Semantics

Every Academic Period has:

```text
start_date
end_date
```

Both values are required ISO calendar dates:

```text
YYYY-MM-DD
```

The date range is inclusive.

For example:

```text
start_date: 2026-09-03
end_date:   2026-11-06
```

includes both September 3 and November 6.

### Dates rather than datetimes

Academic-period boundaries use calendar dates rather than datetimes.

They do not require:

* timezones;
* midnight normalization;
* UTC conversion;
* bell-schedule times;
* or a time of day.

Audit metadata such as `created_at` and `updated_at` may continue to use timezone-aware datetimes under normal Core conventions.

### Date invariants

A valid period must satisfy:

```text
start_date <= end_date
```

A one-day period is valid:

```text
start_date: 2026-10-15
end_date:   2026-10-15
```

For school year:

```text
2026-2027
```

both dates must use either calendar year 2026 or calendar year 2027.

Core must reject:

* malformed dates;
* impossible dates;
* incomplete date pairs;
* dates outside the two school-year calendar years;
* and a start date later than the end date.

### Dates do not assign work

Date containment does not assign any record to an Academic Period.

Core must not assign period membership from:

* assignment creation date;
* assignment due date;
* submission date;
* attempt date;
* scan date;
* review date;
* Score date;
* publication date;
* manifest revision date;
* Event date;
* or intervention date.

Meridian may provide teacher-controlled date-based suggestions.

Any accepted suggestion must become an explicit Meridian-owned membership record.

## Hierarchical Model

Academic Periods form a forest of rooted trees within one school year.

Each period has either:

```text
parent_period_id: null
```

or exactly one parent in the same calendar.

A period with no parent is a root period directly beneath the school year.

The initial Core model is not a general directed graph.

### Parent-child meaning

A parent-child relationship expresses explicit calendar organization and temporal containment.

For example:

```text
Semester 1
    -> Marking Period 1
```

means that Marking Period 1 is defined beneath Semester 1 and occurs within Semester 1’s date range.

It does not mean:

* every Grade item in Marking Period 1 counts toward Semester 1;
* the semester Grade averages its children;
* child results automatically roll up;
* or the parent uses any particular calculation.

Hierarchy is calendar structure, not hidden grading policy.

### Parent-child invariants

The hierarchy must reject:

* self-parenting;
* cycles;
* missing parents;
* multiple parents;
* cross-school-year parents;
* and child dates extending outside the parent’s date range.

For example:

```text
Semester 1:
2026-09-03 through 2027-01-29

Marking Period 1:
2026-09-03 through 2026-11-06
```

is valid.

The following is invalid:

```text
Semester 1:
2026-09-03 through 2027-01-29

Marking Period 1:
2026-08-20 through 2026-11-06
```

because the child begins before its parent.

### Explicit hierarchy

Core must not infer hierarchy from:

* labels;
* period types;
* date containment;
* matching dates;
* sequence;
* or naming conventions.

A period whose dates fall inside another period remains unrelated unless `parent_period_id` explicitly establishes the relationship.

## Overlap and Parallel Structures

Academic Periods that are not in an ancestor-descendant relationship may overlap.

They may also have identical date ranges.

This supports legitimate calendar structures such as:

```text
Semester 1: 2026-09-03 through 2027-01-29
Quarter 1:  2026-09-03 through 2026-11-06
```

when both are root periods.

It also supports:

* marking periods and progress windows;
* semester summaries and quarter periods;
* examination windows;
* custom reporting windows;
* and different institutional views over the same dates.

Core must not require all periods to form one non-overlapping partition.

### Overlap does not create hierarchy

If one period’s dates contain another’s, Core does not infer a parent.

If two periods have identical dates, Core does not treat them as duplicates unless they reuse the same `period_id`.

Identity and relationships are explicit.

## Sibling Ordering

Each period has an explicit positive integer `sequence`.

Sequence is interpreted among periods with the same parent.

Root periods are siblings beneath the school year.

### Sequence invariants

Sibling sequence values must be:

* positive integers;
* explicit;
* deterministic;
* and unique among siblings.

Sequence values need not be contiguous.

For example, the following is valid:

```text
10
20
30
```

This allows deliberate insertion without requiring silent renumbering.

Core must reject duplicate sequence values among siblings.

### Sequence meaning

Sequence controls deterministic:

* display;
* navigation;
* and hierarchy traversal.

It does not determine:

* Grade weight;
* calculation precedence;
* date precedence;
* lifecycle precedence;
* or which period is current.

Core must not infer sequence from:

* period ID;
* label;
* type;
* date;
* filesystem order;
* or JSON object order.

## Lifecycle

The initial Academic Period lifecycle vocabulary is:

```text
planned
active
closed
cancelled
```

Lifecycle is explicit administrative metadata.

### `planned`

The period has been defined but is not yet in active administrative use.

### `active`

The period is currently in administrative use.

Several periods may be active simultaneously.

For example:

* Semester 1;
* Marking Period 1;
* and Progress Window 1

may overlap and all be active.

Core must not assume exactly one active period.

### `closed`

The calendar or reporting period has ended or has been administratively closed.

`closed` does not mean:

* Grades are locked;
* Grades are finalized;
* reports are immutable;
* no late work may be entered;
* no reassessment may occur;
* or Meridian may not recalculate.

Those are Meridian-owned states and policies.

### `cancelled`

The period was defined but should no longer be selected for new downstream membership.

The record remains preserved for:

* historical explanation;
* existing references;
* and calendar revision history.

A cancelled period must not be deleted or reused for another meaning.

### Lifecycle does not mutate automatically

Core must not change lifecycle because:

* the current date passes `start_date`;
* the current date passes `end_date`;
* the active school year is opened or closed;
* a parent is activated or closed;
* a report is generated;
* or a Grade snapshot is created.

Core may provide diagnostics that compare lifecycle with dates.

Diagnostics must not silently mutate canonical state.

### Parent and child lifecycle

Parent and child periods may temporarily have different lifecycle states.

For example:

* a semester may remain `active` while one child marking period is `closed`;
* a future child period may remain `planned` while its parent is `active`;
* or a cancelled progress window may remain beneath an active marking period.

Lifecycle does not propagate automatically through hierarchy.

Consumers must evaluate the selected period’s own lifecycle.

## Calendar Revision and Historical Preservation

Academic-period updates must be revision-aware and append-preserving.

Core will represent each accepted Academic Period Calendar revision as an immutable canonical revision.

Conceptually:

```text
school_year
    -> calendar revision 1
    -> calendar revision 2
    -> calendar revision 3
```

One revision is identified as current through explicit Core state.

### Calendar revision

Each canonical calendar revision has a positive integer:

```text
calendar_revision
```

Revisions increase monotonically for one school year.

They need not be contiguous when an attempted revision is abandoned before canonical persistence.

A new canonical revision is required for any accepted change to:

* label;
* dates;
* parent;
* sequence;
* lifecycle;
* period membership in the calendar;
* or other shared period metadata.

### Immutable revisions

After a calendar revision is canonically persisted:

* its serialized contents must not change;
* its revision number must not be reused;
* and it must remain available for historical interpretation.

A later correction creates a new revision.

Core must not overwrite a prior canonical calendar revision in place.

### Stable period identity across revisions

A period retains the same identity across calendar revisions when its:

```text
school_year + period_id
```

remain unchanged.

Permitted revised fields include:

* label;
* start date;
* end date;
* parent;
* sequence;
* lifecycle;
* and compatible descriptive metadata.

The period type is not mutable after first canonical introduction.

### Period removal and ID reuse

Once a period ID appears in a canonical calendar revision, later revisions must not:

* remove the period from historical existence;
* reuse the ID for another concept;
* or silently replace it.

A period no longer intended for use becomes:

```text
cancelled
```

This preserves referential integrity.

Later calendar revisions continue to carry the period so historical and current references remain resolvable.

### Optimistic concurrency

A calendar update must identify the expected current revision.

If the actual current revision differs, the update fails as a stale-write conflict.

Core must not silently overwrite a newer calendar revision.

The exact public API belongs to implementation work, but the semantic requirement is equivalent to:

```text
write revised calendar only if current_revision == expected_revision
```

### Meridian reproducibility

A Meridian Grade snapshot or formal report that depends on period metadata must preserve:

* the complete Academic Period reference;
* and the Core calendar revision used.

A later Core calendar correction must not silently reinterpret a historical Meridian snapshot.

Current teacher-facing views may resolve the latest calendar revision.

Historical calculations must remain tied to their recorded revision.

## Calendar Storage Authority

Canonical Academic Period Calendar revisions are Core-owned records.

They must live in one deterministic Core-owned school-year location.

A conceptual layout is:

```text
<workspace>/
  settings/
    academic_periods/
      2026-2027/
        revisions/
          1.json
          2.json
          3.json
        current.json
```

The exact:

* path names;
* filenames;
* pointer representation;
* sharding;
* and helper APIs

belong to issue #158.

The architecture requires:

* one canonical location per school year;
* immutable revision records;
* explicit current revision;
* safe path construction;
* and no duplication beneath class folders.

### Calendar and active-school-year state remain separate

The existing file:

```text
settings/school_year.json
```

continues to represent active workspace school-year state.

The academic-period calendar is a separate resource.

Opening a school year must not:

* create a calendar;
* create default periods;
* select a current calendar revision;
* or activate periods.

Closing a school year must not:

* create a new calendar revision;
* close periods;
* cancel periods;
* lock Grades;
* or delete the calendar.

### Calendar and class metadata remain separate

Creating or updating:

```text
classes/<class_id>/class.json
```

must not:

* create an academic-period calendar;
* add periods;
* modify periods;
* or assign the class to particular periods.

The class’s `school_year` establishes which Core calendar namespace is applicable.

Whether the class uses particular periods belongs to Meridian.

## Core and Meridian Ownership Boundary

### Core owns

Core owns:

* school-year validation;
* Academic Period Calendar identity;
* immutable calendar revisions;
* current calendar-revision state;
* Academic Period identity;
* Academic Period references;
* period type;
* label;
* inclusive date range;
* parent-child hierarchy;
* sibling sequence;
* lifecycle;
* calendar validation;
* canonical calendar persistence;
* revision conflict detection;
* and module-neutral calendar queries.

### Meridian owns

Meridian owns:

* whether a class uses a period;
* Grade-item period membership;
* source-result period membership where separately modeled;
* direct versus inherited membership;
* membership in more than one period;
* Grade-item categories;
* weighting;
* parent-period rollup;
* marking-period calculation;
* semester calculation;
* course calculation;
* progress-report inclusion;
* exclusions;
* reassessment policy;
* late-work policy;
* Grade locking;
* Grade finalization;
* calculation history;
* snapshots;
* reporting;
* and teacher-facing grading-period workflow.

### Producing modules own

ScoreForm, Quillan, Concord, and Portia own their native:

* assignments;
* Activities;
* Events;
* Supports;
* results;
* attempts;
* reviews;
* Scores;
* interventions;
* timestamps;
* and lifecycle semantics.

Producer modules do not need to add Academic Period fields to their canonical records merely to participate in Meridian.

### Core does not own Grade-item membership

Core must not add universal Academic Period membership to:

* `ModuleWorkRef`;
* Academic Work Registration;
* Publication Record;
* ScoreForm assignment;
* ScoreForm attempt;
* Quillan assignment;
* Quillan review;
* Concord Activity;
* Concord Score;
* Portia Event;
* Portia Support Process;
* producer manifest;
* standards usage record;
* or route registration.

Meridian establishes explicit membership under its own contract.

Conceptually:

```text
Meridian Grade Item
    -> AcademicPeriodRef
```

or:

```text
Meridian Period Membership
├── grade_item_id
├── AcademicPeriodRef
├── membership_kind
├── provenance
└── lifecycle
```

The exact Meridian schema is outside this ADR.

## Explicit Membership

Grade-item period membership must be explicit and auditable.

Core date ranges may assist Meridian or a teacher-facing interface.

They do not create membership automatically.

### No universal date inference

Core must not infer period membership from:

* assignment creation;
* due date;
* completion date;
* attempt date;
* scan timestamp;
* review timestamp;
* Score timestamp;
* publication timestamp;
* Event date;
* or whether a date falls within a period.

Meridian may offer a suggestion such as:

```text
The assignment due date falls within Marking Period 1.
Assign it there?
```

Accepting that suggestion creates explicit Meridian-owned membership.

### Zero, one, or several memberships

A Meridian Grade item may belong to:

* no Academic Period;
* one Academic Period;
* or several Academic Periods

when Meridian’s policy permits it.

For example, one item might be assigned directly to:

```text
Marking Period 1
```

and also participate in:

```text
Semester 1
```

through a Meridian-owned rule or explicit membership.

Core does not choose the relationship.

### Ancestor membership is not automatic

Membership in a child period does not create Core-owned membership in every ancestor.

For example:

```text
Grade Item
    -> Marking Period 1
```

does not automatically create:

```text
Grade Item
    -> Semester 1
```

Meridian determines whether:

* child membership implies parent inclusion;
* parent calculations aggregate child calculations;
* Grade items are directly assigned to both;
* or parent periods use independent membership.

This prevents the Core hierarchy from becoming hidden Grade policy.

### Period lifecycle and membership

Core defines the meaning of period lifecycle.

Meridian enforces membership policy.

A `cancelled` period should not accept new Meridian membership.

Existing membership may remain for historical explanation.

A `closed` period may or may not permit membership changes depending on Meridian’s:

* late-work policy;
* reassessment policy;
* locking state;
* and teacher authorization.

Core does not make that decision.

## Class Use of the Calendar

Classes relate to a calendar through existing class metadata:

```text
class.json
    -> school_year
    -> Academic Period Calendar
```

A class may use:

* all periods;
* a subset of periods;
* or no periods.

Examples include:

* a full-year English class using four marking periods and two semesters;
* a semester elective using Semester 1 and its child periods;
* a short course using one custom period;
* a non-graded workflow using no academic periods;
* or a class whose calendar has not yet been configured.

Core does not store class-period activation or selection.

That belongs to Meridian or another future module with a concrete use case.

## Current-Period Queries

Core may provide neutral queries such as:

```text
periods for school year
root periods
children of period
ancestors of period
descendants of period
periods containing a date
periods by type
periods by lifecycle
```

A query for periods containing one date returns a collection.

Core must not assume exactly one current period.

For example, on one date the following may all apply:

* Semester 1;
* Marking Period 1;
* Progress Window 1;
* and a custom examination window.

A consumer may select a preferred period by:

* type;
* hierarchy;
* class configuration;
* or explicit teacher choice.

That selection is not a universal Core rule.

## Cross-Year Rules

Every Academic Period belongs to exactly one school year.

Parent-child relationships must remain within that school year.

A period in:

```text
2026-2027
```

cannot have a parent in:

```text
2027-2028
```

The same `period_id` may be reused in another school year because complete identity includes `school_year`.

For example:

```text
2026-2027 + semester_1
2027-2028 + semester_1
```

are distinct.

Academic-period hierarchy does not represent domain-specific cross-year continuity.

For example, a Portia Support Process that continues into a new school year remains governed by Portia’s successor-work relationships.

It does not become one Academic Period spanning multiple school years.

Meridian may compare periods across years through explicit period references and calendar revisions without merging their identities.

## Validation Invariants

The detailed implementation must validate the complete calendar, not only isolated period records.

Validation must reject:

* invalid school-year strings;
* invalid period IDs;
* duplicate period IDs within one school year;
* unsupported schema versions;
* unsupported period types;
* blank labels;
* invalid date values;
* dates outside the school year’s two named calendar years;
* incomplete date pairs;
* start dates later than end dates;
* invalid parent references;
* self-parenting;
* cycles;
* cross-school-year parents;
* child dates outside parent dates;
* invalid sequence values;
* duplicate sibling sequences;
* invalid lifecycle values;
* invalid calendar revisions;
* reuse of an existing period ID for another type;
* removal of a previously canonical period;
* stale expected revisions;
* naive audit timestamps;
* duplicate JSON keys;
* and unknown top-level fields unless a deliberate compatible-extension policy is adopted.

Validation must permit unrelated periods to:

* overlap;
* share dates;
* use different types over the same date range;
* and exist in parallel root structures.

Validation must not silently:

* generate IDs;
* infer parents;
* infer sequence;
* infer period type;
* alter labels;
* normalize local terminology;
* adjust dates;
* insert default periods;
* renumber siblings;
* activate or close periods;
* assign classes;
* or assign Grade items.

## Failure and Recovery

The calendar persistence implementation must follow these principles.

### Validate before persistence

The complete proposed calendar revision must be validated before canonical state changes.

A failure involving:

* one invalid period;
* a duplicate ID;
* a missing parent;
* a cycle;
* an invalid date;
* or a sequence conflict

rejects the proposed revision.

### Immutable revision first

A new immutable revision must be written and durably closed before the current-revision state is updated.

The conceptual order is:

```text
validate proposed calendar
    -> write immutable revision
    -> verify persisted revision
    -> update current-revision state
```

### Failed write preserves prior current state

If writing the new revision fails, the previous current calendar remains current.

If immutable revision creation succeeds but current-pointer update fails:

* the new revision exists but is not current;
* the prior revision remains current;
* and audit or repair tooling must report the orphan revision explicitly.

Repair must not silently promote an orphan revision without an explicit user or caller decision.

### Reads are nonmutating

Loading or querying a calendar must not:

* repair it automatically;
* create defaults;
* update lifecycle;
* change the current revision;
* or rewrite serialized records.

### Missing references remain explicit

A Meridian record referencing:

* a missing school year;
* a missing period;
* an unavailable calendar revision;
* or an invalid period reference

must surface an unresolved-reference condition.

It must not silently:

* substitute a similarly named period;
* select the current period;
* or move membership to another school year.

### Repair does not invent calendars

Core repair tooling may:

* verify revision records;
* validate current-revision state;
* detect orphan revisions;
* restore a current pointer to an explicitly selected valid revision;
* and report invalid records.

Repair must not invent:

* district dates;
* default semesters;
* default marking periods;
* hierarchy;
* or Grade-item membership.

## Core and Module Dependency Direction

Academic-period infrastructure remains in `pds-core`.

The intended dependency direction is:

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
* or Meridian

to validate or load the shared academic calendar.

Producer modules need not depend on the Academic Period APIs unless they have a concrete teacher-facing use.

Meridian is the primary initial consumer.

## Consequences

### Positive consequences

* Paper Data Suite gains one shared period identity model.
* The model supports marking periods, semesters, quarters, trimesters, progress windows, and custom periods.
* Core does not hard-code one district calendar.
* Period IDs remain stable when labels or dates change.
* School-year identity is reused rather than duplicated.
* Classes share one school-year calendar instead of copying period definitions.
* Parent-child relationships are explicit.
* Hierarchy remains calendar structure rather than Grade policy.
* Unrelated periods may overlap.
* Parallel semester, quarter, marking-period, and progress-window structures are supported.
* Sibling display order is deterministic.
* Several periods may be active simultaneously.
* Calendar revisions are immutable and historically inspectable.
* Stale updates cannot silently overwrite newer changes.
* Meridian snapshots can preserve exact calendar context.
* Producer modules do not require period fields in native records.
* Period membership remains explicit and auditable.
* Grade calculations remain outside Core.
* A school year or class can exist before its calendar is configured.
* Opening or closing a school year remains free of hidden calendar side effects.
* Future modules may reference the same period identities without adopting Meridian’s grading model.

### Negative consequences

* Teachers or future import tools must configure calendars explicitly.
* Core must maintain immutable calendar revisions and current-revision state.
* Calendar corrections create new revisions rather than overwriting one file.
* Cancelled periods remain visible in historical data.
* Overlapping period structures may require careful user-interface presentation.
* Several periods may contain the same date.
* Core cannot provide one universal “current marking period” query.
* Meridian must create and maintain explicit membership records.
* Hierarchy alone does not calculate parent Grades.
* Consumers must preserve calendar revision where historical reproducibility matters.
* Missing calendars and unresolved period references require explicit handling.
* The suite gains additional identity, validation, and recovery concepts.

### Risks and mitigations

#### Core hierarchy becomes hidden grading policy

**Risk:** A consumer assumes that Grade items in a child period automatically contribute to the parent.

**Mitigation:** Parent-child relationships express calendar organization only. Meridian owns membership and aggregation.

#### Calendar definitions diverge by class

**Risk:** Every class stores its own marking-period dates.

**Mitigation:** Core owns one school-year-scoped calendar. Classes relate to it through existing school-year metadata.

#### Period labels become identifiers

**Risk:** Renaming “MP1” breaks references.

**Mitigation:** Durable identity uses `school_year + period_id`. Labels are display metadata.

#### Overlap is treated as corruption

**Risk:** Valid semesters, marking periods, progress windows, and custom periods cannot coexist.

**Mitigation:** Unrelated overlap and identical date ranges are allowed. Only parent-child containment is mandatory.

#### Dates become automatic Grade-item membership

**Risk:** Assignments are silently assigned based on due or result dates.

**Mitigation:** Core never creates membership from dates. Meridian may offer explicit teacher-controlled suggestions.

#### Closing a period locks Grades

**Risk:** Core `closed` lifecycle unexpectedly prevents grading changes.

**Mitigation:** Calendar lifecycle and Meridian locking/finalization are separate states.

#### School-year operations mutate periods

**Risk:** Opening or closing a school year creates or alters the calendar.

**Mitigation:** School-year state and academic-period persistence are separate explicit operations.

#### Calendar correction changes historical reports

**Risk:** Revised dates or hierarchy silently reinterpret an earlier report.

**Mitigation:** Calendar revisions are immutable. Meridian snapshots preserve the revision used.

#### Concurrent edits lose changes

**Risk:** Two callers update the same calendar and one silently overwrites the other.

**Mitigation:** Updates require the expected current revision. Stale writes fail.

#### Period ID is reused after cancellation

**Risk:** Existing references begin resolving to another concept.

**Mitigation:** Period IDs are never reused within the school year. Cancellation preserves the original record.

#### Custom periods create uncontrolled schemas

**Risk:** Every district adds incompatible top-level fields.

**Mitigation:** `custom` is a shared type using the normal Core model. Local meaning is expressed through labels and limited compatible metadata.

## Alternatives Considered

### Meridian owns all period definitions privately

Rejected because:

* period identity is shared suite infrastructure;
* classes already use Core-owned school-year identity;
* future modules may need the same references;
* and private Meridian strings would create competing period identities.

Meridian owns membership and Grade policy, not the shared calendar.

### Hard-code four marking periods and two semesters

Rejected because districts may use:

* quarters;
* trimesters;
* six marking periods;
* semester-only structures;
* custom cycles;
* or other calendars.

### Store period definitions in every `class.json`

Rejected because:

* the calendar is normally shared across classes;
* definitions would be duplicated;
* updates could diverge;
* and class metadata would become a Grade-calendar schema.

### Add one period field to producer work or results

Rejected because:

* producer records remain module-owned;
* one item may belong to several periods;
* membership is Meridian policy;
* and source dates or labels are not durable shared references.

### Infer period membership from dates

Rejected as a Core rule because:

* late work may remain in the original period;
* reassessments may count elsewhere;
* due date and grading period may differ;
* Activities may span periods;
* and progress windows may overlap.

Meridian may provide explicit assistance based on dates.

### Represent the school year as an Academic Period

Rejected because Core already has a school-year identity and state contract.

Duplicating the school year as a period would create two authorities and complicate complete period identity.

### Require periods to form one non-overlapping partition

Rejected because:

* semesters and quarters may coexist;
* progress windows may overlap marking periods;
* custom reporting windows may overlap other periods;
* and one date may legitimately belong to several calendar structures.

### Infer hierarchy from date containment

Rejected because:

* parallel structures may overlap or contain one another;
* identical dates do not establish institutional meaning;
* and explicit relationships are more auditable.

### Allow multiple parents

Rejected for the initial Core model because it would create a general graph rather than a hierarchy.

Meridian may define additional calculation or inclusion relationships separately.

### Use labels as identity

Rejected because labels are:

* editable;
* potentially duplicated;
* localizable;
* and unsuitable for durable references.

### Use datetime boundaries

Rejected for the initial period model because academic reporting periods are day-based.

Bell schedules, deadlines, and time-specific events belong to other contracts.

### Automatically activate and close periods based on dates

Rejected because:

* low-level Core records should not mutate based on the system clock;
* administrative state may differ from calendar dates;
* and automatic mutation weakens reproducibility.

### Close all periods when the school year closes

Rejected because active-school-year workflow and calendar lifecycle are separate.

Closing the year must not silently rewrite period definitions.

### Put Grade locking in Core lifecycle

Rejected because calendar closure is not equivalent to:

* Grade lock;
* Grade finalization;
* report submission;
* or institutional approval.

Those belong to Meridian.

### Keep only one mutable current calendar file

Rejected because:

* a correction would overwrite historical context;
* Meridian snapshots could become difficult to explain;
* stale concurrent updates could be destructive;
* and current calendar bytes would be the only surviving interpretation.

Core will preserve immutable calendar revisions.

### Store full Grade-item membership in Core

Rejected because:

* membership belongs to grading policy;
* not every Core consumer is a gradebook;
* class and Grade-item use may differ;
* and Core hierarchy must remain module-neutral.

## Required Follow-Up

This decision governs later Core work under umbrella issue `#154`.

### `#157` — Add academic-period models and serialization

Implement:

* `AcademicPeriod`;
* `AcademicPeriodRef`;
* `AcademicPeriodCalendar`;
* calendar revisions;
* period types;
* lifecycle values;
* safe period identity;
* inclusive date parsing;
* hierarchy validation;
* sibling ordering;
* immutable type rules;
* dictionary conversion;
* and complete calendar validation.

The implementation must reuse Core’s existing school-year validator.

### `#158` — Add academic-period workspace storage and query APIs

Implement:

* deterministic Core-owned calendar paths;
* immutable calendar-revision persistence;
* current-revision state;
* atomic and exclusive writes;
* optimistic concurrency;
* safe loading;
* listing;
* lookup;
* hierarchy traversal;
* date-containment queries;
* lifecycle and type queries;
* and explicit missing-calendar behavior.

Opening or closing a school year must not create or modify period calendars.

Creating or editing class metadata must not create or modify period calendars.

### `#162` — Add the derived academic and reporting catalog

The derived catalog may index:

* school year;
* period ID;
* period type;
* dates;
* parent;
* sequence;
* lifecycle;
* and current calendar revision

where useful for Meridian discovery.

Canonical Core calendar revisions remain authoritative.

### `#163` — Add registry validation, audit, and catalog-repair commands

Validation and audit should detect:

* malformed calendars;
* unsupported schemas;
* duplicate IDs;
* invalid dates;
* missing parents;
* cycles;
* containment failures;
* sibling-order conflicts;
* invalid lifecycle;
* invalid revision state;
* orphan revisions;
* stale current pointers;
* and unresolved period references where included in shared audits.

Repair must not invent calendar definitions or Grade-item membership.

### `#165` — Document the Core integration contract and release `pds-core` v0.6.0

Document:

* calendar configuration;
* school-year scope;
* period identity;
* period references;
* date semantics;
* hierarchy;
* overlap;
* sequence;
* lifecycle;
* immutable revisions;
* storage;
* queries;
* recovery;
* and the Core/Meridian ownership boundary.

## References

### PDS Core

* [`0001-adopt-pds2-page-locator-routing.md`](0001-adopt-pds2-page-locator-routing.md)
* [`0002-adopt-typed-reportable-data-publication-registry.md`](0002-adopt-typed-reportable-data-publication-registry.md)
* [`README.md`](README.md)
* [`../roster_workspace_contract.md`](../roster_workspace_contract.md)
* [`../../pds_core/school_years.py`](../../pds_core/school_years.py)
* [`../../pds_core/class_metadata.py`](../../pds_core/class_metadata.py)
* `Paper-Data-Suite/pds-core#154`
* `Paper-Data-Suite/pds-core#156`
* `Paper-Data-Suite/pds-core#157`
* `Paper-Data-Suite/pds-core#158`

### Quillan

* `Paper-Data-Suite/pds-quillan`
* `Paper-Data-Suite/pds-quillan/docs/assignment_reporting_contract.md`

### Concord

* `Paper-Data-Suite/pds-concord`
* `Paper-Data-Suite/pds-concord/docs/decisions/0008-separate-review-moderation-scoring-grading-and-reporting.md`

### Portia

* `Paper-Data-Suite/pds-portia`
* `Paper-Data-Suite/pds-portia/README.md`

### Meridian

* `Paper-Data-Suite/pds-meridian`

## Notes

This ADR establishes architecture and invariants.

It does not define:

* the final serialized Academic Period schema;
* exact filenames;
* exact path helpers;
* public Python method names;
* SQLite tables;
* CLI syntax;
* calendar-import formats;
* Meridian membership schemas;
* Grade calculations;
* locking workflows;
* or report formats.

Those details belong to the implementation and integration issues governed by this decision.

Implementation convenience must not weaken these invariants:

* the existing school year remains the containing identity;
* Academic Period identity is school-year scoped;
* period IDs are distinct from labels;
* period type is stable;
* date ranges are explicit and inclusive;
* hierarchy is explicit;
* unrelated overlap is permitted;
* sequence is deterministic but not Grade precedence;
* lifecycle is explicit and not clock-driven;
* calendar revisions are immutable;
* Core owns period definitions;
* Meridian owns Grade-item membership and grading policy;
* producer dates do not create membership;
* and school-year or class-metadata operations do not mutate calendars.
