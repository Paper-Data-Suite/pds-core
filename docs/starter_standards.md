# Starter Standards

`pds-core` ships optional starter standards packs for teachers and developers
who need a shared standards library before building module assignments.

Starter standards are setup helpers. They install shared framework
provenance, `StandardDefinition` records, and reusable `StandardsProfile` pools into:

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

## Bundled Packs

Core currently bundles:

- `ap_csp_fall_2023`
- `njsls_clks_2020`
- `njsls_csdt_2020`
- `njsls_ela_2023`

### AP Computer Science Principles Fall 2023 Framework References

The `ap_csp_fall_2023` pack represents the College Board **AP Computer Science
Principles Course and Exam Description — Effective Fall 2023** as a minimal
standards-like reference framework. It is intentionally not a reproduction of
the College Board framework.

The pack contains **95 reference definitions**:

- 5 Big Idea references: `CRD`, `DAT`, `AAP`, `CSN`, and `IOC`;
- 64 unique Learning Objective identifiers;
- 6 Computational Thinking Practice references;
- 20 published Computational Thinking skill identifiers.

The five Big Idea and six Practice titles are retained as short structural
labels. Learning Objective and practice-skill records contain only their
published identifiers plus Core-authored reference text directing teachers to
the official CED. Essential Knowledge, Learning Objective prose, practice-skill
descriptions, assessment content, AP Classroom material, Create performance-task
directions, scoring guidance, and College Board logos are not bundled.

The pack contains three reusable pools:

- `ap_csp_course_content_fall_2023` — 69 course-content references (5 Big Ideas + 64 Learning Objective IDs);
- `ap_csp_computational_thinking_fall_2023` — 26 computational-thinking references (6 Practices + 20 skill IDs);
- `ap_csp_fall_2023` — the combined 95-reference pool.

College Board describes the source as effective **Fall 2023**. Core preserves
that phrase as the framework version instead of inventing a calendar date for
`adoption_date` or `implementation_date`. AP CSP is not assigned a source grade
band in this pack, so CLI and menu output display the empty grade-band metadata
as `not specified` rather than introducing a fictional grade range. College
Board currently identifies Fall 2023 as the CED to use and has announced an
updated CED for the 2027-28 school year; a future Core pack should receive a new
framework identity rather than silently replacing this edition.

Framework metadata links the College Board CED and College Board Educator Legal
Terms. The legal metadata is descriptive: it records that College Board owns or
licenses the underlying content and that the starter pack intentionally omits
protected framework prose. It does not characterize College Board material as
open source or freely redistributable.

`AP`, `Advanced Placement`, and related marks belong to College Board. Paper
Data Suite uses the course name only to identify the referenced framework, does
not bundle College Board branding assets, and is not affiliated with or endorsed
by College Board. Installing the pack does not represent AP Course Audit
authorization.

The AP pack installs independently of New Jersey standards. For teachers who
also use `njsls_csdt_2020`, [`ap_csp_njsls_alignment.md`](ap_csp_njsls_alignment.md)
provides a Paper Data Suite-curated, non-authoritative instructional crosswalk
and demonstrates a mixed-source local profile. That document does not claim
College Board/NJDOE equivalence or endorsement. Generalized first-class
cross-framework mapping persistence remains future work.

### 2023 NJSLS ELA

The `njsls_ela_2023` pack was generated from the local Pandoc Markdown reference file
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



### 2020 NJSLS Career Readiness, Life Literacies and Key Skills

The `njsls_clks_2020` pack is curated from the official June 2020 New Jersey
Student Learning Standards – Career Readiness, Life Literacies, and Key Skills
publication:

```text
https://www.nj.gov/education/standards/clicks/Docs/2020NJSLS-CLKS.pdf
```

It contains all **301 coded Performance Expectations** in the generally
applicable portions of the framework: `9.1` Personal Financial Literacy, `9.2`
Career Awareness, Exploration, Preparation and Training, and `9.4` Life
Literacies and Key Skills. Standard `9.3` Career and Technical Education is not
bundled because it describes specialist expectations associated with completion
of a CTE Program of Study rather than the cross-curricular standards this starter
pack is intended to provide.

The source's end-of-grade 2, 5, 8, and 12 sections map to Core's reusable
`K-2`, `3-5`, `6-8`, and `9-12` grade-band labels. Individual standards keep
`course = null` because CLKS is designed for integration across academic and
technical content areas rather than one named course.

The pack includes four reusable high-school profile pools:

- `personal_financial_literacy_9_12_2020_njsls_clks` — all 55 grade-12 `9.1` expectations;
- `career_readiness_9_12_2020_njsls_clks` — all 23 grade-12 `9.2` expectations;
- `life_literacies_9_12_2020_njsls_clks` — all 29 grade-12 `9.4` expectations;
- `clks_9_12_2020_njsls_clks` — the source-ordered combined pool of all 107 grade-12 expectations.

The combined profile exists so assignment consumers that select one
`standards_profile_id` can still choose focus standards across the three CLKS
areas. It is a selectable pool, not a curriculum sequence or a recommendation
to teach all 107 expectations together.

Only coded Performance Expectations become `StandardDefinition` records. Core
Idea prose and the uncoded Career Readiness, Life Literacies, and Key Skills
Practices remain framework context. Interdisciplinary references printed inside
9.4 expectations remain part of the source wording; this pack does not convert
them into first-class cross-framework mappings.

