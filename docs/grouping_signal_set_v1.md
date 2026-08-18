# `grouping_signal_set_v1` Contract

## Status and authority

This document is the normative serialized contract for Core's accepted neutral
grouping-signal interchange. The architectural decision is
[ADR 0004](decisions/0004-adopt-neutral-grouping-signal-interchange.md).

Version 1 is adopted for Core v0.6.1 implementation. Typed runtime models,
strict structural validation, exact mapping conversion, and canonical JSON
serialization are implemented by issue #180. Human-editable one-dimension CSV
conversion is implemented by issue #181. Immutable exchange storage and
canonical-byte SHA-256 binding are implemented by issue #182. Workspace/roster
diagnostics remain #183, and standalone/release qualification remains #184.

When documentation disagrees, the accepted ADR governs architecture and this
contract governs detailed version-1 wire semantics.

## Purpose

`grouping_signal_set_v1` carries one immutable snapshot of contextual ordinal
student signals for one exact Core class. It is deliberately small enough to
sit between a producer that knows why a signal exists and a consumer that knows
how it may be used for planning.

The intended dependency direction is:

```text
optional producer
      |
      v
     Core
 grouping_signal_set_v1
      |
      v
optional consumer
```

The initial planned integration is:

```text
Meridian -> Core -> Concord
```

but neither Meridian nor Concord is required to author, validate, or inspect a
conforming signal set through Core.

The contract is not an AcademicResult, Grade record, proficiency record,
GroupPlan, Group, or GroupMembership.

## Contract identity

The public contract name is:

```text
grouping_signal_set_v1
```

Version 1 uses Core's established serialized discriminator fields:

```json
{
  "schema_version": "1",
  "record_type": "grouping_signal_set"
}
```

There is no redundant serialized `contract_version` field.

## Exact top-level shape

A version-1 JSON record contains exactly these top-level fields:

```text
schema_version
record_type
signal_set_id
class_id
created_at
source
dimensions
student_bands
```

A representative module-generated record is:

```json
{
  "schema_version": "1",
  "record_type": "grouping_signal_set",
  "signal_set_id": "planning_signal_001",
  "class_id": "english10_p2",
  "created_at": "2026-09-01T18:30:00+00:00",
  "source": {
    "kind": "module_generated",
    "module_id": "meridian",
    "snapshot_id": "meridian_signal_basis_001",
    "snapshot_digest_algorithm": "sha256",
    "snapshot_digest": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  },
  "dimensions": [
    {
      "dimension_id": "reading_analysis",
      "band_count": 4
    },
    {
      "dimension_id": "writing_claim_evidence",
      "band_count": 3
    }
  ],
  "student_bands": [
    {
      "student_id": "student_001",
      "dimension_id": "reading_analysis",
      "band": 2
    },
    {
      "student_id": "student_002",
      "dimension_id": "reading_analysis",
      "band": 4
    },
    {
      "student_id": "student_001",
      "dimension_id": "writing_claim_evidence",
      "band": 3
    }
  ]
}
```

Unknown top-level fields are invalid. Version 1 has no catch-all metadata
object or extension bag.

## `schema_version`

Required string with exact value:

```text
1
```

Consumers must reject unsupported schema versions. They must not reinterpret
another version as version 1.

## `record_type`

Required string with exact value:

```text
grouping_signal_set
```

This distinguishes the record from other Core and module-owned records.

## Signal-set identity

### `signal_set_id`

Required string.

It must satisfy Core's shared path-safe identifier policy: letters, numbers,
underscores, and hyphens only, with no surrounding whitespace.

The durable logical identity of one signal set is:

```text
(class_id, signal_set_id)
```

The identifier:

- identifies the exact immutable snapshot;
- must not be inferred from a title, class label, student name, or path;
- must not be reused for different contents inside the same class; and
- is not a revision number or a pointer to the newest signal.

A materially changed signal uses a new `signal_set_id`.

Version 1 defines no `revision`, `supersedes`, `latest`, `current`, `active`, or
head semantics.

### `class_id`

Required string satisfying Core's shared identifier policy.

It identifies the exact Core class whose student identities the signal may
reference. A display name, course title, teacher name, or period label is not a
substitute for `class_id`.

The signal does not duplicate class metadata such as `school_year`,
`course_name`, `teacher_name`, or `period`. Callers resolve such information
from authoritative Core class/workspace state when needed.

Pure structural validation checks identifier syntax. Workspace-aware
class/roster validation belongs to #183.

## `created_at`

Required timezone-aware ISO-8601 datetime string.

