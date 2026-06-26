# Module Standards Integration

## Purpose

This guide defines how Paper Data Suite modules should consume `pds-core`
standards management.

```text
pds-core owns shared standards identity, storage, profiles, and module-neutral standards selection/validation.

Modules own their assignment schemas, teacher workflows, scoring/tagging/reporting behavior, and module-specific interpretation of standards.
```

The deeper shared standards contract lives in
[`standards_contract.md`](standards_contract.md). This document is the
practical integration guide for `pds-quillan`, `pds-scoreform`, and future
Paper Data Suite modules.

For practical CLI, teacher-menu, import/export, and module-selection examples,
see [`standards_management_workflow.md`](standards_management_workflow.md).

## Dependency Direction

The intended dependency direction is:

```text
pds-scoreform -> pds-core
pds-quillan   -> pds-core
future module -> pds-core
```

ScoreForm and Quillan must not depend on each other. Future modules must not
create separate standards libraries when `pds-core` can provide shared
definitions, profiles, browsing, and validation.

## Storage Ownership

`pds-core` owns the canonical shared standards library:

```text
<PDS workspace root>/standards/library.json
```

This file stores shared standard definitions and reusable standards profiles.
Modules must not create competing standards libraries. Modules may store
module-owned assignment, review, report, or export data that references shared
standards by durable ID.

| Concern | Owner |
| -- | -- |
| Shared standard definitions | `pds-core` |
| Shared standards profiles | `pds-core` |
| Workspace standards storage | `pds-core` |
| Standards browsing/filtering helpers | `pds-core` |
| Standards profile validation | `pds-core` |
| ScoreForm answer keys | `pds-scoreform` |
| ScoreForm OMR scoring | `pds-scoreform` |
| ScoreForm question-level alignment | `pds-scoreform` |
| Quillan writing assignment behavior | `pds-quillan` |
| Quillan tags/comments/scores/review state | `pds-quillan` |
| Quillan feedback exports | `pds-quillan` |
| Module-specific reports | Owning module |

## Durable IDs vs Display Fields

Modules store durable references:

- `standard_id`
- `profile_id`

Modules display teacher-facing metadata from the shared library:

- standard `code`
- `short_name`
- `description`
- `source`
- `subject`
- `course`
- `domain`
- profile title
- profile description

Rules:

- modules store `standard_id` and `profile_id`;
- modules display teacher-friendly fields from the shared library;
- modules do not store `code` as the durable key;
- modules do not treat profile titles as durable keys;
- modules tolerate display metadata changing over time.

## How Modules Should Display Standards

Modules should not show raw IDs as the primary teacher-facing choice. When
teachers select standards, modules should show readable fields such as:

```text
L.KL.11-12.2 - Apply Language in Context
Apply knowledge of language to understand how language functions in different contexts...
Source: NJSLS-ELA 2023 | Subject: English Language Arts | Course: English 12 | Domain: Language
```

The module should save the durable ID:

```json
"njsls-ela:L.KL.11-12.2"
```

The module should not save only the display code:

```json
"L.KL.11-12.2"
```

`pds-core` selection helpers return display-ready items and durable IDs so
modules can keep teacher-facing display separate from durable storage.

## How Modules Should Validate Saved References

Modules should validate saved references at workflow boundaries such as:

- assignment creation;
- assignment editing;
- assignment validation;
- report/export generation;
- standards-linked review/tagging workflows.

Expected validation behavior:

- load the shared standards library from the active workspace;
- validate that `profile_id` exists when a module stores one;
- validate that `standard_id` values exist;
- when a profile and selected standards are both present, validate that
  selected standards belong to that profile;
- report missing, deprecated, or inactive references clearly;
- do not silently delete or rewrite module-owned assignment or review data.

Example:

```python
from pds_core.standards_selection import (
    load_standards_for_selection,
    resolve_profile_standard_selection,
)

library = load_standards_for_selection(workspace_root)

selected = resolve_profile_standard_selection(
    library,
    profile_id="english_12_language_standards",
    selected_standard_ids=[
        "njsls-ela:L.KL.11-12.2",
        "njsls-ela:L.VI.11-12.4",
    ],
)
```

Returned selection items are for display and use inside the module workflow.
The module persists durable `standard_id` and `profile_id` values.

## Missing, Deprecated, or Inactive Standards

Modules preserve teacher-owned data when shared references no longer resolve
cleanly. Validation reports the problem; it does not silently repair,
substitute, or delete module data.

| Case | Expected behavior |
| -- | -- |
| Missing standards library | Read-only validation reports that no shared standards library exists. Modules do not create standards storage merely by validating. Assignment data is not deleted. Teacher-facing workflows explain that standards must be created or imported in `pds-core` first. |
| Missing profile | Validation fails clearly. Module data remains unchanged. Teacher-facing workflows can offer a later path to choose another profile. |
| Missing standard | Validation fails clearly. Reports identify unresolved IDs. Module data remains unchanged. No automatic deletion or substitution occurs. |
| Inactive or deprecated standard | Modules may display it as inactive or deprecated. Historical references are preserved. Modules do not silently remove it from old assignments or reviews. Creation and edit workflows generally prefer active standards unless a teacher explicitly chooses otherwise. |

## Quillan Integration Expectations

### Assignment Configs

Quillan assignment configs should continue to store durable shared references:

```json
{
  "standards_profile_id": "english_12_language_standards",
  "focus_standards": [
    "njsls-ela:L.KL.11-12.2",
    "njsls-ela:L.VI.11-12.4"
  ]
}
```