The State Board adopted the 2020 NJSLS on June 3, 2020. Although the original
schedule called for CLKS implementation in September 2021, the State Board
extended implementation of the affected 2020 standards during the COVID-19
public-health emergency, making September 2022 the applicable implementation
date. A revised CLKS framework was adopted in 2026 for implementation in
September 2027, so this starter pack intentionally remains the 2020 edition.
Core does not switch frameworks automatically based on dates.

The framework metadata follows the same State of New Jersey Conditions of Use
handling as `njsls_csdt_2020`: the State's reuse terms are recorded
descriptively, not treated as an open-source software license, and third-party
rights plus State/agency seal and logo restrictions remain outside the pack.

The 2020 publication also contains source-code irregularities that Core
preserves deliberately. The grade-2 `9.2` Career Awareness section publishes
its four expectations as `9.1.2.CAP.1` through `9.1.2.CAP.4`, so those display
codes are retained while their subject/category metadata correctly identifies
the 9.2 section. Likewise, the grade-2 Global and Cultural Awareness expectation
is printed as `9.4.2.GCA:1`; the colon is retained. Other glossary-versus-table
abbreviation variations such as `RMI`/`RM` and `EGI`/`EG` are preserved from the
actual Performance Expectation codes instead of being silently normalized.

### 2020 NJSLS Computer Science and Design Thinking

The `njsls_csdt_2020` pack is curated from the official June 2020 New Jersey
Student Learning Standards – Computer Science and Design Thinking publication:

```text
https://www.nj.gov/education/standards/compsci/Docs/2020%20NJSLS-CSDT.pdf
```

It contains all **163 coded Performance Expectations** in Standards `8.1`
Computer Science and `8.2` Design Thinking across the source's end-of-grade 2,
5, 8, and 12 expectations. Core maps those endpoints to the reusable grade-band
labels `K-2`, `3-5`, `6-8`, and `9-12` while preserving every official display
code exactly.

The source's ten disciplinary concepts are represented through ordinary Core
metadata: Computing Systems (`CS`), Networks and the Internet (`NI`), Impacts
of Computing (`IC`), Data & Analysis (`DA`), Algorithms & Programming (`AP`),
Engineering Design (`ED`), Interaction of Technology and Humans (`ITH`), Nature
of Technology (`NT`), Effects of Technology on the Natural World (`ETW`), and
Ethics & Culture (`EC`). Only coded Performance Expectations become selectable
`StandardDefinition` records. The seven cross-cutting Computer Science and
Design Thinking Practices and uncoded Core Idea prose remain framework context
rather than fabricated standards.

The pack includes two high-school reusable profile pools:

- `computer_science_9_12_2020_njsls_csdt` — all 26 `8.1.12.*` Performance Expectations;
- `design_thinking_9_12_2020_njsls_csdt` — all 18 `8.2.12.*` Performance Expectations.

These are source-faithful NJSLS pools, not AP Computer Science Principles
profiles. AP CSP framework references are available through `ap_csp_fall_2023`,
and the PDS-curated non-authoritative NJSLS alignment guide is documented
separately. Likewise, the 2020 source explicitly moved former Educational Technology
content into NJSLS Career Readiness, Life Literacies & Key Skills `9.4`; those
expectations are not duplicated in this pack.

The State Board adopted the 2020 NJSLS on June 3, 2020, and the NJDOE
implementation schedule placed Computer Science and Design Thinking in
September 2022. A revised CSDT framework was adopted in 2026 for implementation
in September 2027, so the 2020 pack remains the implemented framework represented
by Core for the 2026-2027 school year. Core does not automatically switch
frameworks based on dates.

The framework metadata also links the State of New Jersey Conditions of Use.
Those terms say State information may generally be viewed, copied, or distributed
without obligation to the State unless particular material states otherwise,
while warning that third-party copyright, trademark, or other restrictions may
still apply. Core records that statement descriptively rather than treating it as
an open-source software license; State and agency seals/logos are not bundled.

One source-layout anomaly is preserved deliberately: `8.2.12.ETW.4` appears
visually beneath the final Ethics & Culture table in the 2020 PDF, but the
published code remains `ETW`, and the source coding key defines `ETW` as Effects
of Technology on the Natural World. Core therefore preserves the official code
and classifies the record under that disciplinary concept rather than silently
renaming it.

## Framework Provenance

Starter packs may carry framework-level provenance in the same
`StandardsLibrary` that contains definitions and profiles. Installing a starter
pack therefore preserves the framework record in `standards/library.json`; the
metadata does not disappear after installation.

The `njsls_ela_2023` pack identifies the 2023 New Jersey Student Learning
Standards for English Language Arts as a framework issued by the New Jersey
State Board of Education and published by the New Jersey Department of
Education. The State Board adopted the revised standards on October 4, 2023,
and the ELA implementation deadline remained September 2024. The framework
record links to the NJDOE 2023 NJSLS-ELA source page. No explicit
redistribution license is asserted by the starter data.

Framework lifecycle metadata is descriptive. It does not change the
`active` flag on individual standards, choose curriculum for a teacher, or
create standards-usage events. Multiple editions may coexist when an authority
has adopted a successor before its implementation date.

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