It represents creation/export of this immutable signal snapshot. It is not an
evidence timestamp, Academic Period boundary, or claim that the underlying
academic activity occurred at that moment.

Canonical version-1 serialization must normalize the timestamp to UTC before
emission.

There is no `updated_at`: a signal set is immutable.

## Source and provenance

`source` is required and contains exactly:

```text
kind
module_id
snapshot_id
snapshot_digest_algorithm
snapshot_digest
```

Unknown `source` fields are invalid. The object is intentionally small so a
producer cannot smuggle rich academic state or consumer-specific planning state
through generic metadata.

### `source.kind`

Required string. Version 1 permits exactly:

```text
teacher_authored
module_generated
```

`teacher_authored` means the bands were explicitly authored/imported under
teacher control rather than generated from a PDS module-owned derivation.
Core does not infer why the teacher chose them.

`module_generated` means a PDS module generated the signal from its own state
under its own workflow. The value does not give that module ownership of Core
storage or downstream grouping decisions.

### `source.module_id`

For `module_generated`:

- required non-null string;
- must satisfy Core's identifier policy; and
- must be lowercase.

For `teacher_authored`, it must be JSON `null`.

The contract does not hard-code Meridian as the only possible producer.

### `source.snapshot_id`

An opaque identity for the exact upstream snapshot/artifact from which the
signal was derived.

When non-null it must satisfy Core's shared identifier policy. It identifies
source state, not the signal set itself, and Core must not interpret it as an
AcademicResult, Grade, proficiency value, or Group.

For `module_generated`, it is required and non-null.

For `teacher_authored`, it may be null. A future teacher-authored import may
populate it when an exact source artifact is deliberately bound.

Do not place local absolute paths or identity-bearing filenames here.

### `source.snapshot_digest_algorithm`

Version 1 supports only:

```text
sha256
```

For `module_generated`, it is required and equals `sha256`.

For `teacher_authored` with no bound source snapshot, it must be null.

If a teacher-authored signal binds an exact source artifact, `snapshot_id`,
`snapshot_digest_algorithm`, and `snapshot_digest` must all be populated
together.

### `source.snapshot_digest`

When present, required to be exactly 64 lowercase hexadecimal characters: the
SHA-256 digest of the exact referenced upstream snapshot/artifact.

Malformed, shortened, prefixed, uppercase/mixed-case, or non-hex digests are
invalid.

For `module_generated`, it is required.

For an unbound `teacher_authored` source, it must be null.

### Upstream digest versus signal-record digest

These are two different integrity bindings.

```text
source.snapshot_digest
```

binds an upstream source snapshot/artifact.

The Core exchange storage implemented in #182 separately calculates the
SHA-256 digest of the canonical `grouping_signal_set_v1` JSON bytes. That
signal-record digest is external storage/integrity metadata and is stored in a
strict sibling `.json.sha256` sidecar rather than embedded in the JSON record
being hashed.

## Dimensions

`dimensions` is a required non-empty JSON array.

Every item contains exactly:

```text
dimension_id
band_count
```

Unknown dimension fields are invalid.

### `dimension_id`

Required string satisfying the shared Core identifier policy.

It must be unique within one signal set.

A dimension ID is a stable machine identifier for the producer/teacher's
stated planning context. It is not a Core-owned global ontology. Two separate
signal sets using the same `dimension_id` are not automatically comparable.

Core does not define the academic meaning of a dimension.

Version 1 intentionally carries no free-form dimension description, standards
list, formula, band label, or evidence detail.

### `band_count`

Required integer greater than or equal to `2`.

A JSON boolean is not an integer for this contract.

For a declared `band_count = N`, valid bands are the inclusive range:

```text
1..N
```

Core validates the count but does not select it. There is no default band
count.

## Student bands

`student_bands` is a required non-empty JSON array.

Every item contains exactly:

```text
student_id
dimension_id
band
```

Unknown entry fields are invalid.

### `student_id`

Required string satisfying Core's existing student identifier policy.

It refers to one student identity in the signal's exact `class_id`.
Student names are not serialized and must not be used for identity resolution.

Pure validation checks identifier syntax. Workspace-aware diagnostics in #183
will determine whether a syntactically valid ID exists, belongs to another
class, or conflicts with the target roster.

### Entry `dimension_id`

Required string and must exactly reference one member of `dimensions`.

An entry referencing an undeclared dimension is invalid.

### `band`

Required JSON integer satisfying the declared dimension's range:

```text
1 <= band <= band_count
```

The following are invalid examples:

