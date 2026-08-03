# Academic Registry Integration Guide

This is the active producer-and-consumer guide for the `pds-core` v0.6 academic
registry. It complements the [PDS2 integration guide](pds2_module_integration.md):
PDS2 routing and reportable-data publication are separate integration surfaces.
Accepted [ADR 0002](decisions/0002-adopt-typed-reportable-data-publication-registry.md)
and [ADR 0003](decisions/0003-adopt-hierarchical-academic-period-model.md)
remain authoritative.

## Architecture and ownership

```text
Producer writes authoritative native records
    -> producer writes an immutable, versioned manifest
    -> academic producer registers eligible work
    -> producer publishes the exact manifest revision through Core
    -> Core stores an immutable Publication Record
    -> Core may rebuild its disposable catalog
    -> Meridian discovers candidate publications
    -> Meridian reloads canonical records and verifies the manifest
    -> Meridian applies its own grading or reporting policy
```

```text
Intervention producer writes native records
    -> writes an immutable intervention manifest
    -> publishes intervention_record_set without Academic Work Registration
    -> Meridian may include it in authorized reporting
    -> it does not become a Score, standards rating, or Grade
```

Core owns shared identities and validation; Academic Period identities and
calendars; Academic Work Registration envelopes; publication and withdrawal
envelopes; publication kinds and capabilities; manifest containment and digest
binding; publication identity, revision, supersession, and withdrawal;
canonical registry persistence; producer-facing services; publication
compatibility profiles; the rebuildable catalog; and bounded audit, validation,
and maintenance.

Producing modules own authoritative native records; assignment, Activity,
attempt, Review, Score, intervention, and outcome semantics; producer manifest
schemas; manifest generation and validation; stable record-set identity and
revision rules; source-record contracts; and producer-specific migration.

Meridian owns publication selection and subscriptions; Grade-item membership;
evidence, attempt, reassessment, and exclusion policy; standards proficiency;
conventional and hybrid Grade calculations; weights and categories; Academic
Period membership of Grade items; teacher overrides; Grade history; report
composition and snapshots; audience-aware reporting; and delivery policy.

The application/deployment layer owns trusted package installation, profile-
registry construction, authorization, filesystem permissions, backups and
retention, and which installed producers are enabled. Discovery is not
authorization.

## Routing profiles versus publication profiles

The independently discovered entry-point groups are:

```text
paper_data_suite.modules
paper_data_suite.publication_producers
```

A routing `ModuleProfile` declares routing compatibility, contains a route
handler, and may contain a registration validator. A
`PublicationProducerProfile` has compatibility metadata only: supported
publication schemas, producer contracts, publication kinds, capabilities,
manifest contracts, and source-record contracts. It has no parser or callback.

A routing profile does not make a module a publication producer.
A publication profile does not make a module routable.

## Independent versions