Future Quillan assignment creation should use `pds-core` shared standards and
profile selection to replace typed entry for `standards_profile_id` and
`focus_standards`. The teacher-facing workflow should let the teacher select a
profile and then choose focus standards from that profile.

### Review Tags and Comments

Quillan review records currently use `standard_code` in structured tags and
selected comments. That is a transitional compatibility shape.

Future Quillan integration should move standards-linked review artifacts
toward durable `standard_id` references. If backward compatibility requires
`standard_code`, Quillan should treat it as display or provenance metadata,
not as the durable shared key.

Target shape for a future Quillan review tag:

```json
{
  "tag_id": "tag_0001",
  "label": "Evidence needs more explanation",
  "polarity": "developing",
  "standard_id": "njsls-ela:W.AW.11-12.1",
  "comment_id": "evidence_needs_explanation"
}
```

If `standard_code` remains for compatibility, the distinction is:

```json
{
  "standard_id": "njsls-ela:W.AW.11-12.1",
  "standard_code": "W.AW.11-12.1"
}
```

`standard_id` is the durable shared reference. `standard_code` is display or
provenance metadata.

### Quillan-Owned Data

Quillan continues to own:

- writing assignment configuration;
- writing type;
- tagging mode;
- focus standards behavior;
- teacher tags;
- teacher notes;
- teacher comments;
- teacher-entered scores;
- review states;
- feedback exports;
- standards summaries;
- Quillan-specific comment banks;
- hotwords;
- subskills;
- severity defaults;
- feedback templates.

These must not move into `pds-core` merely because they are standards-adjacent.

### Quillan Validation

Quillan should validate that:

- assignment `standards_profile_id` exists in `pds-core`;
- `focus_standards` exist and belong to the selected profile;
- standards-linked review artifacts resolve when workspace-aware validation is
  requested;
- missing references are reported without destructive mutation.

## ScoreForm Integration Expectations

### Assignment Configs

ScoreForm assignment files may include:

```json
{
  "standards_profile_id": "english_12_language_standards",
  "standards": {
    "1": [],
    "2": ["njsls-ela:L.KL.11-12.2"],
    "3": [
      "njsls-ela:L.KL.11-12.2",
      "njsls-ela:L.VI.11-12.4"
    ]
  }
}
```

Rules:

- `standards_profile_id` is optional unless shared-library validation is
  requested;
- `standards` is assignment-local question alignment;
- standards values are durable shared `standard_id` strings;
- empty lists are allowed;
- missing question keys are allowed if current ScoreForm validation allows or
  normalizes them;
- ScoreForm must not store full standard definitions inside assignment JSON.

### ScoreForm Workflows

Future ScoreForm workflows should use shared `pds-core` standards selection to
attach standards to:

- assessment forms;
- answer keys;
- individual questions;
- reporting outputs;
- item-level performance summaries.

The teacher-facing workflow should show readable standard labels and
descriptions but save durable IDs.

### ScoreForm-Owned Data

ScoreForm continues to own:

- answer keys;
- answer choices;
- question counts;
- OMR scoring;
- scan handling;
- result CSVs;
- item-level performance calculations;
- assignment-local standards alignment;
- ScoreForm-specific reports/exports.

`pds-core` does not decide what a correct answer means, how a scanned form is
scored, or how ScoreForm reports item performance.

### ScoreForm Validation

ScoreForm should validate that:

- question numbers are valid for the assignment;
- question-level `standard_id` values exist in the shared `pds-core` library
  when shared validation is requested;
- if `standards_profile_id` is present, selected question-level standards
  belong to that profile;
- missing or deprecated standards are reported clearly;
- validation does not alter scoring behavior.

## Future Module Guidance

Future modules should:

- depend on `pds-core` for standards identity, storage, profile browsing, and
  validation;
- store durable `standard_id` and `profile_id` references;
- display teacher-facing standard metadata from `pds-core`;
- keep module-specific assignment, review, and report data in their own
  schemas;
- validate saved references before creating reports or using standards-linked
  workflows;
- handle missing or deprecated standards without silently deleting or
  rewriting teacher data;
- avoid creating module-specific standards libraries unless a later
  architecture decision explicitly allows it.

Future modules must not:

- duplicate shared standard definitions in module storage;
- use display `code` as a durable key;
- treat standards usage as mastery, proficiency, or grade evidence by itself;
- create standards usage events without a teacher-controlled workflow and
  explicit contract;
- depend on another assignment module to interpret standards.

## Usage Events Are Out of Scope for This Ticket

Assignment alignment is not the same as standards usage.

Attaching a standard to a ScoreForm question does not automatically mean the
standard was assessed unless a future usage policy says so. Selecting a
Quillan focus standard does not automatically mean the standard was taught,
practiced, assessed, or reviewed.

Usage-event emission should be handled by future module-specific
implementation tickets. No backfill from existing assignment configs should
occur without explicit migration policy and teacher-visible confirmation.

## Non-Goals

This ticket must not:

- change Quillan assignment creation;
- change Quillan review records;
- migrate `standard_code` to `standard_id`;
- change ScoreForm assignment creation;
- change ScoreForm standards editing;
- emit standards usage events;
- create usage ledgers;
- change `pds-core` storage schema;
- add new `pds-core` APIs unless a tiny documentation helper is absolutely
  necessary;
- modify sibling repositories.

This is a documentation issue.