```text
0
-1
5 when band_count is 4
1.5
"2"
true
false
null
"missing"
"advanced"
"low"
```

### Entry uniqueness

There may be at most one entry for each exact pair:

```text
(student_id, dimension_id)
```

Duplicate pairs are invalid even if their band values agree.

One student may have entries in several different dimensions.

Every declared dimension must be represented by at least one `student_bands`
entry. A dimension with zero entries is invalid and must be omitted from that
snapshot rather than carried as an empty declaration. This rule does not require
complete roster coverage: a represented dimension may still be missing any
number of individual roster students.

## Partial roster coverage and missing signals

A signal set does not need to contain every roster member in every dimension.
Partial coverage can be legitimate because, for example, a student has
insufficient evidence, an evidence window contains no usable evidence, or a
teacher-authored file is intentionally incomplete.

Partial coverage applies within a represented dimension. Because every declared
dimension must have at least one entry, a dimension with no student bands at all
is invalid rather than a valid 100%-missing signal dimension.

Absence of a `(student_id, dimension_id)` entry means only:

> No band is present for that student in that dimension in this exact signal
> set.

Absence must not be interpreted as:

- band `0`;
- lowest band;
- failure;
- absence from school;
- unenrollment;
- no ability;
- no proficiency;
- exclusion from grouping; or
- permission for a consumer to omit the student.

Do not create sentinel entries for missing values.

Issue #183 will report missing roster coverage explicitly. When Concord later uses a
signal-dependent strategy, Concord must require an explicit teacher-facing
decision about students without a selected signal.

## Normative band semantics

A band is a **contextual ordinal planning signal**.

The integers establish order only within the exact signal set and exact
dimension. They do not establish equal numeric distance. For example,
`4 - 3` is not necessarily the same academic difference as `2 - 1`.

The contract does not contain or imply a universal conversion between a band
and:

- Grades or letter grades;
- points or percentages;
- rubric ratings;
- proficiency-category names or values;
- standardized-test scores or percentile ranks;
- ability or intelligence;
- readiness;
- disability or accommodation status;
- language status;
- behavior or motivation; or
- predicted achievement.

A band is not a permanent learner attribute.

Core documentation and APIs must not relabel bands as `high student`, `medium
student`, `low student`, `advanced student`, `weak student`, `ability group`,
`high ability`, or `low ability`.

A producer may derive temporary bands from academic information under explicit
teacher-controlled policy, but that derivation remains producer-owned.

## Multi-dimension semantics

JSON v1 supports one or more dimensions in one immutable signal set.

Each dimension has its own `band_count`. Coverage can differ by dimension, but
every declared dimension must contain at least one student-band entry. Each
`(student_id, dimension_id)` pair is independent.

A consumer must explicitly choose the dimension it intends to use. Bands from
two dimensions must not be compared as if they share a common scale.

A future Concord GroupPlan that consumes one dimension must record the exact
selected `dimension_id` along with the signal-set identity and canonical
digest.

## Canonical ordering

Canonical version-1 representation uses deterministic list ordering.

### `dimensions`

Ascending exact-string order by:

```text
dimension_id
```

### `student_bands`

Ascending exact-string order by:

```text
dimension_id
student_id
```

List order does not encode priority.

Runtime APIs normalize valid in-memory construction into this canonical ordering
after validating all entries and rejecting duplicates. Serialized mapping and
canonical-wire loading are stricter: they reject noncanonical list order rather
than silently repairing it or assigning semantic meaning to insertion order.

Sorting must never be used to silently resolve duplicate or unknown identities.

## Object field order and canonical JSON

Canonical serialization emits object fields in the documented contract order shown
in this document. Dictionaries are constructed in that order; canonical JSON
does not enable `sort_keys`.

The version-1 canonical JSON text is equivalent to:

```python
json.dumps(
    grouping_signal_set_to_dict(value),
    indent=2,
    ensure_ascii=True,
    allow_nan=False,
) + "\n"
```

Canonical bytes are exactly that text encoded as UTF-8. Therefore canonical
version-1 JSON uses two-space indentation, standard ASCII escaping, LF line
endings, no BOM, and exactly one final LF. `NaN`, `Infinity`, and `-Infinity`
are invalid. Object field order does not carry domain meaning even though the
canonical representation emits one required order.

The strict canonical JSON loader rejects duplicate object keys and requires the
supplied text/bytes to equal Core's canonical serialization exactly after model
validation. Semantically equivalent but byte-different JSON is noncanonical,
including reordered object fields, alternate whitespace, CRLF, missing or extra
final newlines, `Z` instead of `+00:00`, or an equivalent non-UTC timestamp.

