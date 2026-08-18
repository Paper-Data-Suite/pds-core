# ADR 0004: Adopt a Neutral Grouping-Signal Interchange

**Status:** Accepted
**Date:** August 17, 2026
**Decision owners:** Paper Data Suite maintainers
**Applies to:** `pds-core`, `pds-meridian`, `pds-concord`, and suite-level tooling that discovers or protects Core exchange data
**Related issue:** `Paper-Data-Suite/pds-core#179`
**Umbrella issue:** `Paper-Data-Suite/pds-core#177`

## Context

Paper Data Suite needs a way to pass a small amount of teacher-controlled
planning information between modules without turning one module into another
module's runtime dependency and without moving academic or grouping policy into
Core.

The immediate use case is future group planning:

```text
Meridian
   |
   v
Core grouping_signal_set_v1
   |
   v
Concord
```

Meridian will be able to interpret selected academic evidence under explicit
teacher policy and derive temporary ordinal bands. Concord will be able to use
a selected signal as one optional input to a teacher-reviewed GroupPlan. Those
responsibilities must remain separate.

A direct Meridian-to-Concord dependency would make Concord's planning features
dependent on Meridian's installation and private data model. Letting Concord
read Meridian's internal records would also allow academic policy and schema
changes to leak across repository boundaries. Moving proficiency or grouping
algorithms into Core would solve the dependency problem by creating a more
serious ownership problem: Core would become either a grading engine or a group
formation engine.

The shared representation therefore needs to be deliberately smaller than both
Meridian's academic state and Concord's planning state.

It must also support a teacher-authored signal with neither Meridian nor
Concord installed. Academic derivation is one source of a signal, not a
requirement for the contract.

### Existing Core conventions

Core already owns shared identifiers, workspace and class identity, rosters,
Academic Periods, PDS2 routing, source provenance, Academic Work Registration,
Publication Records, and strict shared JSON contracts. Existing contracts use
explicit schema and record-type values, exact field sets, timezone-aware
timestamps, deterministic serialization, and rejection rather than inference.

The grouping-signal contract follows those conventions while remaining a new,
independent interchange surface. It does not modify PDS2, rosters, Academic
Periods, publication, or producer-native records.

## Decision

Adopt `grouping_signal_set_v1` as a Core-owned, strict, immutable interchange
contract representing contextual ordinal student signals for one Core class.

The contract name is:

```text
grouping_signal_set_v1
```

Its serialized discriminator is:

```json
{
  "schema_version": "1",
  "record_type": "grouping_signal_set"
}
```

The detailed version-1 wire contract is normative in
[`../grouping_signal_set_v1.md`](../grouping_signal_set_v1.md).

### Dependency direction

Core owns the interchange language and must not import Meridian or Concord.

A producer may create a conforming signal through Core without depending on a
consumer. A consumer may read a conforming signal through Core without
depending on the producer that created it.

For the planned integrations:

```text
Meridian -> Core grouping_signal_set_v1 -> Concord
```

This is a producer-to-neutral-interchange-to-consumer data flow, not a shared
write path. Specifically:

- Meridian owns academic interpretation and optional signal derivation;
- Core owns the shared signal representation, validation, canonicalization,
  exchange persistence, and class/roster diagnostics;
- Concord owns GroupPlans, planning strategies, teacher approval, Groups, and
  GroupMemberships; and
- the suite shell owns no grouping policy.

There is no direct Meridian-to-Concord runtime or import dependency.

### Signal identity and immutability

The logical identity of one signal set is:

```text
(class_id, signal_set_id)
```

A signal set is an immutable snapshot. A changed derivation, corrected import,
new evidence state, different band boundary, changed band count, changed
coverage, or teacher edit produces a new `signal_set_id`.

Version 1 has no mutable revision, supersession chain, `latest`, `current`,
`active`, or head pointer. A consumer selects an exact signal set explicitly.

Future Core exchange storage will bind the canonical signal bytes by SHA-256.
That digest is storage/integrity metadata and is not embedded in the record
being hashed.

The human-editable CSV form represents one selected dimension. Exporting one
dimension from a multi-dimension signal therefore creates a projection, not an
alternate serialization of the complete source signal. Re-importing that
projection as a standalone signal requires a new `signal_set_id`; the reduced
contents cannot reuse the immutable identity of the multi-dimension source.

For an already single-dimension signal, identity-preserving CSV round trip is
permitted only when the CSV preserves every canonical value needed to reproduce
the exact same snapshot, including `created_at` and complete source provenance.
An importer must not generate a new `created_at` while retaining the original
`signal_set_id`. Any material CSV change requires a new signal-set identity.

### Contextual ordinal bands

For a dimension with `band_count = N`, a band is an integer in the inclusive
range `1..N`.

