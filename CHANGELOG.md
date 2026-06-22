# Changelog

All notable changes to PDS Core will be documented in this file.

## Version Policy

PDS Core is in early pre-1.0 development. GitHub issues and milestones may be
used as planning buckets, while package versions describe installable package
state.

## [Unreleased]

### Added

- Added a generic, standard-library-only helper for opening existing local
  files and directories in the system default application.
- Added shared active scan root, retained source, date-bucket, routing review,
  retained filename, and retained source path helpers without directory
  creation or scan copying.
- Added shared routing failure categories, a frozen failure metadata model,
  strict validation and dictionary conversion, canonical review JSON paths,
  and exclusive UTF-8 JSON writing.
- Defined the active scan intake, retained source scan, routing review, failure
  metadata, and provenance contract without changing existing scan route
  helpers or module behavior.
- Added pure in-memory roster mutation helpers for adding, replacing,
  upserting, and removing student records while returning new validated
  `Roster` instances.
- Added pure in-memory standards library mutation helpers for adding,
  replacing, and upserting standard definitions and standards profiles while
  returning new validated `StandardsLibrary` instances.
- Added read-only in-memory standards library browsing helpers for finding and
  filtering standard definitions and standards profiles, plus deterministic
  subject, source, domain, and category-path listing helpers.
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
- legacy scan inbox and `scans_archive_*` route helpers;
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
