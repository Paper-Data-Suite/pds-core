# Changelog

All notable changes to PDS Core will be documented in this file.

## Version Policy

PDS Core is in early pre-1.0 development. GitHub issues and milestones may be
used as planning buckets, while package versions describe installable package
state.

## [Unreleased]

### Added

- Added shared active school-year workspace state helpers.
- Added shared standards library workspace-storage behavior where the canonical
  `standards/library.json` path is side-effect free to resolve, missing
  workspace libraries load as empty libraries without creating files, and
  workspace writes create only the standards library file and parent directory.
- Added root-level `CHANGELOG.md`.
- Added root-level `LICENSE`.
- Added root-level `SECURITY.md`.

## Historical Development Notes

PDS Core already includes shared infrastructure for:

- identifier validation;
- safe route and path helpers;
- PDS1 QR payload construction and parsing;
- legacy OMR1 compatibility where needed by downstream modules;
- scan inbox and archive route helpers;
- workspace-root resolution and status inspection;
- roster models, validation, CSV loading, and CSV writing;
- class folder helpers;
- assignment folder helpers;
- shared standards definition and profile models;
- standards library JSON helpers;
- standards workspace library helpers;
- standards usage event models;
- explicit-path standards usage JSONL helpers;
- canonical standards usage workspace ledger helpers.

These notes summarize existing capability areas. They do not represent formal
tagged releases.