## Human-editable CSV relationship

Core implements a self-contained human-editable CSV representation identified
by:

```text
grouping_signal_csv_v1
```

CSV is a convenience/interchange representation only. Canonical
`grouping_signal_set_v1` JSON remains authoritative, and the #182 exchange
storage hashes canonical JSON bytes rather than CSV bytes.

### One file, one selected dimension

One CSV file represents exactly one selected dimension. The row table is always:

```csv
student_id,band
student_001,2
student_002,4
```

The file begins with a fixed metadata preamble. A complete single-dimension
teacher-authored signal is represented as:

```text
# csv_contract=grouping_signal_csv_v1
# schema_version=1
# record_type=grouping_signal_set
# representation_scope=complete_signal
# signal_set_id=teacher_plan_001
# class_id=english10_p2
# created_at=2026-09-01T18:00:00+00:00
# source.kind=teacher_authored
# source.module_id=
# source.snapshot_id=
# source.snapshot_digest_algorithm=
# source.snapshot_digest=
# dimension_id=discussion_support
# band_count=3
student_id,band
student_001,1
student_002,3
```

Version 1 recognizes exactly these metadata keys:

```text
csv_contract
schema_version
record_type
representation_scope
signal_set_id
class_id
created_at
source.kind
source.module_id
source.snapshot_id
source.snapshot_digest_algorithm
source.snapshot_digest
dimension_id
band_count
```

Metadata lines use exact `# key=value` syntax. Unknown, duplicate, or missing
metadata keys are invalid. Nullable source fields use an empty value; arbitrary
blank required metadata is not converted to null.

Core export emits metadata in the order shown above, then the exact
`student_id,band` header, then ascending exact-string `student_id` row order.
Export uses comma delimiters, standard CSV quoting, UTF-8 without a BOM, LF line
endings, and exactly one final LF.

CSV import is intentionally more tolerant than canonical JSON. It accepts UTF-8
text/bytes, an initial UTF-8 BOM, LF or CRLF, standard CSV quoting, metadata
reordering after the required first `csv_contract` discriminator line, valid row
reordering, and equivalent timezone-aware ISO-8601 timestamps. Import does not
require the original bytes to match Core's deterministic exporter.

The importer rejects invalid UTF-8, NUL, malformed CSV quoting, unsupported
headers or delimiters, unknown/duplicate/missing metadata, arbitrary comments,
blank data records, missing/extra cells, duplicate student IDs, invalid IDs, and
invalid bands. It does not perform delimiter sniffing or accept header aliases.

### Representation scope

Every file declares exactly one of:

```text
complete_signal
dimension_projection
```

`complete_signal` means the CSV contains the complete serialized signal content
for a signal set that has exactly one declared dimension. It does not claim
complete class-roster coverage; partial roster coverage remains valid.

`dimension_projection` means the CSV contains one explicitly selected dimension
from a source signal set that contains more than one dimension. The CSV retains
the source signal's `signal_set_id`, `class_id`, `created_at`, and source
provenance for preview, but it is not a lossless serialized form of the source
signal.

Export from a one-dimension `GroupingSignalSet` uses `complete_signal`. Export
from a multi-dimension signal requires an explicit `dimension_id` and uses
`dimension_projection`. Core never chooses a dimension implicitly or flattens
multiple dimensions into one row table.

### Identity-preserving complete round trips

An unchanged `complete_signal` CSV may preserve the CSV-declared
`signal_set_id` and `created_at`. A valid one-dimension signal exported to CSV
and immediately imported without edits reconstructs an equal #180 runtime model
and therefore the exact same canonical JSON bytes.

CSV conversion may also be given an explicit replacement `signal_set_id` and
`created_at` together. The replacement ID must differ from the CSV-declared ID.
This supports callers deliberately creating a new immutable signal after an
edit. CSV parsing alone cannot prove whether an unrelated historical signal
already exists under the declared identity; issue #182 will reject attempts to
persist different canonical bytes under an existing `(class_id, signal_set_id)`.

### Projection conversion

A `dimension_projection` cannot become a standalone canonical signal under its
source identity. Standalone conversion requires both:

```text
new_signal_set_id
new_created_at
```

The new ID must differ from the CSV-declared source `signal_set_id`, and the new
time must be explicitly supplied as a timezone-aware datetime. Core does not
invent IDs, suffixes, UUIDs, or timestamps.