The Core package, routing contract, QR schema, route-registration schema,
failure and resolution schemas, Academic Period schemas, Academic Work
Registration schema and producer contract, Publication Record and withdrawal
schemas, producer manifest contract, source-record contract, publication
compatibility contract, catalog schema, CLI JSON envelope, and producer-native
revisions are independent. Compatibility uses explicit supported-version
membership, not numerical similarity. Core-owned values are listed in the
[v0.6.0 compatibility matrix](releases/v0.6.0.md#compatibility-matrix).

## Academic Periods

The public modules are `pds_core.academic_periods`,
`pds_core.academic_period_queries`, and `pds_core.academic_period_storage`.
`AcademicPeriodRef` is the complete identity:

```text
school_year + period_id
```

`AcademicPeriod` supports `marking_period`, `semester`, `quarter`, `trimester`,
`progress_window`, and `custom`, with `planned`, `active`, `closed`, and
`cancelled` lifecycles. Dates are inclusive. Parents form an explicit acyclic
hierarchy; unique sibling `sequence` values determine display order. Parallel
and overlapping structures are allowed when children remain date-contained by
their parents.

`AcademicPeriodCalendar` is an immutable revision. Transition validation
preserves school year, creation time, existing IDs, and existing period types.
Storage creates revisions exclusively and atomically replaces the explicit
pointer with expected-revision protection:

```text
settings/
  academic_periods/
    <school_year>/
      revisions/
        <calendar_revision>.json
      current.json
```

No calendar or default periods are created automatically. Current state comes
only from `current.json`; Core never selects the greatest revision. Lifecycle
does not change from dates. Opening/closing a school year does not mutate
calendars. Core does not infer Grade-item membership.

This verified synthetic example creates, writes, updates, loads, queries, and
resolves a small calendar:

```python
from dataclasses import replace
from datetime import UTC, date, datetime

from pds_core.academic_period_queries import (
    list_academic_periods_containing_date,
    list_child_academic_periods,
)
from pds_core.academic_period_storage import (
    load_current_academic_period_calendar,
    resolve_academic_period_ref,
    write_academic_period_calendar,
)
from pds_core.academic_periods import (
    ACADEMIC_PERIOD_CALENDAR_RECORD_TYPE,
    ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION,
    AcademicPeriod, AcademicPeriodCalendar, AcademicPeriodRef,
)

now = datetime(2026, 8, 3, 12, tzinfo=UTC)
calendar_v1 = AcademicPeriodCalendar(
    ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION,
    ACADEMIC_PERIOD_CALENDAR_RECORD_TYPE,
    "2026-2027", 1, now, now,
    (
        AcademicPeriod("semester_1", "semester", "Semester 1",
                       date(2026, 8, 20), date(2026, 12, 20), None, 1, "planned"),
        AcademicPeriod("quarter_1", "quarter", "Quarter 1",
                       date(2026, 8, 20), date(2026, 10, 20), "semester_1", 1, "planned"),
    ),
)
write_academic_period_calendar(workspace_root, calendar_v1,
                               expected_current_revision=None)
calendar_v2 = replace(
    calendar_v1, calendar_revision=2,
    updated_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
    periods=tuple(replace(item, lifecycle="active") for item in calendar_v1.periods),
)
write_academic_period_calendar(workspace_root, calendar_v2,
                               expected_current_revision=1)
current = load_current_academic_period_calendar(workspace_root, "2026-2027")
assert current is not None and current.calendar_revision == 2
assert [item.period_id for item in list_child_academic_periods(current, "semester_1")] == ["quarter_1"]
assert len(list_academic_periods_containing_date(current, date(2026, 9, 1))) == 2
assert resolve_academic_period_ref(
    workspace_root, AcademicPeriodRef("2026-2027", "quarter_1")
).label == "Quarter 1"
```

## Academic Work Registration

The public modules are `pds_core.academic_work_registrations`,
`pds_core.academic_work_registration_storage`, and
`pds_core.registry_services`. Registration explicitly declares that an
existing `ModuleWorkRef` may participate in academic grading or reporting.
That complete reference remains the identity; there is no registration ID.

Each immutable schema-`"1"` revision stores the record type, registration
revision, producer contract version, title snapshot, work kind, academic
intent, lifecycle, timestamps, and source-record references. Storage is:

```text
registry/
  work/
    <class_id>/
      <module_id>/
        <work_id>/
          revisions/
            <registration_revision>.json
          current.json
```

History is immutable and selection is explicit. Storage writers are strict and
use expected-revision protection. Services are idempotent for exact replay and
return a structured `disposition` (`created`, `existing`, or `updated`).

```python
from pds_core.registry_services import (
    AcademicWorkRegistrationRequest,
    register_academic_work,
    update_academic_work_registration,
)
from pds_core.routes import module_work_dir
from pds_core.routing_models import ModuleRecordRef, ModuleWorkRef

work = ModuleWorkRef("quillan", "english12_p4", "personal_narrative")
module_work_dir(workspace_root, work).mkdir(parents=True)
request = AcademicWorkRegistrationRequest(
    work=work, producer_contract_version="assignment_v2",
    title="Personal Narrative", work_kind="assignment",
    academic_intent="summative", lifecycle="active",
    source_records=(ModuleRecordRef(
        "quillan", "assignment", "personal_narrative", "2"
    ),),
)
created = register_academic_work(workspace_root, request)
assert created.disposition == "created"
assert register_academic_work(workspace_root, request).disposition == "existing"
update = AcademicWorkRegistrationRequest(
    work=work, producer_contract_version="assignment_v2",
    title="Personal Narrative Final", work_kind="assignment",
    academic_intent="summative", lifecycle="closed",
    source_records=request.source_records,
)
updated = update_academic_work_registration(
    workspace_root, update, expected_current_revision=1
)
assert updated.disposition == "updated"
assert updated.registration.registration_revision == 2
```

Registration metadata does not determine Grade inclusion, category or weight,
points, attempt selection, proficiency, period membership, or audience.

## Typed Publication Records

The public modules are `pds_core.publication_records`,
`pds_core.publication_storage`, and `pds_core.registry_services`. Each immutable
record carries publication ID; work; optional source record; publication kind;
capabilities; record-set ID and revision; manifest contract, path, digest
algorithm, and digest; publication time; registration revision; and predecessor.

Kinds are `academic_result_set` and `intervention_record_set`. Academic
capabilities are `points`, `question_evidence`, `multiple_attempts`,
`standards_ratings`, `criterion_scores`, and `moderated_scores`. Intervention
capabilities are `intervention_history`, `intervention_status`, and
`intervention_outcomes`.

Capabilities are discovery and compatibility metadata. They do not define
manifest structure, educational equivalence, authorization, attempt selection,
or Grade policy.

An academic publication requires the exact current Academic Work Registration
revision and a non-cancelled lifecycle. It remains producer-native and does not
automatically become a Grade or Grade item. An intervention publication
requires and references no registration, remains nonacademic reportable data,
and cannot claim academic capabilities. Profile validation depends on kind,
not module ID: academic-result producers need nonempty supported Academic Work
versions; intervention-only producers may use an empty set.

### Revision and services

```text
Series identity:
ModuleWorkRef + publication_kind + record_set_id

Logical revision identity:
ModuleWorkRef + publication_kind + record_set_id + record_set_revision
```

Record-set revisions differ from attempts, native revisions, registration
revisions, schemas, and package versions. Use `publish_manifest_revision` for
the first revision and `supersede_manifest_revision` with an explicit expected
head thereafter. Exact replay returns `existing`; contradictory logical-
revision reuse fails. `withdraw_publication` adds an immutable withdrawal;
replay never restores it, although a withdrawn head may later be superseded.
Use `get_canonical_publication_record` and
`get_canonical_publication_withdrawal` to reload authority.

`RegistryServicePartialSuccessError.state` reports any durable state; reload
and reconcile it. Core never chooses a current publication from greatest
revision, newest timestamp, or filename.

### Manifest requirements

A published manifest is complete, immutable, contract-versioned, revision-
addressed, machine-readable, beneath the module work root, referenced with a
workspace-relative POSIX path, a regular nonsymlink file during verification,
bound to a stable record-set ID and positive revision, and bound to exact
SHA-256 bytes. Recommended layout:

```text
classes/<class_id>/modules/<module_id>/work/<work_id>/
  exports/manifests/<record_set_id>/<record_set_revision>.json
```

Never bind to `latest.json` or `current.json`. Core validates containment and
bytes and computes/verifies SHA-256; it does not parse the manifest body or
validate educational semantics. Restore a missing/altered manifest only from
trusted bytes reproducing the digest. Otherwise publish a new revision. Never
edit the historical Publication Record, path, or digest.

## Publication compatibility profiles

`pds_core.publication_compatibility` exposes
`SourceRecordContractSupport`, `PublicationContractSupport`,
`PublicationProducerProfile`, `PublicationProducerRegistry`,
`PublicationCompatibilityResult`, `validate_publication_producer_profile`,
`evaluate_publication_compatibility`, `discover_publication_producer_profiles`,
and `build_publication_producer_registry`.

```python
from pds_core.publication_compatibility import (
    PublicationContractSupport, PublicationProducerProfile,
    SourceRecordContractSupport,
)

academic_profile = PublicationProducerProfile(
    "synthetic_academic", "Synthetic Academic Producer",
    frozenset({"1"}), frozenset({"assignment_v1"}),
    (PublicationContractSupport(
        "academic_result_set", frozenset({"results_manifest_v1"}),
        frozenset({"points", "multiple_attempts"}),
        (SourceRecordContractSupport("result_set", frozenset({"1"})),),
        False,
    ),),
)
intervention_profile = PublicationProducerProfile(
    "synthetic_intervention", "Synthetic Intervention Producer",
    frozenset({"1"}), frozenset(),
    (PublicationContractSupport(
        "intervention_record_set", frozenset({"intervention_manifest_v1"}),
        frozenset({"intervention_history", "intervention_status"}),
    ),),
)
```

```toml
[project.entry-points."paper_data_suite.publication_producers"]
synthetic_academic = "synthetic_academic.pds_publication:get_profile"
```

The entry-point name must equal the returned profile's `module_id`. Current
Core fixtures are architecture fixtures, not proof that ScoreForm, Quillan,
Concord, or Portia exposes a production publication entry point.

## Producer and consumer checklists

An academic producer uses stable Core identities; defines native, manifest,
record-set, and source-record contracts; exposes a profile; registers eligible
work; writes an immutable manifest; publishes first and later revisions through
the proper services; withdraws rather than deletes; rebuilds the catalog when
needed; audits with its profile; and preserves native meaning.

An intervention-only producer does not fabricate registration, uses an empty
Academic Work contract set, publishes only intervention capabilities, and
preserves intervention meaning.

A consumer must:

1. Use the catalog only for candidate discovery.
2. Reload the canonical Publication Record.
3. Reload registration state where applicable.
4. Evaluate producer compatibility.
5. Verify the exact manifest path and digest.
6. Parse only through the producer's public manifest contract.
7. Preserve native scales, attempts, dispositions, and intervention states.
8. Check supersession and withdrawal.
9. Record exact provenance.
10. Apply authorization.
11. Apply consumer-owned policy only afterward.

Meridian may use capabilities to narrow candidates; they never determine Grade
policy.

## Canonical, derived, catalog, and transient state

Canonical Core state is Academic Period revisions/pointers, registration
revisions/pointers, Publication Records, and withdrawals. Canonical producer
state is native records, immutable manifest revisions, and native history.
Derived state is `registry/catalog.sqlite`, catalog rows/snapshots, audit
summaries, and rendered CLI output. Locks, temporary files, and SQLite
journal/WAL/SHM files are transient. Canonical JSON and producer records remain
authoritative; SQLite may be deleted and rebuilt.

`pds_core.academic_catalog` performs atomic full rebuilds with source inventory
and snapshot. Typed queries support bounded filters and deterministic ordering.
Publication states are `current`, `series_heads`, `historical`, `withdrawn`,
and `all`; schema is `1`, application ID is `0x50445341`. Rebuild does not crawl
work roots, open/hash manifests, parse producer data, or modify canonical state.
Queries do not create or rebuild a missing catalog automatically.

## CLI and audit

```text
pds-core academic registry status
pds-core academic registry validate
pds-core academic registry list registrations
pds-core academic registry list publications
pds-core academic registry list withdrawals
pds-core academic registry list locks
pds-core academic registry show registration
pds-core academic registry show publication
pds-core academic registry show withdrawal
pds-core academic registry show catalog
pds-core academic registry show lock
pds-core academic registry rebuild-catalog
pds-core academic registry clear-lock
pds-core academic periods list
pds-core academic periods validate
```

Commands support text and `--format json`. The stable schema-`"1"` JSON
envelope has `schema_version`, `command`, `workspace`, `ok`, `data`, and
`findings`. Exit codes are `0` success, `1` validation/operational failure, and
`2` usage failure. `--strict` promotes warnings. Validation can verify exact
manifest bytes and producer-profile compatibility. Missing profiles are
informational unless required. Rebuild supports dry run and audit is bounded.
Lock clearing is fingerprint protected. Follow the
[recovery guide](academic_registry_recovery.md).

## Migration and dependency guidance

```toml
dependencies = ["pds-core>=0.6,<0.7"]
```

The dependency update alone does not complete producer integration. Upgrading
does not create calendars/periods, register work, generate manifests, publish
records, build the catalog, crawl work, assign Grade items, calculate Grades,
or repair state. These namespaces appear only through explicit operations:

```text
settings/academic_periods/
registry/work/
registry/publications/
registry/withdrawals/
registry/catalog.sqlite
registry/.locks/
```

Downstream modules retain explicit routing and serialized-contract support,
decide whether they are producers, define real producer/manifest contracts,
expose the publication entry point only when implemented, register academic
work explicitly, publish immutable manifests through Core, and add producer-
owned integration tests. No old catalog migration is needed because it is
derived; rebuild it. Use the recovery guide for damaged or ambiguous state.
