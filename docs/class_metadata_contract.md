# Class Metadata Contract

Paper Data Suite stores class-level metadata beside each shared roster. The
metadata record describes the class as a whole; student rows remain in
`roster.csv`.

## Path

The canonical metadata path is:

```text
classes/<class_id>/class.json
```

Use `pds_core.routes.class_metadata_path(root, class_id)` or
`pds_core.class_metadata.class_metadata_path(root, class_id)` to resolve this
path. The `class_id` is validated with the same shared identifier policy used
by roster and assignment routes.

## JSON Shape

Version 1 class metadata uses this strict object shape:

```json
{
  "schema_version": "1",
  "record_type": "class",
  "class_id": "english10_p2",
  "school_year": "2026-2027",
  "created_at": "2026-07-09T13:00:00-04:00",
  "updated_at": "2026-07-09T13:00:00-04:00",
  "module_details": {}
}
```

Unknown top-level fields are rejected. `module_details` is reserved for
compatible future extension and must be a JSON object.

## Field Rules

`schema_version` is required and must be `"1"`.

`record_type` is required and must be `"class"`.

`class_id` is required, must pass the shared pds-core identifier policy, and
must match the containing class folder when loaded through canonical class
helpers.

`school_year` is required for newly created metadata and must use consecutive
`YYYY-YYYY` format, such as `2026-2027`. The shared public validator is
`pds_core.school_years.validate_school_year(value)`.

`created_at` and `updated_at` are required timezone-aware ISO datetime strings.
`updated_at` must not be earlier than `created_at`.

## Relationship To Rosters

Do not add `school_year` to `roster.csv`. The roster remains shared row data
with the existing required columns:

```text
class_id
student_id
last_name
first_name
period
```

Existing class folders and rosters without `class.json` remain valid. Metadata
is required only when a caller explicitly asks for it through metadata-aware
helpers such as `list_class_folders(..., require_metadata=True)`.

## Ownership

pds-core owns the class metadata schema, validation, route, and load/write
helpers. Quillan, ScoreForm, and future modules should consume these helpers
instead of defining module-specific class metadata formats. Modules decide when
to prompt for or display a school year; pds-core does not write metadata as a
side effect of roster loading or roster writing.
