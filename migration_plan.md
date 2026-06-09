# Stepwise Migration Plan: Shared `pds-core` Responsibilities

## Purpose

This document outlines the planned migration path for shared Paper Data Suite responsibilities.

The guiding principle is:

```text
pds-core defines shared contracts and utilities.
pds-scoreform and pds-quillan consume those utilities.
Module-specific scoring, tagging, reporting, PDF generation, and archival workflows stay in their own modules.
```

---

## 1. `pds-core` — Design shared QR payload and routing contract

**Purpose:** Establish the contract before moving code.

Define:

* `PDS1` QR payload grammar
* required fields: `module`, `class`, `aid`, `sid`, `page`
* optional fields: `doc`, `pages`, `part`, `form`, `attempt`
* legacy `OMR1` compatibility expectations
* safe identifier rules
* shared folder/path conventions
* raw scan vs routed submission distinction
* module responsibility boundaries

**Status:** Complete.

---

## 2. `pds-core` — Scaffold package and development tooling

**Purpose:** Make `pds-core` a real installable/testable Python package.

Add:

* package structure
* `pyproject.toml`
* `pytest`
* `ruff`
* `mypy`
* README setup instructions
* initial docs folder
* CI later if desired

**Depends on:** Step 1 design.

**Status:** Complete.

---

## 3. `pds-core` — Implement shared identifier validation

**Purpose:** Move safe ID/path assumptions into one shared module.

Implement validation for:

* `module`
* `class_id`
* `assignment_id`
* `student_id`
* safe filesystem/path-bearing identifiers

Reject:

* empty values
* spaces
* path separators
* `..`
* absolute paths
* unsafe punctuation
* QR delimiters such as `|` and `=`

**Used by:** `pds-scoreform`, `pds-quillan`.

**Status:** Complete.

---

## 4. `pds-core` — Implement QR payload data model

**Purpose:** Create a shared internal representation for parsed QR data.

Implement something like:

```text
QrPayload
```

Fields:

* `schema`
* `module`
* `class_id`
* `assignment_id`
* `student_id`
* `page`
* optional metadata dict

Include tests.

**Depends on:** Step 3 identifier validation.

**Status:** Complete.

---

## 5. `pds-core` — Implement `PDS1` QR payload builder/parser

**Purpose:** Let new modules create and parse shared QR payloads.

Implement:

* build `PDS1|module=...|class=...|aid=...|sid=...|page=...`
* parse `PDS1`
* validate required fields
* reject malformed payloads
* preserve optional fields

**Used by:** future Quillan response sheets and later ScoreForm migration.

**Status:** Complete.

---

## 6. `pds-core` — Implement legacy `OMR1` parser

**Purpose:** Preserve current ScoreForm compatibility.

Implement parsing for:

```text
OMR1|class=<class_id>|aid=<assignment_id>|sid=<student_id>
```

Map internally to shared payload shape:

```text
schema = OMR1
module = scoreform
class_id = ...
assignment_id = ...
student_id = ...
page = 1
metadata = {}
```

**Important:** This should not force ScoreForm to stop producing `OMR1` yet.

**Status:** Complete.

---

## 7. `pds-core` — Implement shared route resolution helpers

**Purpose:** Centralize folder construction.

Implement safe path helpers for:

```text
classes/
classes/<class_id>/
classes/<class_id>/roster.csv
classes/<class_id>/assignments/
classes/<class_id>/assignments/<assignment_id>/
classes/<class_id>/assignments/<assignment_id>/assignment.json
classes/<class_id>/assignments/<assignment_id>/templates/
classes/<class_id>/assignments/<assignment_id>/scans/
classes/<class_id>/assignments/<assignment_id>/submissions/
classes/<class_id>/assignments/<assignment_id>/submissions/<student_id>/
classes/<class_id>/assignments/<assignment_id>/results/
classes/<class_id>/assignments/<assignment_id>/debug/
```

No module-specific scoring or tagging logic.

Helpers should:

* accept `root: str | Path`
* return `Path` objects
* validate `class_id`, `assignment_id`, and `student_id`
* construct paths only
* not create directories

**Status:** Complete.

---

## 8. `pds-core` — Implement scan inbox/archive conventions

**Purpose:** Give all modules one shared convention for raw scan intake and conservative scan archive locations.

Define helpers for:

```text
scans_inbox/
scans_archive/
scans_archive/<YYYY-MM-DD>/
```