The band establishes ordering only inside the exact signal set and dimension.
It does not establish equal numeric distance and does not carry universal
academic meaning.

A band is not:

- a Grade, percentage, point value, or rubric score;
- a shared proficiency category;
- an ability, intelligence, readiness, disability, language, behavior, or
  demographic label;
- a permanent learner attribute; or
- a final grouping instruction.

Core validates the representation. It does not decide what a dimension means,
how many bands should exist, where boundaries should fall, or what academic
evidence should contribute.

### Dimensions

A signal set declares one or more dimensions. Each dimension has an exact
`dimension_id` and `band_count`. Dimension identifiers are stable only within
the contract's intended provenance; they are not a Core-owned global ontology.
Every declared dimension must have at least one student-band entry. An entirely
empty dimension is omitted rather than represented as a 100%-missing dimension.

A multi-dimension signal set permits one source snapshot to expose several
bounded planning dimensions without repeating top-level provenance. Consumers
must explicitly choose the dimension they use. Bands from different dimensions
must not be treated as one common scale.

### Student coverage

Entries use exact `student_id` values. Names are not part of the contract and
must not be used for identity resolution.

Partial coverage is valid. Absence of a `(student_id, dimension_id)` entry
means only that no band is present for that student in that dimension in that
exact signal set. It does not mean zero, lowest band, failure, absence,
unenrollment, or permission to omit the student from a later plan.

Core's later workspace-aware diagnostics will report missing, unknown,
wrong-class, and duplicate identities without silently dropping, remapping, or
completing entries.

### Provenance

Every signal contains a small, strict `source` object. Version 1 distinguishes:

```text
teacher_authored
module_generated
```

A module-generated signal identifies the producing module and exact upstream
snapshot with SHA-256 provenance. A teacher-authored signal may have no bound
upstream snapshot, or may bind an exact imported source artifact when such a
binding is available.

The upstream `source.snapshot_digest` is distinct from the SHA-256 digest of
the canonical grouping-signal record itself.

The `source` object is intentionally not an extension bag. Rich academic
calculation state, evidence, explanations, free-form notes, and downstream
planning state remain outside the interchange.

### Privacy

A populated grouping signal is teacher-restricted educational data even though
it excludes raw academic values. It contains class identity, student IDs,
relative planning signals, and educational provenance.

Signal values must not be reproduced by default in logs, troubleshooting
bundles, passive attention summaries, PDS2 payloads, route registrations,
packet or artifact metadata, AcademicResult manifests, or Publication Records.
Repository examples and fixtures must be synthetic.

### Core invariants

The following are architectural invariants:

1. Core does not calculate proficiency.
2. Core does not decide what academic evidence matters.
3. Core does not choose band boundaries or default band counts.
4. Core does not infer a missing student's band.
5. Core does not form Groups or approve GroupPlans.
6. Core does not assign GroupMembership.
7. Core does not infer Scores from bands.
8. Bands are contextual ordinal values, not Grades or permanent labels.
9. Signal sets are immutable and have no automatic latest/current selection.
10. Student identity is exact `student_id`, never name matching.
11. Partial roster coverage is explicit and never silently repaired.
12. Every declared dimension contains at least one student-band entry.
13. A reduced CSV projection cannot reuse the immutable identity of its
    multi-dimension source signal.
14. An identity-preserving single-dimension CSV round trip preserves
    `created_at`, source provenance, and all other canonical signal contents.
15. Raw academic values do not cross the interchange boundary.
16. Final grouping decisions do not cross back into the signal snapshot.
17. Teacher-authored signals are a first-class use case.
18. Core works without Meridian or Concord installed.
19. Meridian signal generation must work without Concord installed.
20. Concord signal consumption must work without Meridian installed.
21. Every downstream write remains owned by the repository that owns that
    record type.

## Ownership Boundaries

| Responsibility | Owner |
| --- | --- |
| `grouping_signal_set_v1` wire contract | Core |
| shared identifier validation | Core |
| structural signal validation | Core |
| canonical JSON serialization | Core |
| CSV conversion contract | Core |
| immutable neutral exchange storage | Core |
| canonical signal-byte digest | Core |
| class/roster diagnostics | Core |
| choosing academic evidence | Meridian/teacher |
| determining evidence eligibility | Meridian/teacher |
| proficiency calculation | Meridian |
| choosing an academic dimension | Meridian/teacher |
| choosing number of bands | producer/teacher |
| choosing academic band boundaries | Meridian/teacher |
| tie and missing-academic-evidence policy | Meridian/teacher |
| rich academic derivation/explanation history | Meridian |
| deciding whether to export a signal | teacher through producer workflow |
| direct manual signal authoring | teacher through Core-supported interchange |
| choosing a signal for grouping | teacher/Concord |
| planning strategy and manual placement | Concord |
| GroupPlan lifecycle and approval | Concord/teacher |
| canonical Group and GroupMembership creation | Concord |
| suite-wide launcher/health presentation | suite shell |
| grouping policy in suite shell | prohibited |

