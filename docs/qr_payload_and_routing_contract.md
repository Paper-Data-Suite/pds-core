# QR Payload and Routing Contract

## Purpose

This document defines the first shared Paper Data Suite QR payload and routing contract.

The contract is intended for use by multiple Paper Data Suite modules, beginning with:

* `pds-scoreform`
* `pds-quillan`

The purpose is to prevent each module from inventing incompatible QR formats, identifier rules, folder conventions, and scan-routing behavior.

This document is design-only. It defines the intended shared contract before implementation begins in `pds-core`.

## Design Goals

The shared QR and routing contract should:

* support multiple Paper Data Suite modules;
* preserve compatibility with existing ScoreForm `OMR1` QR payloads;
* define a future shared `PDS1` payload format;
* use safe identifier rules for path-bearing values;
* support local-first project folders;
* distinguish raw scan files from routed student submissions;
* support ScoreForm selected-response workflows;
* support future Quillan paper-based writing-response workflows;
* keep shared infrastructure in `pds-core`;
* avoid direct dependencies between module-specific repositories.

The intended dependency direction is:

```text
pds-scoreform -> pds-core
pds-quillan   -> pds-core
```

The following dependency should be avoided:

```text
pds-quillan -> pds-scoreform
```

ScoreForm may inform the design because it already has QR, template, roster, scan, and result-routing behavior, but shared QR/routing infrastructure should live in `pds-core`.

## Module Boundaries

### `pds-core`

`pds-core` should own shared infrastructure that is useful across Paper Data Suite modules.

Planned responsibilities:

* identifier validation;
* QR payload construction;
* QR payload parsing;
* QR payload validation;
* legacy ScoreForm `OMR1` parsing support;
* shared `PDS1` payload schema/version contract;
* safe path construction;
* route resolution from parsed QR metadata;
* scan inbox conventions;
* scan archive conventions;
* shared class/assignment/student path conventions;
* project-root/home-directory configuration;
* module-neutral route result objects.

### `pds-scoreform`

`pds-scoreform` should own selected-response and OMR-specific behavior.

Responsibilities that should remain ScoreForm-specific:

* OMR answer sheet layout;
* answer boxes/bubbles;
* corner registration marks;
* answer-key scoring;
* ambiguous/double-mark detection;
* selected-response scoring;
* selected-response result exports;
* ScoreForm-specific debug artifacts;
* ScoreForm-specific template layout.

ScoreForm should eventually consume shared QR and routing utilities from `pds-core`, but it should not be forced to abandon existing `OMR1` support immediately.

### `pds-quillan`

`pds-quillan` should own writing-response, tagging, scoring, and feedback behavior.

Responsibilities that should remain Quillan-specific:

* writing assignment data model;
* writing-response template layout;
* lined response sheets;
* continuation pages;
* writing submission records;
* standards-aligned writing tags;
* rubric/scoring data;
* feedback data;
* writing reports;
* scanned essay review workflow;
* OCR/transcription workflow if added later.

Quillan should eventually consume shared QR and routing utilities from `pds-core`, but it should not depend directly on ScoreForm.

## Legacy ScoreForm `OMR1` Payloads

ScoreForm currently uses a legacy QR payload format:

```text
OMR1|class=english9_p2|aid=rj_act1_quiz|sid=1001
```

Current fields:

```text
class = class_id
aid   = assignment_id
sid   = student_id
```

Legacy `OMR1` payloads should remain parseable by `pds-core`.

Existing ScoreForm sheets, packets, and scans should not be broken casually.

A future `pds-core` parser should support both:

* legacy `OMR1` payloads;
* shared `PDS1` payloads.

When parsed, an `OMR1` payload should be normalized into the same internal route shape used by newer payloads.

Recommended normalized interpretation:

```text
schema        = OMR1
module        = scoreform
class_id      = <class>
assignment_id = <aid>
student_id    = <sid>
page          = 1
metadata      = {}
```

Because `OMR1` does not include a page field, `page` should default to `1` when represented internally.

This does not require ScoreForm to start generating `PDS1` immediately. ScoreForm can continue generating `OMR1` while consuming shared parsing or routing helpers from `pds-core`.

## Shared `PDS1` Payload Format

The first shared Paper Data Suite QR payload format should be `PDS1`.

Recommended format:

```text
PDS1|module=<module>|class=<class_id>|aid=<assignment_id>|sid=<student_id>|page=<page_number>
```

