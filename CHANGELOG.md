# Changelog

All notable changes to PDS Core are documented in this file.

## Version Policy

PDS Core remains pre-1.0. Package versions describe installable package state;
planning milestones and historical development notes do not imply that every
minor version was published. Unless otherwise documented, only the latest
supported pre-1.0 minor line receives fixes.

## [Unreleased]

## [0.6.3] - 2026-08-24

### Added

- Added durable `StandardsFrameworkMetadata` provenance, lifecycle,
  supersession, and descriptive licensing/redistribution metadata to the
  canonical shared standards library and framework-aware starter merge results.
- Added the complete coded 2020 NJSLS Computer Science and Design Thinking
  starter pack with high-school Computer Science and Design Thinking profiles.
- Added the generally applicable 2020 NJSLS Career Readiness, Life Literacies &
  Key Skills 9.1, 9.2, and 9.4 starter pack with four high-school profile pools.
- Added AP Computer Science Principles Fall 2023 framework references for five
  Big Ideas, 64 Learning Objective identifiers, six Computational Thinking
  Practices, and 20 practice-skill identifiers without redistributing protected
  College Board framework prose.
- Added `english11_2023_njsls_ela`, reusing the existing source-defined grades
  11-12 ELA durable IDs rather than duplicating standard definitions.

### Changed

- Expanded the bundled starter library to four independently installable packs:
  AP CSP Fall 2023, 2020 NJSLS-CLKS, 2020 NJSLS-CS&DT, and 2023 NJSLS-ELA.
- Made course-filtered standards selection profile-aware so one source grade
  band can support multiple local course profiles without rewriting previously
  installed definitions.
- Expanded release artifact and installed-wheel acceptance to require the exact
  four starter resources and verify the audited 694-definition, 12-profile,
  four-framework combined release surface.

### Migration

- Upgrading from v0.6.2 requires no automatic workspace, path, or schema
  migration. Legacy standards libraries without framework metadata continue to
  load with an empty framework collection.
- Package installation alone does not install or rewrite starter standards.
  Explicitly reinstalling the v0.6.3 `njsls_ela_2023` starter into a v0.6.2-era
  ELA library adds the English 11 profile and ELA framework metadata without
  rewriting the existing 135 definitions.
- Existing consumers using established Core 0.6 APIs may continue to declare
  `pds-core>=0.6,<0.7`; consumers that require the new standards-framework
  surfaces should use an appropriate `>=0.6.3,<0.7` floor.


## [0.6.2] - 2026-08-21

### Added

- Added guarded full-roster import preview/diff/commit with exact `student_id`
  identity, explicit additions/changes/removals, opaque reviewed-state tokens,
  stale candidate/canonical-state rejection, per-roster write coordination, and
  atomic complete replacement.
- Added deterministic noninteractive `pds-core roster import-preview` and
  `pds-core roster import-commit` commands over the public guarded import
  service without adding a duplicate teacher-menu workflow.
- Added failure-isolating diagnostics for Core-owned routing, publication, and
  module-operations providers while preserving strict runtime registries.
- Added the version-`"1"` `paper_data_suite.module_operations` provider contract
  with distinct readiness and attention capabilities, bounded privacy-minimal
  results, and opaque owner-routed action references.
- Added authenticated exact released-consumer qualification for ScoreForm
  0.10.0, Quillan 0.9.0, Concord 0.2.0, Meridian 0.1.1, and Vitrine 0.2.0.

### Changed

- Modernized package license metadata to the SPDX/PEP 639 form while retaining
  the MIT license and packaged `LICENSE` file.
- Final-release CI builds the tracked v0.6.2 wheel normally before invoking the
  exact-wheel released-consumer qualifier; #195's temporary version-substitution
  builder remains provisional historical tooling only.

### Migration

- Upgrading from v0.6.1 requires no workspace, path, or schema migration. New
  roster-import and provider operations occur only through explicit calls;
  existing Core 0.6 records retain their meanings and locations.
- Existing consumers using established Core 0.6 APIs may continue to declare
  `pds-core>=0.6,<0.7`. Consumers that require a new v0.6.2 API should use an
  appropriate `>=0.6.2,<0.7` floor.

## [0.6.1] - 2026-08-18

### Added

- Added typed immutable `grouping_signal_set_v1` models, strict structural and
  exact-mapping validation, and deterministic canonical JSON text/UTF-8 bytes
  for the neutral grouping-signal interchange.
- Added self-contained `grouping_signal_csv_v1` import/export with immutable
  typed preview, deterministic one-dimension export, validated conversion to
  canonical grouping-signal models, and projection-safe identity handling.
- Added create-only grouping-signal exchange storage with exact canonical-JSON
  SHA-256 sidecars, strict load/integrity verification, idempotent identical
  replay, immutable identity-collision rejection, and no current/latest alias.
- Added workspace-aware grouping-signal diagnostics with exact target-roster
  comparison, deterministic wrong-class/unknown identity distinction,
  per-dimension missing coverage and matched-band counts, and no silent
  remapping or completion.

## [0.6.0] - 2026-08-03

### Added

- Added atomic ordered standard-definition batch addition and atomic profile
  membership add, remove, and metadata-preserving replacement CLI commands.
