# Paper Data Suite Migration Plan

## Purpose

This document tracks remaining migration and architecture work for the Paper Data Suite family of repositories.

The current direction is:

```text
pds-core defines shared contracts and utilities.
Paper Data Suite modules consume those utilities directly.
Forward-looking modules should use PDS1 by default.
Legacy behavior may remain as fallback where useful, but it should not drive new architecture.
```

`pds-scoreform` is the Paper Data Suite version of ScoreForm. The original standalone ScoreForm repository remains available as the stable legacy line, so `pds-scoreform` should prioritize the shared suite architecture.

---

## Core Architecture Principle

Paper Data Suite modules should share common infrastructure through `pds-core`:

* identifier validation
* QR payload building/parsing
* route/path conventions
* raw scan inbox/archive path conventions
* normalized metadata models where useful

Module-specific behavior should remain in the module that owns it.

Examples:

| Repo            | Owns                                                                            |
| --------------- | ------------------------------------------------------------------------------- |
| `pds-core`      | Shared contracts, validation, QR payload utilities, route helpers               |
| `pds-scoreform` | OMR answer sheets, scoring, ScoreForm-specific PDFs/results                     |
| `pds-quillan`   | Writing-response sheets, writing tags, scores, feedback, writing reports        |
| `pds-corum`     | Student behavior tracking and intervention/modification records                 |
| `pds-chatter`   | Class/small-group discussion tracking and scoring                               |
| `pds-register`  | Teacher class notes and instructional filing                                    |
| `pds-cast`      | Communications to students, parents, administrators, and other stakeholders     |
| `pds-dashboard` | Data visualization layer; name still tentative                                  |
| `pds-folio`     | Student portfolios                                                              |
| `pds-reports`   | Report generation layer; name still tentative                                   |
| `pds-sunset`    | Archival lifecycle, rollover, restoration, and material carry-forward workflows |

---

## Shared QR Direction

New Paper Data Suite modules should use `PDS1` payloads by default.

General format:

```text
PDS1|module=<module>|class=<class_id>|aid=<assignment_id>|sid=<student_id>|page=<page>
```

Examples:

```text
PDS1|module=scoreform|class=english9_p2|aid=rj_act1_quiz|sid=1001|page=1
```

```text
PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=1|doc=response
```

Legacy `OMR1` may remain supported as a fallback for old ScoreForm sheets, but new `pds-scoreform` generation should default to `PDS1`.

---

## Remaining `pds-scoreform` Work

### 1. `pds-scoreform` — Review completed migration as a whole

**Purpose:** Confirm that the combined migration to `pds-core` and `PDS1` did not introduce regressions.

Review:

* dependency setup
* identifier validation
* route helper adoption
* result path preservation
* scan inbox route adoption
* legacy `OMR1` fallback parsing
* default `PDS1` generation
* QR-aware scoring behavior
* real PDF generation/scoring workflow
* documentation consistency

This is a good point for a skeptical Antigravity review.

The review should specifically check:

* no accidental result-path migration;
* no QR parsing regression;
* no old `OMR1` documentation presented as the default;
* no hidden dependency on machine-specific paths;
* no scan movement/deletion/archive behavior accidentally introduced;
* test coverage for `PDS1` generation and parsing;
* whether `pds-scoreform` is ready for a real classroom exam trial.

---

### 2. `pds-scoreform` — Prepare for classroom trial

**Purpose:** Make sure `pds-scoreform` is ready for the planned real exam workflow.

Confirm:

* fresh class packet generation;
* `PDS1` QR decoding;
* scoring from scanned PDFs/images;
* routed result output;
* roster enrichment;
* invalid/missing QR behavior;
* manual recovery path if a QR code fails;
* generated files ignored by Git;
* no real student data committed.

This should be a practical readiness pass, not a broad architecture refactor.

---

### 3. `pds-scoreform` — Add ruff development tooling

**Purpose:** Bring ScoreForm’s linting closer to `pds-core` and `pds-quillan`.

Add:

* `ruff` development dependency
* `ruff` configuration in `pyproject.toml`
* documented lint command
* optional update to test scripts

Start with linting only. Avoid large automatic rewrites unless reviewed carefully.

---

### 4. `pds-scoreform` — Add mypy development tooling cautiously

**Purpose:** Begin type-checking ScoreForm without forcing a disruptive strict migration.

Add:

* `mypy` development dependency
* initial `mypy` configuration
* documented type-check command

Use a cautious configuration at first. ScoreForm is older and more operationally complex than `pds-core`, so strict typing can be introduced gradually.

---

### 5. `pds-scoreform` — Decide whether to remove `OMR1` fallback later

**Purpose:** Decide whether legacy QR fallback should remain permanently.

Options:

* keep `OMR1` fallback indefinitely;
* remove `OMR1` fallback after all generated examples/tests use `PDS1`;
* keep parser fallback but remove most `OMR1` documentation;
* provide a small legacy-note section only.

This does not need to be decided immediately.

---

## Remaining `pds-quillan` Work

### 1. `pds-quillan` — Add `pds-core` as a dependency

**Purpose:** Prepare Quillan for shared IDs, QR payloads, scan routes, and folder conventions.

Update:

* dependency configuration
* setup docs
* development instructions
* import smoke test if appropriate

Use the same sibling-repo local development model as `pds-scoreform` until packaging is settled.

---

### 2. `pds-quillan` — Align assignment path conventions with `pds-core`

**Purpose:** Ensure Quillan’s storage model supports future paper-based workflows.