Example ScoreForm payload:

```text
PDS1|module=scoreform|class=english9_p2|aid=rj_act1_quiz|sid=1001|page=1
```

Example Quillan payload:

```text
PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=1
```

Example Quillan writing-response payload with a document type:

```text
PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=1|doc=response
```

Example future ScoreForm payload with a document type:

```text
PDS1|module=scoreform|class=english9_p2|aid=rj_act1_quiz|sid=1001|page=1|doc=answer_sheet
```

## Payload Grammar

A `PDS1` payload should follow this grammar:

```text
PDS1|key=value|key=value|key=value
```

Rules:

* The first segment must be exactly `PDS1`.
* Remaining segments must be `key=value` pairs.
* Segments are separated by the pipe character: `|`.
* Keys must be unique within a payload.
* Required keys must be present.
* Empty keys are invalid.
* Empty values are invalid unless a future field explicitly allows them.
* Unknown optional keys may be preserved as metadata.
* Required fields should be parsed into explicit payload attributes.
* Optional fields may be parsed into explicit attributes or preserved in metadata.

The order of fields after `PDS1` should not matter to the parser.

Preferred canonical serialization order:

```text
PDS1|module=<module>|class=<class_id>|aid=<assignment_id>|sid=<student_id>|page=<page_number>|doc=<doc_type>|pages=<total_pages>|part=<part>|form=<form>|attempt=<attempt>|template=<template>
```

Only fields with values should be emitted.

## Required Fields

Required `PDS1` fields:

| Field    | Meaning                                   | Example                |
| -------- | ----------------------------------------- | ---------------------- |
| `module` | Paper Data Suite module identifier        | `scoreform`, `quillan` |
| `class`  | Class/course section identifier           | `english12_p4`         |
| `aid`    | Assignment identifier                     | `personal_narrative`   |
| `sid`    | Student identifier                        | `1001`                 |
| `page`   | Page number within the generated document | `1`                    |

Internal normalized names:

| QR Field | Internal Name   |
| -------- | --------------- |
| `module` | `module`        |
| `class`  | `class_id`      |
| `aid`    | `assignment_id` |
| `sid`    | `student_id`    |
| `page`   | `page`          |

Initial allowed `module` values:

* `scoreform`
* `quillan`

`page` must be a positive integer.

## Optional Fields

Recommended optional fields:

| Field      | Meaning                                         | Example                                       |
| ---------- | ----------------------------------------------- | --------------------------------------------- |
| `doc`      | Document/page type                              | `response`, `answer_sheet`, `cover`, `rubric` |
| `pages`    | Total number of pages in the generated document | `3`                                           |
| `part`     | Draft/revision/submission part                  | `draft`, `final`, `revision`                  |
| `form`     | Form or layout version                          | `v1`                                          |
| `attempt`  | Attempt number                                  | `1`                                           |
| `template` | Template identifier                             | `lined_response_v1`                           |

Potential Quillan payload:

```text
PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=2|pages=3|doc=response|template=lined_response_v1
```

Potential ScoreForm payload:

```text
PDS1|module=scoreform|class=english9_p2|aid=rj_act1_quiz|sid=1001|page=1|doc=answer_sheet|form=v1
```

Optional fields should not be required for initial routing. Required fields should be enough to locate the class, assignment, student, and page.

## Identifier Validation Rules

The shared contract must distinguish between display names and identifiers.

Display names may contain spaces, punctuation, and human-readable formatting.

Examples:

```text
English 12 Period 4
Personal Narrative Essay
Jane Doe
```

Identifiers are path-bearing and QR-bearing values. They must be safe for filesystem paths and payload parsing.

Examples:

```text
english12_p4
personal_narrative
1001
```

At minimum, the following fields should be validated as safe identifiers:

* `module`
* `class`
* `aid`
* `sid`
* optional identifier-like fields such as `doc`, `part`, `form`, `attempt`, and `template`

Recommended identifier rule:

```text
letters, numbers, underscores, and hyphens only
```

Recommended regex:

```text
^[A-Za-z0-9_-]+$
```

Rejected values should include:

* empty strings;
* spaces;
* path separators such as `/` or `\`;
* relative path traversal such as `..`;
* absolute paths;
* shell metacharacters;
* URL-like values;
* pipe characters;
* equals signs;
* values with leading or trailing whitespace.

Examples of invalid identifiers:

```text
English 12
../english12
classes/english12
C:\classes\english12
english12;p4
https://example.com
personal|narrative
aid=personal_narrative
```

The `page` field is not a general identifier. It must be parsed and validated as a positive integer.

The optional `pages` field, when present, must also be a positive integer.

If both `page` and `pages` are present, `page` must be less than or equal to `pages`.

## Parsed Payload Model

A future implementation should parse supported QR payloads into a normalized object.

Conceptual model:

```text
QrPayload
  schema: str
  module: str
  class_id: str
  assignment_id: str
  student_id: str
  page: int
  metadata: dict[str, str]
```

For `PDS1`, `schema` should be:

```text
PDS1
```

For legacy ScoreForm payloads, `schema` should be:

```text
OMR1
```

Example parsed `PDS1` payload:

Input:

```text
PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=2|doc=response
```

Normalized object:

```json
{
  "schema": "PDS1",
  "module": "quillan",
  "class_id": "english12_p4",
  "assignment_id": "personal_narrative",
  "student_id": "1001",
  "page": 2,
  "metadata": {
    "doc": "response"
  }
}
```

Example parsed legacy `OMR1` payload:

Input:

```text
OMR1|class=english9_p2|aid=rj_act1_quiz|sid=1001
```

Normalized object:

```json
{
  "schema": "OMR1",
  "module": "scoreform",
  "class_id": "english9_p2",
  "assignment_id": "rj_act1_quiz",
  "student_id": "1001",
  "page": 1,
  "metadata": {}
}
```

The normalized object should let module code route a payload without needing to know every historical payload format.

## Error Cases

A future implementation should define clear exception types or error results for invalid QR payloads.

Malformed payload cases:

* unsupported schema prefix;
* missing required fields;
* duplicate keys;
* segment without `=`;
* empty key;
* empty value;
* invalid page number;
* invalid total page count;
* `page` greater than `pages`;
* unsupported module;
* unknown required-field equivalent;
* extra delimiters that produce empty segments.

Unsafe identifier cases:

* invalid `module`;
* invalid `class`;
* invalid `aid`;
* invalid `sid`;
* invalid identifier-like optional metadata;
* path traversal attempt;
* absolute path attempt;
* embedded path separator;
* embedded payload delimiter.

Suggested future error categories:

```text
QrPayloadError
InvalidPayloadFormatError
MissingPayloadFieldError
InvalidPayloadFieldError
UnsafeIdentifierError
UnsupportedPayloadSchemaError
UnsupportedModuleError
RouteResolutionError
```

Implementation can begin with fewer exception classes if that is simpler, but the design should preserve these distinctions.

## Shared Routing Contract

The shared routing contract should resolve normalized QR metadata into safe local paths.

Recommended shared base structure:

```text
classes/
  <class_id>/
    roster.csv
    assignments/
      <assignment_id>/
        assignment.json
        templates/
        scans/
        submissions/
        results/
        debug/
```

Required shared route components:

```text
classes/<class_id>/
classes/<class_id>/roster.csv
classes/<class_id>/assignments/<assignment_id>/
classes/<class_id>/assignments/<assignment_id>/assignment.json
```

Recommended assignment-level folders:

```text
templates/
scans/
submissions/
results/
debug/
```

These folders should mean:

| Folder         | Meaning                                                      |
| -------------- | ------------------------------------------------------------ |
| `templates/`   | Generated printable materials for an assignment              |
| `scans/`       | Assignment-associated scanned source or processed scan files |
| `submissions/` | Student-specific routed submissions                          |
| `results/`     | Module-specific outputs, scores, summaries, exports          |
| `debug/`       | Debug artifacts that should not clutter the project root     |

`pds-core` should provide safe route resolution helpers, but module-specific code should decide what files to place in those folders.

## Shared Route Examples

Class folder:

```text
classes/english12_p4/
```

Roster path:

```text
classes/english12_p4/roster.csv
```

Assignment folder:

```text
classes/english12_p4/assignments/personal_narrative/
```

Assignment config path:

```text
classes/english12_p4/assignments/personal_narrative/assignment.json
```

Assignment templates folder:

```text
classes/english12_p4/assignments/personal_narrative/templates/
```

Assignment scans folder:

```text
classes/english12_p4/assignments/personal_narrative/scans/
```

Student submission folder:

```text
classes/english12_p4/assignments/personal_narrative/submissions/1001/
```

Assignment results folder:

```text
classes/english12_p4/assignments/personal_narrative/results/
```

Assignment debug folder:

```text
classes/english12_p4/assignments/personal_narrative/debug/
```

Route resolution must not allow identifiers to escape the project root.

## ScoreForm Routing Compatibility

Current ScoreForm behavior routes selected-response results to:

```text
classes/<class_id>/assignments/<assignment_id>/results.csv
```

Current ScoreForm folder direction includes:

```text
classes/
  <class_id>/
    roster.csv
    assignments/
      <assignment_id>/
        assignment.json
        results.csv
        templates/
          class_packet.pdf
          individual/
            <student_id>_<last>_<first>.pdf
        scans/
        debug/