- Added shared presentation-independent transformations used by both the direct
  CLI and teacher menu for those four compound mutations.
- Added immutable, school-year-qualified Academic Period Calendar models,
  storage with explicit current pointers, hierarchy/date queries, and exact
  reference resolution.
- Added immutable Academic Work Registration revisions and producer-facing
  idempotent create/update services.
- Added typed immutable academic-result and intervention Publication Records,
  explicit supersession and withdrawal, exact SHA-256 manifest binding, and
  canonical retrieval services.
- Added publication producer profiles, compatibility evaluation, registry
  construction, and installed discovery through
  `paper_data_suite.publication_producers`.
- Added a disposable SQLite academic catalog with atomic full rebuild, source
  snapshots, and typed deterministic queries.
- Added bounded registry audit, manifest/profile verification, dry-run catalog
  rebuilding, and fingerprint-protected lock clearing.
- Added the `pds-core academic registry` and `pds-core academic periods`
  noninteractive CLI surfaces with text and schema-`"1"` JSON output.
- Added synthetic producer contract fixtures for academic and intervention
  compatibility without importing sibling runtime packages.
- Added active academic-registry integration and conservative recovery guides.

### Changed

- Documented Core as the shared academic-period and reportable-data contract;
  producer-native records remain authoritative and Meridian owns grading and
  reporting policy.
- Corrected publication-profile validation so only producers supporting
  `academic_result_set` require supported Academic Work contract versions;
  intervention-only profiles may declare an empty set.
- Updated active downstream dependency guidance to `pds-core>=0.6,<0.7`.
- Documented canonical JSON and producer records as authoritative and
  `registry/catalog.sqlite` as rebuildable derived state.

### Migration

- Upgrading from v0.5 creates no calendars, registrations, manifests,
  publications, catalog, Grade policy, or sibling producer integration.
- Producers must opt into publication, expose a real compatibility profile,
  and publish immutable producer-owned manifests through Core services.
- Rebuild the derived catalog; there is no prior authoritative catalog to
  migrate.
- See [the v0.6.0 release notes](docs/releases/v0.6.0.md),
  [the academic registry integration guide](docs/academic_registry_integration.md),
  and [the recovery guide](docs/academic_registry_recovery.md).

## [0.5.0] - 2026-07-14

### Added

- Added strict PDS2 page-locator parsing and canonical serialization.
- Added generic routing identities, route-ID generation, exact dictionary
  conversion, route-registration persistence, and runtime route resolution.
- Added module-qualified work roots at
  `classes/<class_id>/modules/<module_id>/work/<work_id>/` and safe
  module-owned descendant paths.
- Added explicit and entry-point-discovered module profiles through the
  `paper_data_suite.modules` group, exact module registries, compatibility
  checks, and ordered mixed-module dispatch.
- Added version 2 generic routing-failure records and append-only linked
  resolution events with strict JSON loading and immutable creation.
- Added active source-scan retention with SHA-256 provenance.
- Added shared workspace, roster, class, standards, school-year, menu
  navigation, and local-open infrastructure developed before this release.
- Added the `pds-core` CLI, the `core` teacher menu, bundled 2023 NJSLS-ELA
  starter standards, and standards management and selection APIs.
- Added explicit PEP 517 setuptools build metadata and release-metadata
  regression tests.

### Changed

- Core is now documented as the shared contracts and infrastructure package
  for ScoreForm, Quillan, Concord, and future Paper Data Suite modules.
- QR payloads now identify an expected physical page route through
  `module_id`, `class_id`, `work_id`, and `route_id`; semantic target identity
  remains behind a persisted module-owned registration.
- Shared routing failure and resolution schemas are version `"2"`; version 1
  records are historical and are not converted automatically.
- The active workspace contract is module-qualified. Core no longer treats
  assignments or student-submission directories as universal routing roots.

### Removed

- Removed PDS1 and OMR1 parsing, generation, normalization, and compatibility
  behavior. These payloads are rejected as unsupported schemas.
- Removed the former `QrPayload` model and the `pds_core.pds1`,
  `pds_core.omr1`, and `pds_core.qr_payload` runtime modules.
- Removed universal assignment and student-submission route helpers, including
  the former `pds_core.assignments` surface.
- Removed shared routing assumptions that every page has a `student_id`, an
  assignment identity, a logical page number, or a Core-owned final evidence
  destination.

### Migration

- Downstream modules must require Python 3.11 or newer and depend on
  `pds-core>=0.5,<0.6` while integrating this pre-1.0 line.
- Replace legacy payload handling with `pds_core.pds2` and
  `pds_core.routing_models`.
- Replace universal assignment paths with `pds_core.routes` module-qualified
  work roots and keep module-specific descendants module-owned.
- Register a `ModuleProfile` explicitly or expose a zero-argument provider in
  the `paper_data_suite.modules` entry-point group before dispatch.
- See [the v0.5.0 release notes](docs/releases/v0.5.0.md) and
  [the PDS2 module integration guide](docs/pds2_module_integration.md).

## Historical Development Notes

The repository previously reported package version `0.1.0` while capabilities
were developed through planning milestones. No formal `0.2.0`, `0.3.0`, or
`0.4.0` package release history is asserted here. Version 0.5.0 is the next
installable release represented by this changelog.