Keep behavior conservative:

* do not delete originals
* do not move files
* do not rename files
* do not create directories
* do not define retention policy
* do not define restore workflows
* do not define audit metadata yet

This step is about shared path conventions only.

Higher-level archiving behavior belongs in a future module such as `pds-sunset`.

**Status:** Complete.

---

## Deferred `pds-core` Follow-up Issues

These are useful but not required before beginning low-risk `pds-scoreform` migration.

### Deferred A. `pds-core` — Define raw scan archive file naming and metadata contract

**Purpose:** Define how raw scanned files should eventually be preserved, named, and audited after intake.

Possible future topics:

* source filename preservation
* filename collision handling
* scanner/source metadata
* timestamps
* checksums
* audit JSON sidecars
* original scan provenance
* relationship between archived raw scans and routed submissions

This should remain a contract/design issue unless implementation becomes necessary.

**Do not include yet:**

* deletion policy
* retention policy
* restore workflows
* school-year rollover workflows
* reusable-material carry-forward
* full archival lifecycle behavior

Those belong more naturally in `pds-sunset`.

**Recommended milestone:** Backlog or later `v0.3.0 — Scan Lifecycle Contracts`.

---

## 9. `pds-scoreform` — Add `pds-core` as a dependency

**Purpose:** Prepare ScoreForm to consume shared logic.

Update:

* dependency config
* imports
* local setup docs
* tests/install instructions

For private/local development, this may temporarily use a local path dependency or editable install until packaging is settled.

**Depends on:** completed `pds-core` QR/routing foundation.

---

## 10. `pds-scoreform` — Replace internal identifier/path validation with `pds-core`

**Purpose:** First low-risk extraction.

Replace duplicated local checks with shared helpers for:

* class IDs
* assignment IDs
* student IDs
* safe paths
* class/assignment folder resolution

Do **not** change QR payload format yet.

---

## 11. `pds-scoreform` — Use `pds-core` legacy `OMR1` parser

**Purpose:** Move QR parsing responsibility out of ScoreForm while preserving behavior.

Replace ScoreForm’s local `OMR1` parsing with:

```text
pds-core parses OMR1 -> ScoreForm receives normalized payload
```

Expected behavior should remain unchanged.

Current ScoreForm sheets should still score.

---

## 12. `pds-scoreform` — Use `pds-core` route helpers for result paths

**Purpose:** Centralize route resolution.

Move result-path construction toward shared helpers.

Preserve current output compatibility unless intentionally changed:

```text
classes/<class_id>/assignments/<assignment_id>/results.csv
```

If changing to:

```text
classes/<class_id>/assignments/<assignment_id>/results/results.csv
```

make that a separate explicit migration issue.

---

## 13. `pds-scoreform` — Use `pds-core` scan inbox/archive helpers

**Purpose:** Align ScoreForm raw scan handling with shared Paper Data Suite scan conventions.

Use `pds-core` helpers for:

```text
scans_inbox/
scans_archive/
scans_archive/<YYYY-MM-DD>/
```

Keep behavior conservative:

* do not delete raw scans by default
* do not rename raw scans as part of this step
* do not introduce retention policy
* do not introduce archive metadata yet

This should be a path-convention adoption step only.

---

## 14. `pds-scoreform` — Add optional `PDS1` QR payload generation

**Purpose:** Begin migration without breaking old packets.

Add option/configuration for generating future shared payloads:

```text
PDS1|module=scoreform|class=...|aid=...|sid=...|page=1
```

Keep default as `OMR1` until enough testing confirms compatibility.

---

## 15. `pds-scoreform` — Decide ScoreForm QR default migration

**Purpose:** Make a deliberate compatibility decision.

Options:

* keep `OMR1` default indefinitely
* switch new templates to `PDS1`
* support both with a config flag
* support both parser formats permanently

This should happen only after `pds-core` parsing and routing are tested.

---

## 16. `pds-quillan` — Add `pds-core` as a dependency

**Purpose:** Prepare Quillan for shared IDs, QR payloads, and routing.

Update:

* dependency config
* setup docs
* development instructions

No paper workflow implementation yet.

---

## 17. `pds-quillan` — Align assignment path conventions with `pds-core`

**Purpose:** Ensure Quillan’s storage model will support scan routing later.

Use shared route helpers for:

```text
classes/<class_id>/assignments/<assignment_id>/
```

