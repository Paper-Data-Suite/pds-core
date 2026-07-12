# Standards Management Workflow

## Purpose

`pds-core` owns the shared standards library used by Paper Data Suite modules.
This guide is the practical workflow reference for:

- power users who manage standards with direct CLI commands;
- teachers who manage standards through the menu;
- module developers who consume standards through `pds-core` selection APIs.

All examples are synthetic. Do not use real student data, rosters,
assignments, essays, scans, answer sheets, reports, or classroom records in
standards-library examples.

## Canonical Storage Path

The shared workspace standards library lives at:

```text
<PDS workspace root>/standards/library.json
```

Read-only operations treat a missing library as an empty library and do not
create this file. Mutation commands may create `standards/` and
`standards/library.json`.

Standards usage ledgers are separate from library management and are not
created by standards-library commands. ScoreForm, Quillan, class folders, and
other module folders are not created by standards-library management.

Starter standards installation follows the same storage rule: it writes only
the canonical shared library file and does not create usage ledgers or module
folders.

For workspace setup, validation, reset, and clean simulation workspace
workflows, see [`workspace_management.md`](workspace_management.md). From the
teacher menu, use `core -> Workspace Settings`.

## Power-User CLI Workflow

Use an explicit workspace while testing or drafting standards:

```powershell
$workspace = ".\tmp-pds-workspace"
```

Validate or create that workspace root before writing standards data:

```powershell
pds-core --workspace $workspace workspace validate
```

Add a synthetic umbrella standard:

```powershell
pds-core --workspace $workspace standards add `
  --standard-id njsls-ela:L.KL.11-12.2 `
  --code L.KL.11-12.2 `
  --source "NJSLS-ELA 2023" `
  --short-name "Apply Language in Context" `
  --description "Apply knowledge of language to understand how language functions in different contexts." `
  --subject "English Language Arts" `
  --course "English 12" `
  --grade-band "11-12" `
  --domain "Language" `
  --category-path "English Language Arts/Language" `
  --tag synthetic `
  --available-module pds-scoreform `
  --available-module pds-quillan
```

Add synthetic child or subpart standards:

```powershell
pds-core --workspace $workspace standards add `
  --standard-id njsls-ela:L.KL.11-12.2.A `
  --code L.KL.11-12.2.A `
  --source "NJSLS-ELA 2023" `
  --short-name "Contextual Language Choice" `
  --description "Analyze how language choices shape meaning in context." `
  --subject "English Language Arts" `
  --course "English 12" `
  --grade-band "11-12" `
  --domain "Language" `
  --category-path "English Language Arts/Language" `
  --tag synthetic

pds-core --workspace $workspace standards add `
  --standard-id njsls-ela:L.KL.11-12.2.B `
  --code L.KL.11-12.2.B `
  --source "NJSLS-ELA 2023" `
  --short-name "Language Conventions" `
  --description "Apply language conventions for clarity and style." `
  --subject "English Language Arts" `
  --course "English 12" `
  --grade-band "11-12" `
  --domain "Language" `
  --category-path "English Language Arts/Language" `
  --tag synthetic
```

Create a reusable profile and add standards by durable `standard_id`:

```powershell
pds-core --workspace $workspace standards profile create `
  --profile-id english_12_language_synthetic `
  --title "English 12 Language Synthetic" `
  --description "Synthetic English 12 language standards." `
  --subject "English Language Arts" `
  --course "English 12" `
  --source "NJSLS-ELA 2023" `
  --standard njsls-ela:L.KL.11-12.2 `
  --standard njsls-ela:L.KL.11-12.2.A `
  --standard njsls-ela:L.KL.11-12.2.B
```

Validate and inspect the library:

```powershell
pds-core --workspace $workspace standards validate
pds-core --workspace $workspace standards profile validate english_12_language_synthetic
pds-core --workspace $workspace standards list
pds-core --workspace $workspace standards search language --all
pds-core --workspace $workspace standards show njsls-ela:L.KL.11-12.2.A
pds-core --workspace $workspace standards profiles
pds-core --workspace $workspace standards profile show english_12_language_synthetic
```

Export and import a full library:

```powershell
pds-core --workspace $workspace standards export ".\synthetic-standards-library.json"
pds-core --workspace ".\tmp-imported-pds-workspace" standards import ".\synthetic-standards-library.json" --replace
pds-core --workspace ".\tmp-imported-pds-workspace" standards validate
```