```

The shared contract should not force an immediate breaking change to this layout.

For compatibility, `pds-core` should be able to support the current ScoreForm path:

```text
classes/<class_id>/assignments/<assignment_id>/results.csv
```

A future ScoreForm migration may choose to move toward:

```text
classes/<class_id>/assignments/<assignment_id>/results/results.csv
```

That should be a separate explicit migration issue.

Until then:

* `pds-core` should support shared assignment-folder resolution;
* ScoreForm may continue writing `results.csv` at its current path;
* ScoreForm may later choose to write outputs under `results/`;
* parsers should support both legacy `OMR1` and future `PDS1`.

## Quillan Routing Direction

Quillan should eventually support printable writing-response templates with QR metadata and lined writing space.

A Quillan writing-response sheet should likely include:

* Paper Data Suite / Quillan identifying header;
* class name or class ID;
* assignment title or assignment ID;
* student name or student ID;
* QR code;
* page number;
* optional total pages;
* lined writing area;
* optional continuation-page support;
* optional prompt text or abbreviated directions;
* optional rubric/standards reference later.

Recommended future Quillan assignment structure:

```text
classes/
  english12_p4/
    roster.csv
    assignments/
      personal_narrative/
        assignment.json
        templates/
          class_packet.pdf
          individual/
            1001_doe_jane.pdf
            1002_smith_marcus.pdf
        scans/
          original/
          processed/
        submissions/
          1001/
            response_page_1.pdf
            response_page_2.pdf
            metadata.json
            tags.json
            score.json
            feedback.md
          1002/
            response_page_1.pdf
            metadata.json
            tags.json
            score.json
            feedback.md
        results/
          scores.csv
          tags.csv
          standards_summary.csv
        debug/