## Consequences

### Positive

- Meridian and Concord can interoperate without importing one another.
- Core remains a neutral shared-contract layer rather than a grading or group
  formation engine.
- Teacher-authored files remain valid inputs, preserving manual workflows.
- Immutable exact snapshots make later GroupPlan provenance reproducible.
- Strict minimization reduces accidental disclosure of raw grades and richer
  academic state.
- Concord can qualify signal-based planning against synthetic Core fixtures
  without Meridian installed.
- Meridian can qualify export without Concord installed.

### Costs and constraints

- Producers must retain richer derivation state outside the interchange if they
  need explanations or auditability.
- Consumers cannot infer the academic meaning of a band from the Core record.
- A changed interpretation creates another signal set rather than mutating an
  existing file.
- Partial coverage requires an explicit downstream teacher decision rather than
  automatic completion, while entirely empty declared dimensions are invalid.
- A selected-dimension CSV projection of a multi-dimension signal needs fresh
  signal identity if imported as a standalone signal.
- Identity-preserving CSV round trips of single-dimension signals must preserve
  `created_at`, complete source provenance, and every other canonical value.
- Strict version-1 field sets mean later serialized additions require an
  explicit compatibility/versioning decision.

## Alternatives Considered

### Direct Meridian-to-Concord runtime dependency

Rejected. It would couple Concord planning to Meridian installation, private
models, and release cadence, and would prevent independent synthetic
qualification.

### Store raw grades or percentages in Core for Concord to interpret

Rejected. Core would become a carrier of unnecessary academic detail, Concord
would gain grading-policy responsibilities, and the privacy surface would grow
without improving neutral interoperability.

### Treat shared proficiency labels as band meanings

Rejected. Proficiency categories are policy-dependent. Reusing labels such as
`advanced`, `proficient`, or `below` would turn a contextual planning signal
into a suite-wide academic classification.

### Let Concord query Meridian's private state directly

Rejected. This is another form of direct coupling and would bypass Core's
neutral contract, provenance, and privacy boundary.

### Put final Groups or memberships in the Core interchange

Rejected. Group formation, approval, and canonical membership are Concord
responsibilities. A planning input must not become a grouping decision.

### Put grouping algorithms in Core

Rejected. Random, similar-signal, mixed-signal, manual, and future planning
strategies belong to Concord. Core validates input; it does not optimize groups.

### Use a mutable `current` or `latest` signal

Rejected. Automatic selection could silently change a teacher's planning input
when academic evidence or interpretation changes. Exact immutable identity is
required for reproducibility.

### Use student names instead of exact student IDs

Rejected. Names are display data, can be duplicated or changed, and would
invite ambiguous resolution. The contract uses Core student identity only.

### Require academic signals for Concord grouping

Rejected. Direct Groups, manual planning, and random planning remain valid
first-class Concord workflows. Academic grouping signals are optional.

## Required Follow-Up

Core v0.6.1 issues must implement the accepted contract without changing its
semantics silently:

1. #180 — typed models, validation, and canonical JSON serialization;
2. #181 — human-editable one-dimension CSV import/export;
3. #182 — immutable exchange storage and canonical-byte digest binding;
4. #183 — workspace-aware class and roster identity diagnostics; and
5. #184 — standalone acceptance, backward-compatibility qualification, and the
   v0.6.1 release audit.

Concord v0.3 may consume the public Core contract and synthetic conforming
signals without Meridian installed. Meridian v0.2 may derive and export signals
through Core without Concord installed.

A later suite-level acceptance test may prove the complete
`Meridian -> Core -> Concord` path, but that qualification must not establish a
direct sibling runtime dependency.

## References

- `Paper-Data-Suite/pds-core#177`
- `Paper-Data-Suite/pds-core#179`
- `Paper-Data-Suite/pds-concord#47`
- `Paper-Data-Suite/pds-paper-data-suite/development-plan.md`
- [`../grouping_signal_set_v1.md`](../grouping_signal_set_v1.md)
- [`README.md`](README.md)
- [`0002-adopt-typed-reportable-data-publication-registry.md`](0002-adopt-typed-reportable-data-publication-registry.md)
- [`0003-adopt-hierarchical-academic-period-model.md`](0003-adopt-hierarchical-academic-period-model.md)

## Notes

The repository audit for this decision used `pds-core` main commit
`6c507213618b68a6dd3ea096e1a898201ff029e6` as the implementation baseline.
The accepted contract is additive planning for Core v0.6.1; this ADR does not
claim that the runtime models or exchange store are implemented in v0.6.0.