The resulting `GroupingSignalSet` contains exactly the selected dimension and
its rows. It carries no supersession/revision relationship and does not copy the
source's omitted dimensions. Source provenance may be preserved when it remains
truthful and valid under the version-1 source rules.

### Integer and identity parsing

CSV `band_count` and `band` are accepted only as unambiguous unsigned base-10
integer text. Values such as `2.0`, `+2`, `-1`, surrounding-whitespace forms,
booleans, or words are invalid. Leading zeros may be parsed and are normalized
on deterministic export.

The row identity is exact Core `student_id`. Version 1 does not accept
`student_name`, `name`, email, display-name, fuzzy lookup, or roster-position
identity. Structurally valid but unknown/wrong-class student IDs remain issue
#183 workspace/roster diagnostics rather than CSV parser failures.

### Typed preview and canonical conversion

CSV parsing returns an immutable typed preview/document containing the declared
scope, source signal identity/time, class, source provenance, selected dimension,
band count, and every parsed `student_id`/band row. Callers may inspect that
preview before canonical conversion, including whether a new identity is
required.

Successful conversion always produces the public #180 `GroupingSignalSet`.
The CSV layer does not define an alternate JSON record or serializer; callers
use #180 canonical JSON helpers after conversion.

Grouping-signal CSV remains teacher-restricted educational data. Extra columns
or metadata attempting to carry names, raw academic values, free-form notes,
Groups, GroupMemberships, GroupPlans, planning strategies, or other extension
state are rejected rather than preserved.

## Immutability and history

A grouping signal is a snapshot and has no update operation.

A material change creates a new signal set, including changes to:

- academic evidence;
- interpretation policy;
- source snapshot;
- band boundaries;
- band count;
- dimension choice;
- roster inclusion/coverage;
- manual band assignment; or
- a corrected import.

The earlier record remains historical.

Version 1 has no automatic current or latest selection.

## Core exchange storage

Issue #182 implements immutable neutral exchange storage at:

```text
exchange/grouping-signals/<class_id>/<signal_set_id>.json
exchange/grouping-signals/<class_id>/<signal_set_id>.json.sha256
```

The `.json` file contains exactly the canonical version-1 UTF-8 JSON bytes
emitted by the #180 serializer. Storage does not independently reserialize a
signal and never persists CSV as the canonical exchange record.

### Canonical-byte digest binding

Core calculates:

```text
SHA256(exact canonical grouping_signal_set_v1 JSON bytes)
```

and returns the lowercase 64-character hexadecimal digest. This digest is
separate from `source.snapshot_digest`: the source digest binds the upstream
producer/teacher source artifact, while the storage digest binds the exact Core
signal snapshot.

The signal-record digest is not embedded in the JSON being hashed. It is stored
in the sibling `.json.sha256` sidecar as exactly:

```text
<64 lowercase hexadecimal characters>\n
```

with no algorithm prefix, filename, BOM, spaces, CRLF, or additional newline.
The algorithm is fixed to `sha256` for this storage contract.

### Immutable creation and replay

The durable identity remains:

```text
(class_id, signal_set_id)
```

Final JSON and digest-sidecar paths are create-only. Core never replaces either
member of an existing canonical pair.

For a write request:

- absent identity + successful verified creation returns `created`;
- an already-valid pair with exactly the same canonical JSON bytes returns
  `existing` without rewriting either file; and
- an already-valid pair under the same identity with different canonical bytes
  raises an immutable-identity conflict.

A retry therefore provides idempotency without mutation. A changed band,
`created_at`, provenance value, dimension declaration, coverage set, or other
canonical value requires a new `signal_set_id`.

If only one member of the JSON/sidecar pair already exists, Core treats storage
as incomplete/corrupt and fails closed. Ordinary writes do not repair or delete
pre-existing incomplete pairs. A failed write may clean up only artifacts that
the same call can identify as its own newly created files.

### Strict loading and integrity verification

Loading one exact identity requires both canonical files. Core:

1. validates the requested `class_id` and `signal_set_id`;
2. reads the raw JSON bytes and strict digest sidecar;
3. calculates SHA-256 over the raw JSON bytes present on disk;
4. verifies that value against the sidecar;
5. loads the raw JSON through the strict #180 canonical JSON loader; and
6. requires the embedded `class_id` and `signal_set_id` to match the canonical
   directory/filename identity.

Core does not normalize or rewrite noncanonical persisted JSON. A semantically
valid but byte-noncanonical JSON file remains invalid storage even if its
sidecar was recalculated to match those altered bytes.

