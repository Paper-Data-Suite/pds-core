# Starter Standards

`pds-core` ships optional starter standards packs for teachers and developers
who need a shared standards library before building module assignments.

Starter standards are setup helpers. They install shared
`StandardDefinition` records and reusable `StandardsProfile` pools into:

```text
<PDS workspace root>/standards/library.json
```

Installing starter standards does not record standards usage, does not create
usage ledgers, and does not create ScoreForm, Quillan, class, assignment,
roster, submission, review, scan, or export files.

If the workspace itself needs to be inspected or created first, use
`core -> Workspace Settings` or `pds-core workspace validate`. Workspace
validation creates the workspace root, `.pds/workspace.json`, and shared
baseline class and scan directories; it does not install starter standards or
create module-specific folders. See
[`workspace_management.md`](workspace_management.md).

## Bundled Pack

The first bundled pack is:

```text
njsls_ela_2023
```

It was generated from the local Pandoc Markdown reference file
`2023_NJSLS_ELA.md` and committed as package data at:

```text
pds_core/starter_data/standards/njsls_ela_2023_library.json
```

The pack contains 64 parent-standard definitions and 71 lettered subskill
definitions from the 2023 NJSLS-ELA high school grade bands, for 135 standards
total, plus 2 reusable profiles:

- `english10_2023_njsls_ela`
- `english12_2023_njsls_ela`

Each lettered subskill is an ordinary, first-class `StandardDefinition`. Its
durable `standard_id` and display `code` extend the parent value with the
subskill letter. Its `short_name` combines the parent skill name with a concise,
teacher-readable label derived from the subskill description, while its
`category_path` and tags identify the parent grouping.
Both profiles list parent standards followed by their subskills, so downstream
modules can select either granularity by durable `standard_id`.

No hierarchy schema is required for this representation. Parent/child rollup
and mastery aggregation are outside the standards library's scope. Starter
standards are setup metadata, not grading policy or curriculum guidance.

## CLI Workflow

List available packs:

```powershell
pds-core standards starter list
```

Preview a pack:

```powershell
pds-core standards starter preview njsls_ela_2023
```

Validate bundled starter data:

```powershell
pds-core standards starter validate
pds-core standards starter validate njsls_ela_2023
```

Install into the active workspace:

```powershell
pds-core standards starter install njsls_ela_2023
```

Install writes only the canonical shared standards library path. If a
workspace library already exists, missing standards and profiles are merged,
identical records are skipped, and conflicting existing records are refused.
Replacing conflicting starter records requires:

```powershell
pds-core standards starter install njsls_ela_2023 --overwrite
```

## Menu Workflow

The direct standards menu includes:

```text
pds-core standards menu
-> Standards Library
-> 5. Starter Standards
```

The starter menu can list, preview, validate, and install starter standards
packs. Preview, validate-one-pack, and install workflows show available packs
as numbered choices, then display the selected pack metadata. Teachers do not
need to type internal pack IDs in the menu. Installation still requires typing
`YES` before writing `standards/library.json`.

## Profiles Are Pools

A standards profile is a reusable selectable pool, not an assignment template.
For example, Quillan can offer `english10_2023_njsls_ela` during assignment
creation, then the teacher still chooses the assignment's focus standards from
that profile. ScoreForm can use the same shared definitions and profiles for
question-level alignment while keeping answer keys and scoring in ScoreForm.

Teachers remain responsible for verifying starter data against local and
state requirements. Starter data is not curriculum guidance, grading policy,
mastery evidence, or official legal advice.
