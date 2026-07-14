# Changelog

All notable changes to PDS Core are documented in this file.

## Version Policy

PDS Core remains pre-1.0. Package versions describe installable package state;
planning milestones and historical development notes do not imply that every
minor version was published. Unless otherwise documented, only the latest
supported pre-1.0 minor line receives fixes.

## [Unreleased]

### Added

- Added atomic ordered standard-definition batch addition and atomic profile
  membership add, remove, and metadata-preserving replacement CLI commands.
- Added shared presentation-independent transformations used by both the direct
  CLI and teacher menu for those four compound mutations.

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