Keep existing Quillan data model intact:

* assignment configs
* standards profiles
* submissions
* requirements
* tags
* scores
* feedback
* reports

---

## 18. `pds-quillan` — Use `pds-core` scan inbox/archive helpers

**Purpose:** Align Quillan’s future paper workflow with shared raw scan conventions.

Use `pds-core` helpers for:

```text
scans_inbox/
scans_archive/
scans_archive/<YYYY-MM-DD>/
```

This should not implement writing-response routing yet.

---

## 19. `pds-quillan` — Design printable writing-response template contract

**Purpose:** Define Quillan’s paper workflow before implementation.

Document:

* lined response sheet requirements
* QR/header requirements
* page numbering
* continuation pages
* class packet structure
* individual student PDFs
* scan routing expectations

No implementation yet.

---

## 20. `pds-quillan` — Use `pds-core` to build Quillan QR payloads

**Purpose:** First Quillan use of shared QR logic.

Generate payloads like:

```text
PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=1|doc=response
```

This can be tested without generating PDFs yet.

---

## 21. `pds-quillan` — Implement printable writing-response PDF generation

**Purpose:** Add the first Quillan paper-output feature.

Generate:

```text
templates/class_packet.pdf
templates/individual/<student_id>_<last>_<first>.pdf
```

Each page should include:

* header
* class/assignment/student metadata
* QR payload
* page number
* lined writing area

---

## 22. `pds-quillan` — Implement scan routing design spike

**Purpose:** Prototype routing scanned writing pages without full OCR/tagging.

Use `pds-core` parser/router to route pages into:

```text
classes/<class_id>/assignments/<assignment_id>/submissions/<student_id>/
```

Preserve raw scan metadata conceptually, but do not define the final raw scan archive file naming or metadata contract in this step.

Do not implement handwriting OCR yet.

---

## Future Module: `pds-sunset`

`pds-sunset` should handle higher-level archival lifecycle workflows that do not belong in `pds-core`.

Possible responsibilities:

* archive inactive classes
* archive inactive assignments
* archive completed marking periods
* archive completed school years
* inspect archived projects
* restore archived materials where appropriate
* support school-year rollover workflows
* support reusable instructional material carry-forward
* exclude or separate student-specific artifacts when carrying materials forward

`pds-sunset` should distinguish between reusable instructional materials and student-specific artifacts.

Reusable materials may include:

* assignment templates
* standards profiles
* rubrics
* teacher-authored prompts
* blank printable templates

Student-specific artifacts should generally not be carried forward as reusable materials:

* student submissions
* scan files
* scores
* feedback
* debug output
* attempt history
* class rosters from previous years

`pds-core` may provide shared paths and contracts used by `pds-sunset`, but `pds-core` should not own archival policy.

---

## Recommended Order

Do not start by modifying ScoreForm until the `pds-core` foundation is complete.

Order should be:

```text
pds-core design
pds-core package scaffold
pds-core identifier validation
pds-core QR payload model
pds-core PDS1 parser/builder
pds-core OMR1 parser
pds-core route helpers
pds-core scan inbox/archive helpers
pds-scoreform dependency + low-risk migration
pds-quillan dependency + future paper workflow
pds-sunset archival lifecycle work later
```

---

## Practical First Issues

The first `pds-core` foundation issues are:

1. **`pds-core`** — Design shared QR payload and routing contract
2. **`pds-core`** — Scaffold pds-core Python package and development tooling
3. **`pds-core`** — Implement shared identifier validation
4. **`pds-core`** — Implement shared QR payload model
5. **`pds-core`** — Implement PDS1 QR payload parser and builder
6. **`pds-core`** — Implement legacy OMR1 parser for ScoreForm compatibility
7. **`pds-core`** — Implement shared route resolution helpers
8. **`pds-core`** — Implement scan inbox/archive conventions

After those are complete, begin the `pds-scoreform` migration with a low-risk dependency/setup issue.

---

## Current Milestone Completion Criteria

The initial `pds-core` QR/routing foundation milestone is complete when the following are implemented and tested:

* shared QR/routing contract documentation
* package scaffold and tooling
* identifier validation
* `QrPayload` data model
* `PDS1` parser/builder
* legacy `OMR1` parser
* class/assignment route helpers
* scan inbox/archive route helpers

Once these are merged, the next recommended milestone is the first `pds-scoreform` migration milestone.