Use shared route helpers for:

```text
classes/<class_id>/assignments/<assignment_id>/
```

Keep the existing Quillan data model intact:

* assignment configs
* standards profiles
* submissions
* requirements
* tags
* scores
* feedback
* reports

---

### 3. `pds-quillan` — Use `pds-core` scan inbox/archive helpers

**Purpose:** Align Quillan’s future paper workflow with shared raw scan conventions.

Use `pds-core` helpers for:

```text
scans_inbox/
scans_archive/
scans_archive/<YYYY-MM-DD>/
```

This should not implement writing-response routing yet.

---

### 4. `pds-quillan` — Design printable writing-response template contract

**Purpose:** Define Quillan’s paper workflow before implementation.

Document:

* lined response sheet requirements
* QR/header requirements
* page numbering
* continuation pages
* class packet structure
* individual student PDFs
* scan routing expectations
* how assignment requirements appear on the page
* how student identity/class/assignment metadata appears on the page

No implementation yet.

---

### 5. `pds-quillan` — Use `pds-core` to build Quillan QR payloads

**Purpose:** First Quillan use of shared QR logic.

Generate payloads like:

```text
PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=1|doc=response
```

This can be tested without generating PDFs yet.

---

### 6. `pds-quillan` — Implement printable writing-response PDF generation

**Purpose:** Add the first Quillan paper-output feature.

Generate:

```text
templates/class_packet.pdf
templates/individual/<student_id>_<last>_<first>.pdf
```

Each page should include:

* header
* class metadata
* assignment metadata
* student metadata
* QR payload
* page number
* lined writing area

---

### 7. `pds-quillan` — Implement scan routing design spike

**Purpose:** Prototype routing scanned writing pages without full OCR/tagging.

Use `pds-core` QR parsing and route helpers to route pages into:

```text
classes/<class_id>/assignments/<assignment_id>/submissions/<student_id>/
```

Preserve the concept of raw scan provenance, but do not define the final raw scan archive file naming or metadata contract in this step.

Do not implement handwriting OCR yet.

---

## Future Shared Module Work

### `pds-corum`

**Purpose:** Track student behavior patterns, interventions, modifications, and outcomes.

Possible responsibilities:

* behavior event logging
* intervention tracking
* modification plans
* follow-up notes
* pattern summaries
* exportable behavior reports

Likely shared dependencies:

* `pds-core` identifiers
* class/student routing
* report output conventions
* possible integration with `pds-dashboard` and `pds-reports`

---

### `pds-chatter`

**Purpose:** Track and score class discussions, seminars, small-group work, and participation.

Possible responsibilities:

* discussion event logging
* participation evidence
* rubric-aligned discussion scoring
* group-level summaries
* student-level participation records
* teacher notes during live discussion

Likely shared dependencies:

* class/student identifiers
* assignment/session identifiers
* route helpers
* reporting layer
* portfolio layer

---

### `pds-register`

**Purpose:** File and retrieve teacher class notes, instructional records, and related artifacts.

Possible responsibilities:

* daily class notes
* instructional logs
* lesson reflections
* unit notes
* links between notes and classes/assignments
* searchable teacher records

Likely shared dependencies:

* class IDs
* assignment IDs
* route helpers
* archival conventions
* dashboard/report integrations

---

### `pds-cast`

**Purpose:** Support communications to students, parents, administrators, and other stakeholders.

Possible responsibilities:

* message templates
* class announcements
* parent contact logs
* administrator updates
* generated communication records
* exportable communication histories

Likely shared dependencies:

* class/student identifiers
* contact/recipient conventions
* reporting layer
* archive layer

---

### `pds-dashboard`

**Purpose:** Provide a data visualization layer across Paper Data Suite modules.

Name is tentative.

Possible responsibilities:

* class-level visual summaries
* student-level trend displays
* assignment performance views
* behavior/participation/writing/scoring dashboards
* cross-module data aggregation

This module should consume outputs from other modules rather than own their data models.

Possible alternate names:

* `pds-lens`
* `pds-atlas`
* `pds-observatory`
* `pds-compass`
* `pds-vista`

---

### `pds-folio`

**Purpose:** Maintain student portfolios across assignments, writing samples, scoring artifacts, feedback, and selected evidence.

Possible responsibilities:

* student artifact collections
* writing portfolios
* scoring history
* selected teacher feedback
* student-facing or teacher-facing portfolio exports
* cross-module evidence aggregation

Likely shared dependencies:

* class/student identifiers
* assignment identifiers
* route helpers
* reports layer
* archive layer

---

### `pds-reports`

**Purpose:** Generate formal reports from Paper Data Suite module data.

Name is tentative.

Possible responsibilities:

* printable reports
* CSV/JSON summaries
* student reports
* class reports
* standards reports
* parent/admin-facing reports
* end-of-marking-period exports

This should probably consume module outputs rather than directly own scoring/tagging logic.

Possible alternate names:

* `pds-dispatch`
* `pds-brief`
* `pds-ledger`
* `pds-summary`
* `pds-press`

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

## Deferred `pds-core` Follow-up Issues

### Define raw scan archive file naming and metadata contract

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

Do not include yet:

* deletion policy
* retention policy
* restore workflows
* school-year rollover workflows
* reusable-material carry-forward
* full archival lifecycle behavior

Those belong more naturally in `pds-sunset`.

Recommended milestone:

```text
Backlog
```

or:

```text
v0.3.0 — Scan Lifecycle Contracts
```