```

The shared route contract should support this structure without requiring Quillan to depend on ScoreForm.

For Quillan, page metadata is important because writing responses may span multiple pages.

Example Quillan QR payload:

```text
PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=2|pages=3|doc=response
```

This should route conceptually to:

```text
classes/english12_p4/assignments/personal_narrative/submissions/1001/
```

The module may then store the scanned page as:

```text
response_page_2.pdf
```

or another module-defined page artifact.

`pds-core` should provide the safe directory route. Quillan should decide the exact file naming and writing-review metadata.

## Raw Scans vs Routed Submissions

The contract must distinguish raw scan files from routed submissions.

### Raw scan files

Raw scans are original input files produced by a scanner or upload process.

A raw scan file may contain:

* one student response;
* multiple student responses;
* multiple pages from one assignment;
* mixed assignments;
* mixed classes;
* pages out of order;
* duplicate pages;
* rescans;
* missing pages.

Raw scans belong in a scan inbox or archive and should not be treated as equivalent to a clean student submission.

Recommended scan inbox:

```text
scans_inbox/
```

Possible future archive location:

```text
scans_archive/
```

Possible module/date archive convention:

```text
scans_archive/<module>/<date>/
```

Raw scans should generally be preserved unchanged unless the user explicitly chooses otherwise.

### Routed submissions

A routed submission is the organized system representation of one student's response to one assignment.

Recommended routed submission folder:

```text
classes/<class_id>/assignments/<assignment_id>/submissions/<student_id>/
```

For Quillan, a routed submission folder may contain:

* scanned page PDFs/images;
* source metadata;
* page metadata;
* OCR/transcription output later;
* manual transcription later;
* tags;
* scores;
* feedback;
* review status.

For ScoreForm, a routed submission may be less central because selected-response scoring often aggregates directly into results files, but future audit workflows may still preserve per-student scan artifacts.

## Source Metadata and Auditability

Routing should preserve enough metadata to support review and audit.

A future routed submission metadata file may include:

```json
{
  "module": "quillan",
  "class_id": "english12_p4",
  "assignment_id": "personal_narrative",
  "student_id": "1001",
  "pages": [
    {
      "page": 1,
      "source_scan": "scan_batch_2026-06-08.pdf",
      "source_page": 4,
      "routed_file": "response_page_1.pdf",
      "qr_payload": "PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=1|pages=2|doc=response"
    },
    {
      "page": 2,
      "source_scan": "scan_batch_2026-06-08.pdf",
      "source_page": 5,
      "routed_file": "response_page_2.pdf",
      "qr_payload": "PDS1|module=quillan|class=english12_p4|aid=personal_narrative|sid=1001|page=2|pages=2|doc=response"
    }
  ],
  "created_at": "2026-06-08T12:00:00",
  "routing_status": "routed"
}
```

This example is not a required implementation target for the first `pds-core` issue. It illustrates the kind of audit metadata that the routing contract should not block.

## `pds-core` Responsibilities

`pds-core` should eventually provide shared, module-neutral utilities for:

* validating safe identifiers;
* parsing `PDS1` payloads;
* building `PDS1` payloads;
* parsing legacy `OMR1` payloads;
* normalizing payloads into a shared internal object;
* validating required payload fields;
* preserving optional metadata;
* validating page numbers;
* resolving safe class routes;
* resolving safe assignment routes;
* resolving safe student submission routes;
* resolving scan inbox paths;
* resolving scan archive paths;
* preventing path traversal;
* supporting project-root/home-directory configuration.

`pds-core` should not know how to score an answer sheet or tag an essay.

## Module-Specific Responsibilities

### ScoreForm-specific

`pds-scoreform` should remain responsible for:

* generating OMR answer sheets;
* rendering answer boxes;
* rendering registration/corner marks;
* selected-response scoring;
* answer-key handling;
* ambiguous mark detection;
* ScoreForm-specific CSV outputs;
* ScoreForm-specific debug images.

### Quillan-specific

`pds-quillan` should remain responsible for:

* creating writing assignments;
* generating lined response sheets;
* generating class writing packets;
* managing writing submissions;
* evaluating basic writing requirements;
* tagging writing evidence;
* scoring writing with rubrics;
* generating feedback;
* exporting writing reports;
* OCR/transcription workflows if added later.

## Out of Scope

This design issue should not implement:

* QR image generation;
* QR decoding from scans;
* route helper code;
* dataclasses;
* parser code;
* ScoreForm migration;
* Quillan template generation;
* scan splitting;
* OCR;
* handwriting recognition;
* GUI workflows;
* gradebook export;
* cloud sync.

Implementation should happen in later issues after this contract is documented.

## Future Migration Notes

Recommended staged migration:

1. Document the shared contract in `pds-core`.
2. Implement identifier validation in `pds-core`.
3. Implement a shared normalized QR payload model in `pds-core`.
4. Implement `PDS1` parser and builder in `pds-core`.
5. Implement legacy `OMR1` parser in `pds-core`.
6. Implement shared route helpers in `pds-core`.
7. Add `pds-core` as a dependency of `pds-scoreform`.
8. Replace ScoreForm’s local identifier/path logic with `pds-core` helpers.
9. Replace ScoreForm’s local `OMR1` parser with `pds-core` legacy parsing.
10. Add optional ScoreForm `PDS1` generation.
11. Decide later whether new ScoreForm templates should default to `PDS1`.
12. Add `pds-core` as a dependency of `pds-quillan`.
13. Use `pds-core` identifiers and route helpers in Quillan.
14. Use `pds-core` QR payload building for Quillan writing-response sheets.
15. Implement Quillan printable writing-response templates.
16. Implement Quillan scan routing only after the shared parser/router is stable.

Existing `OMR1` ScoreForm payloads should remain supported during migration.

New Quillan paper workflows should start with `PDS1`.

## Summary

The shared QR and routing contract should allow Paper Data Suite modules to agree on:

* how QR payloads are formatted;
* how legacy ScoreForm payloads are preserved;
* how identifiers are validated;
* how payloads normalize to a shared internal model;
* how class, assignment, and student submission paths are resolved;
* how raw scans differ from routed submissions;
* what belongs in `pds-core`;
* what remains module-specific.

The immediate priority is documentation and design stability. Implementation should proceed only after this contract is reviewed and accepted.