If neither member of an explicitly requested pair exists, the exact signal is
not found. If exactly one exists, the state is an integrity failure rather than
a normal not-found result.

### Class-scoped listing

Core can list validated `signal_set_id` values for one exact class. Listing is
bounded to:

```text
exchange/grouping-signals/<class_id>/
```

and returns IDs in ascending exact-string order after verifying complete valid
pairs. It does not recursively crawl the workspace or rank records by creation
time, producer, filesystem modification time, or any academic property.

A consumer still chooses an exact signal identity deliberately.

### No automatic selection or mutation

Version 1 creates no alias or pointer such as:

```text
latest.json
current.json
active.json
head.json
```

and exposes no `load_latest`, `load_current`, update, replace, revision,
supersession, or in-place editing semantics. Filesystem ordering and timestamps
must not be interpreted as implicit selection policy.

Where reproducibility matters, a downstream record such as a Concord GroupPlan
should retain:

- the exact `class_id` and `signal_set_id`;
- the canonical signal-set SHA-256 digest returned by Core; and
- the exact selected `dimension_id`.

It must not copy source band values into GroupMembership.

### Filesystem and threat boundary

Core derives storage paths only from the normalized workspace root and validated
Core identifiers. Existing storage-parent symlinks/redirections outside the
workspace, final-file symlinks, directories occupying final file paths, malformed
visible entries, incomplete pairs, and digest/path mismatches fail safely.

The SHA-256 sidecar detects accidental mutation, incomplete writes, corruption,
and stale/mismatched bytes. It is not a signature or secret-backed authenticity
mechanism: an actor with unrestricted local filesystem write access could
replace both the JSON and its digest sidecar. Version 1 does not claim protection
against that threat model.

Workspace-aware class and roster validation remains issue #183. Structurally
valid signals can be stored without Meridian, Concord, a roster lookup, or
producer-runtime discovery.

## Privacy classification

Treat every populated grouping signal as **teacher-restricted educational
data**.

Although the contract excludes raw academic values, it contains class
identity, student IDs, relative educational planning signals, and provenance.

Grouping-signal values must not be reproduced by default in:

- application logs;
- diagnostic event payloads;
- troubleshooting bundles;
- crash reports;
- passive suite attention summaries;
- PDS2 QR payloads;
- route registrations;
- packet metadata;
- Artifact metadata;
- AcademicResult manifests;
- Publication Records;
- public examples using real identities; or
- screenshots intended for public documentation.

A teacher-facing workflow may display signal information when the teacher is
explicitly working with the selected signal. Passive diagnostics must not
reproduce it.

Repository fixtures, examples, screenshots, and tests must use synthetic
identities only.

## Data prohibited from version 1

The strict field set prevents the following data from being embedded in the
signal contract.

### Raw or derived academic values

Do not include:

- raw points or points possible;
- percentages;
- letter or conventional Grades;
- rubric or criterion scores;
- question-level scores;
- raw standards ratings;
- proficiency-category names or numeric values;
- standardized-test scores or percentile ranks;
- assignment attempts;
- evidence excerpts;
- student writing or answer content.

### Permanent or stigmatizing learner classifications

Do not include:

- ability labels;
- gifted/not-gifted labels;
- disability, IEP, 504, or accommodation status;
- language-learner status;
- behavior or discipline classifications;
- attendance classifications;
- demographic attributes;
- race or ethnicity;
- sex or gender; or
- socioeconomic status.

### Concord planning/output state

Do not include:

- Group IDs or names;
- GroupMembership records;
- GroupPlan IDs;
- proposed or final groups;
- keep-together/keep-apart constraints;
- role assignments;
- planning strategy;
- random seed;
- group size/count; or
- Scores or Group Scores.

### Unnecessary identity/display data

Do not include:

- student names;
- teacher names;
- email addresses;
- local absolute paths;
- filenames that disclose student identity;
- class display labels when `class_id` is sufficient;
- free-form notes, comments, or rationales.

## Ownership matrix