Install a bundled starter standards pack:

```powershell
pds-core --workspace $workspace standards starter list
pds-core --workspace $workspace standards starter preview njsls_ela_2023
pds-core --workspace $workspace standards starter validate njsls_ela_2023
pds-core --workspace $workspace standards starter install njsls_ela_2023
```

Starter install merges missing records, skips identical records, and refuses
conflicting existing records unless `--overwrite` is supplied. The bundled
`njsls_ela_2023` pack provides English 10 and English 12 reusable standards
profiles from the 2023 NJSLS-ELA high school standards. The profiles include
parent standards and ordinary first-class records for lettered subskills;
their `short_name` values provide concise teacher-readable skill labels.
Downstream modules can select either by durable `standard_id`. This flat
representation does not define hierarchy, rollup, mastery, grading policy, or
curriculum guidance.

## Teacher-Facing Menu Workflow

Teachers can open the broader Core menu:

```text
core
-> Standards Management
-> Standards Library
-> Standards
-> Add standard
```

The direct standards route is also available:

```powershell
pds-core standards menu
```

Broad menu workflow:

1. Open the menu.
2. Add standards, including subparts when needed.
3. Create a profile from numbered standard lists.
4. Browse, search, and view standards.
5. Browse and view profiles.
6. Import or export libraries and profiles when needed.
7. Install starter standards when a prepared library/profile pool is useful.
8. Validate the library.

The menu displays teacher-readable labels such as codes, short names, titles,
sources, and descriptions. Module-facing standard selection labels prioritize
`code | short_name | source`; modules store durable `standard_id` and
`profile_id` values internally. Write operations require explicit confirmation.

## Import and Export Safety

Full-library export writes canonical `StandardsLibrary` JSON. Existing export
targets are refused unless `--overwrite` is supplied.

Full-library import validates the entire source file before writing. It
requires `--replace`, and replacing an existing workspace library also
requires `--overwrite`. Invalid imports do not partially rewrite
`standards/library.json`.

Profile export writes one canonical `StandardsProfile` JSON file. Profile
import supports explicit add or replacement behavior and validates standard
references against the current library before writing.

Starter standards install validates the bundled pack before writing. It is a
merge workflow, not full-library replacement. Existing teacher-edited records
are protected from silent overwrite.

Import/export files contain shared standards metadata only. They do not
contain student work, answer sheets, essays, scans, rosters, assignment files,
reports, grades, or module output.

## Module-Facing Selection APIs

Modules should load the shared library and store durable IDs:

```python
from pds_core.standards_selection import (
    list_profiles_for_selection,
    list_standards_for_profile_selection,
    load_standards_for_selection,
    resolve_profile_standard_selection,
)

library = load_standards_for_selection(workspace_root)

profiles = list_profiles_for_selection(
    library,
    subject="English Language Arts",
    course="English 12",
)

standards = list_standards_for_profile_selection(
    library,
    "english_12_language_synthetic",
    available_module="pds-scoreform",
)

selected = resolve_profile_standard_selection(
    library,
    profile_id="english_12_language_synthetic",
    selected_standard_ids=[
        "njsls-ela:L.KL.11-12.2",
    ],
)
```

Modules store `standard_id` and `profile_id` values. Returned labels, display
codes, titles, and descriptions are for UI display. Helper failures should be
surfaced as validation errors in the module workflow. Modules should not copy
or duplicate the standards library.

For module ownership boundaries and ScoreForm/Quillan expectations, see
[`module_standards_integration.md`](module_standards_integration.md).

## Safety and Privacy Notes

- Examples must be synthetic.
- Standards metadata should not include real student information.
- Standards management does not read student work.
- Standards management does not grade, score, or determine mastery.
- Library management does not emit standards usage events.
- Starter standards installation does not emit standards usage events.
- Review import/export files before sharing because local teacher-created
  metadata may still be sensitive.

## Non-Goals

Standards management does not:

- perform AI grading;
- decide mastery;
- score assessments;
- tag writing;
- generate feedback;
- create ScoreForm or Quillan assignment files;
- create usage events merely because a standard exists;
- create standards usage ledgers during ordinary library management;
- replace module-owned validation, reporting, scoring, or feedback behavior.