| Responsibility | Owner |
| --- | --- |
| wire contract and schema semantics | Core |
| identifier/structural validation | Core |
| canonical JSON serialization | Core (#180) |
| CSV conversion | Core (#181) |
| immutable exchange persistence and signal-byte digest | Core (#182) |
| class/roster diagnostics | Core (#183) |
| academic evidence and eligibility | Meridian/teacher |
| proficiency and academic derivation | Meridian |
| band count/boundary/tie policy for academic derivation | Meridian/teacher |
| rich derivation and explanations | Meridian |
| export authorization | teacher through producing workflow |
| manual signal authoring | teacher through Core-supported interchange |
| signal selection for group planning | teacher/Concord |
| planning strategy and GroupPlan lifecycle | Concord |
| teacher preview/approval of proposed groups | Concord/teacher |
| canonical Groups and GroupMemberships | Concord |
| grouping policy in the suite shell | prohibited |

## Valid synthetic examples

### Single-dimension teacher-authored signal

```json
{
  "schema_version": "1",
  "record_type": "grouping_signal_set",
  "signal_set_id": "teacher_plan_001",
  "class_id": "english10_p2",
  "created_at": "2026-09-01T18:00:00+00:00",
  "source": {
    "kind": "teacher_authored",
    "module_id": null,
    "snapshot_id": null,
    "snapshot_digest_algorithm": null,
    "snapshot_digest": null
  },
  "dimensions": [
    {"dimension_id": "discussion_support", "band_count": 3}
  ],
  "student_bands": [
    {"student_id": "student_001", "dimension_id": "discussion_support", "band": 1},
    {"student_id": "student_002", "dimension_id": "discussion_support", "band": 3}
  ]
}
```

### Single-dimension module-generated signal

```json
{
  "schema_version": "1",
  "record_type": "grouping_signal_set",
  "signal_set_id": "reading_plan_001",
  "class_id": "english10_p2",
  "created_at": "2026-09-01T18:30:00+00:00",
  "source": {
    "kind": "module_generated",
    "module_id": "meridian",
    "snapshot_id": "proficiency_snapshot_008",
    "snapshot_digest_algorithm": "sha256",
    "snapshot_digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "dimensions": [
    {"dimension_id": "reading_analysis", "band_count": 4}
  ],
  "student_bands": [
    {"student_id": "student_001", "dimension_id": "reading_analysis", "band": 2},
    {"student_id": "student_002", "dimension_id": "reading_analysis", "band": 4}
  ]
}
```

### Multi-dimension signal

```json
{
  "schema_version": "1",
  "record_type": "grouping_signal_set",
  "signal_set_id": "multi_plan_001",
  "class_id": "english10_p2",
  "created_at": "2026-09-01T19:00:00+00:00",
  "source": {
    "kind": "module_generated",
    "module_id": "meridian",
    "snapshot_id": "academic_snapshot_012",
    "snapshot_digest_algorithm": "sha256",
    "snapshot_digest": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  },
  "dimensions": [
    {"dimension_id": "reading_analysis", "band_count": 4},
    {"dimension_id": "writing_claim_evidence", "band_count": 3}
  ],
  "student_bands": [
    {"student_id": "student_001", "dimension_id": "reading_analysis", "band": 2},
    {"student_id": "student_002", "dimension_id": "reading_analysis", "band": 4},
    {"student_id": "student_001", "dimension_id": "writing_claim_evidence", "band": 3},
    {"student_id": "student_002", "dimension_id": "writing_claim_evidence", "band": 1}
  ]
}
```

### Partial coverage

Here `student_002` has no `writing_claim_evidence` entry. That is valid
structurally and means only that no band is present for that exact pair.

```json
{
  "schema_version": "1",
  "record_type": "grouping_signal_set",
  "signal_set_id": "partial_plan_001",
  "class_id": "english10_p2",
  "created_at": "2026-09-01T19:30:00+00:00",
  "source": {
    "kind": "teacher_authored",
    "module_id": null,
    "snapshot_id": null,
    "snapshot_digest_algorithm": null,
    "snapshot_digest": null
  },
  "dimensions": [
    {"dimension_id": "reading_analysis", "band_count": 4},
    {"dimension_id": "writing_claim_evidence", "band_count": 3}
  ],
  "student_bands": [
    {"student_id": "student_001", "dimension_id": "reading_analysis", "band": 2},
    {"student_id": "student_002", "dimension_id": "reading_analysis", "band": 4},
    {"student_id": "student_001", "dimension_id": "writing_claim_evidence", "band": 3}
  ]
}
```

## Representative invalid cases

The following are contract failures and must map to explicit validation in
Issue #180 unless identified below as workspace-aware #183 diagnostics.

| Case | Why invalid |
| --- | --- |
| unsupported `schema_version` | v1 consumers do not reinterpret other versions |
| wrong `record_type` | exact record discriminator required |
| blank/unsafe `signal_set_id` | shared identifier policy required |
| blank/unsafe `class_id` | shared identifier policy required |
| naive `created_at` | timezone-aware timestamp required |
| unknown `source.kind` | exact v1 source kinds only |
| `teacher_authored` with non-null `module_id` | teacher source is not attributed to a module |
| `module_generated` without `module_id` | producing module identity required |
| uppercase module ID | module IDs are lowercase Core identifiers |
| `module_generated` without snapshot ID/digest | exact upstream provenance required |
| partial teacher source-provenance triple | snapshot ID/algorithm/digest are all-null or all-present |
| malformed SHA-256 | exact lowercase 64-hex digest required |
| empty `dimensions` | at least one dimension required |
| duplicate `dimension_id` | dimension identity must be unique |
| declared dimension with zero student-band entries | every declared dimension must represent at least one signal |
| invalid dimension identifier | shared identifier policy required |
| `band_count < 2` | v1 requires at least two ordinal bands |
| boolean `band_count` | bool is not an integer for this contract |
| empty `student_bands` | a signal set must contain at least one signal entry |
| undeclared entry `dimension_id` | every entry references a declared dimension |
| duplicate `(student_id, dimension_id)` | exact pair must be unique |
| invalid `student_id` | shared student identifier policy required |
| band `0` or negative | outside `1..N` |
| band greater than `band_count` | outside declared range |
| float/string/bool/null band | band must be an integer |
| noncanonical canonical-wire list order | canonical bytes require deterministic ordering |
| student name used instead of `student_id` | names are not contract identity |
| `score`, `percentage`, `grade`, or `proficiency` field | prohibited academic data/unknown field |
| `group_id`, `group_membership`, or plan field | prohibited Concord output/unknown field |
| arbitrary metadata or free-text extension | v1 is an exact strict contract |
| re-imported reduced CSV projection reusing its multi-dimension source `signal_set_id` | immutable identity cannot name different contents |

The following are **workspace-aware diagnostic failures** rather than reasons
to make pure #180 model validation load a roster:

- syntactically valid but unknown student;
- a student ID known to a different class but not the target class;
- selected class/workspace context not matching the record's `class_id`; and
- roster members missing from one or more dimensions.

Issue #183 owns those diagnostics. Core must report them without silently dropping,
remapping, or filling entries.

## Versioning rules

Version 1 is strict:

- unknown fields are rejected;
- unsupported schema versions are rejected;
- improving diagnostics does not change v1 semantics;
- adding an optional serialized field is not automatically backward-compatible
  because v1 uses exact field sets;
- any field addition requires an explicit compatibility decision;
- changing identity, band, source/provenance, required-field, or missing-value
  semantics requires a later contract version; and
- existing v1 records retain their original meaning permanently.

Permissive parsing is not a substitute for versioning.

## Relationship to existing Core contracts

`grouping_signal_set_v1` is additive. It does not change the schema or meaning
of:

- PDS2 payloads;
- RouteRegistration;
- retained-source records;
- rosters or class metadata;
- Academic Periods;
- Academic Work Registration;
- Publication Records;
- producer manifests;
- module profiles; or
- publication producer profiles.

Existing consumers declaring `pds-core>=0.6,<0.7` that do not use grouping
signals require no migration merely because this contract exists.

Concord v0.3 is expected to require `pds-core>=0.6.1,<0.7` because it actively
consumes this new contract.

## Implementation follow-up

This document freezes the semantics consumed by the Core v0.6.1 implementation
sequence:

```text
Issue #180 typed models + validation + canonical JSON — implemented
Issue #181 one-dimension CSV conversion — implemented
Issue #182 immutable exchange storage + signal-byte digest — implemented
Issue #183 class/roster diagnostics
Issue #184 standalone acceptance + release audit
```

If implementation reveals that a rule here is impossible or contradictory,
do not silently change runtime wire semantics. Amend the architectural decision
and contract explicitly before implementation diverges.

Repository-local acceptance must preserve sibling independence:

```text
Core      tests without Meridian or Concord
Meridian  tests signal generation/export without Concord
Concord   tests signal planning with synthetic Core-conformant input without Meridian
```

A later suite qualification may prove `Meridian -> Core -> Concord` without
creating a direct runtime dependency between those modules.

## References

- [ADR 0004](decisions/0004-adopt-neutral-grouping-signal-interchange.md)
- `Paper-Data-Suite/pds-core#177`
- `Paper-Data-Suite/pds-core#179`
- `Paper-Data-Suite/pds-concord#47`
- `Paper-Data-Suite/pds-paper-data-suite/development-plan.md`

The implementation baseline audited for this contract was `pds-core` main
commit `6c507213618b68a6dd3ea096e1a898201ff029e6`.
