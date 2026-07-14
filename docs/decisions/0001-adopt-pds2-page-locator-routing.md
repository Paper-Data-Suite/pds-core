# ADR 0001: Adopt PDS2 Page-Locator Routing

**Status:** Accepted; implemented in `pds-core` v0.5.0
**Date:** July 14, 2026
**Decision owners:** Paper Data Suite maintainers
**Applies to:** `pds-core` and all Paper Data Suite modules that generate or route returned paper pages
**Related issue:** `Paper-Data-Suite/pds-core#136`
**Umbrella issue:** `Paper-Data-Suite/pds-core#135`

**Implementation note:** Core issues #137 through #141 completed the routing
models, PDS2 parser/serializer, module-qualified workspace and registrations,
module profiles and dispatch, and generalized failure/resolution metadata.
Version 0.5.0 completes the Core documentation and packaging work. The
coordinated ScoreForm, Quillan, and Concord migrations remain downstream work.

## Context

Paper Data Suite requires one shared QR and routing contract that can support ScoreForm, Quillan, Concord, and future paper-processing modules.

The current shared contract is `PDS1`:

```text
PDS1|module=<module>|class=<class_id>|aid=<assignment_id>|sid=<student_id>|page=<page_number>
```

The current normalized payload requires:

```text
schema
module
class_id
assignment_id
student_id
page
metadata
```

The current shared route model is based on:

```text
classes/<class_id>/assignments/<assignment_id>/
```

and treats a student submission directory as the normal universal destination:

```text
classes/<class_id>/assignments/<assignment_id>/submissions/<student_id>/
```

This model was created around the initial ScoreForm and Quillan workflows. It assumes that every routed paper page:

* belongs to one student;
* belongs to one unqualified assignment;
* carries its student identity in the QR;
* carries its logical page number in the QR;
* may carry arbitrary module metadata in the QR;
* and can be routed through a student-submission-oriented path.

Those assumptions cannot serve as the long-term Paper Data Suite routing architecture.

Concord requires valid pages that may concern:

* no student;
* one student;
* several students;
* one Group;
* several Groups;
* one Session;
* one Activity;
* one Activity Event;
* one Artifact Instance;
* one Artifact Page;
* a teacher-authored multi-subject tracker;
* or unresolved Authors or Subjects.

A page may be completed by one person while concerning another person, a Group, a Session, an Activity, or several contextual entities. The person who physically writes on a page is not necessarily its Subject, scorer, Score target, or route owner.

Future Paper Data Suite modules may introduce additional valid non-student targets.

Making `student_id` optional would not solve this problem. It would preserve student identity as the privileged route concept while treating all other cases as exceptions.

Likewise, adding more optional fields to PDS1 would increase QR density, duplicate mutable semantic records, and produce incompatible module-specific interpretations of the shared payload.

Paper Data Suite is not currently in active classroom use. No teacher depends on existing PDS1 or OMR1 pages, data, or parsing behavior. Backward compatibility is therefore not a requirement for this redesign.

PDS1 and OMR1 will no longer be supported for either generation or parsing.

## Decision

Paper Data Suite will replace PDS1 and OMR1 with a new shared page-locator contract named `PDS2`.

The foundational rule is:

> A Paper Data Suite QR code identifies one expected physical page route. It does not identify the page’s Author, Subject, scorer, Score target, student submission, or final evidence destination.

The shared routing relationship is:

```text
physical page
    -> PDS2 QR
    -> Core RouteLocator
    -> persisted Core RouteRegistration
    -> typed module-owned page target
    -> module-owned semantic records
    -> module-owned evidence or processing workflow
```

It is not:

```text
QR
    -> student
    -> universal student submission directory
```

### PDS2 schema identifier

The new QR schema identifier is:

```text
PDS2
```

PDS1 will not be redefined in place because PDS1 and PDS2 have materially different meanings.

PDS1 means conceptually:

```text
module + class + assignment + student + logical page number
```

PDS2 means conceptually:

```text
module + class + module work context + durable expected-page route
```

Using a new schema identifier makes the breaking semantic change explicit.

### Canonical PDS2 envelope

The canonical PDS2 payload is:

```text
PDS2|m=<module_id>|c=<class_id>|w=<work_id>|r=<route_id>
```

The payload contains exactly four fields:

| QR key | Internal field | Meaning                              |
| ------ | -------------- | ------------------------------------ |
| `m`    | `module_id`    | Owning Paper Data Suite module       |
| `c`    | `class_id`     | Core class identifier                |
| `w`    | `work_id`      | Module-owned top-level work context  |
| `r`    | `route_id`     | Durable expected-page route identity |

All four fields are required.

Parsing is field-order independent.

Canonical serialization uses this order:

```text
PDS2|m=...|c=...|w=...|r=...
```

The shared grammar does not permit arbitrary extension fields.

A PDS2 parser must reject:

* missing fields;
* duplicate fields;
* unknown fields;
* empty keys;
* empty values;
* empty segments;
* malformed segments;
* unsafe identifiers;
* unsupported schema identifiers;
* and payloads exceeding the configured absolute size limit.

### Data excluded from PDS2

The common QR envelope does not contain:

* `student_id`;
* student name;
* Author identity;
* Subject identity;
* Group identity;
* Session identity;
* logical page number;
* total page count;
* document type;
* template identifier;
* form identifier;
* attempt number;
* revision state;
* assignment title;
* scoring Criterion;
* Score target;
* marking period;
* assessment classification;
* destination path;
* or arbitrary module metadata.

These values belong in:

* the persisted route registration when appropriate for shared routing;
* the authoritative module-owned page record;
* or other module-owned semantic records.

The QR remains small, stable, inspectable, and independent of mutable workflow details.

### Page-locator semantics

Every physical page expected to return through scanning receives one durable route identity before the page is rendered.

A multi-page document therefore receives:

* one module-owned page record per expected returned physical page;
* one distinct route ID per page;
* one persisted route registration per page;
* and one PDS2 QR per page.

PDS2 identifies an expected physical page route rather than a whole document, student submission, assignment, or Artifact.

Logical page number and page-order information remain module-owned data.

For example, a Quillan response-page record may contain:

* logical page number;
* continuation-page relationship;
* total expected page count;
* submission relationship;
* and template version.

Those values are resolved after routing and do not appear in the QR.

### Module-qualified work identity

Core will use a neutral module work reference:

```text
ModuleWorkRef
├── module_id
├── class_id
└── work_id
```

The effective identity of one module work unit is:

```text
module_id + class_id + work_id
```

A bare `work_id` is not globally meaningful.

Initial mappings are:

| Module        | Meaning of `work_id`                                |
| ------------- | --------------------------------------------------- |
| ScoreForm     | `assignment_id`                                     |
| Quillan       | `assignment_id`                                     |
| Concord       | `activity_id`                                       |
| Future module | Its durable top-level routable work-unit identifier |

`work_id` is a routing and storage term.

It does not assert that every work unit is:

* a graded assignment;
* an assessment;
* owned by one student;
* or directly reportable to a future gradebook.

The following work units may coexist in the same class without collision:

```text
scoreform / english10_p3 / project_check
quillan   / english10_p3 / project_check
concord   / english10_p3 / project_check
```

### Route identity

Every expected returned physical page receives a `route_id`.

A route ID must be:

* non-empty;
* collision-resistant;
* path-safe;
* QR-safe;
* non-semantic;
* immutable after printing;
* unique within its `ModuleWorkRef`;
* and never reused for another target.

The complete route identity is:

```text
module_id + class_id + work_id + route_id
```

Core should generate route IDs that are practically globally collision-resistant, even though uniqueness is formally required within the containing `ModuleWorkRef`.

A route ID must not encode:

* student identity;
* Group identity;
* person names;
* logical page number;
* target record type;
* marking period;
* grading category;
* or mutable lifecycle status.

A diagnostic prefix such as `rt_` may be used, but the route’s meaning must not depend on the prefix.

### Route registration

A QR is not a complete route record.

Before rendering a returned page, the owning module must persist a `RouteRegistration` connecting the PDS2 locator to one typed module-owned page target.

Conceptually:

```text
RouteRegistration
├── registration schema version
├── RouteLocator
├── ModuleRecordRef target
├── creation timestamp
├── lifecycle status
├── human-readable fallback
└── optional module details
```

The route registration must exist before the page’s QR is rendered.

Page generation must fail rather than produce a PDS2 locator that does not already have a persisted registration.

The route registration is the authoritative connection between:

```text
RouteLocator
    -> module-owned page target
```

A QR alone must not cause Core or a module to:

* create a missing target;
* create a missing registration;
* infer a student;
* infer an Author or Subject;
* select a Score target;
* or invent an evidence destination.

### Typed module-owned target

The registration target uses a generic typed module-record reference:

```text
ModuleRecordRef
├── module_id
├── record_kind
├── record_id
└── optional contract_version
```

Representative page targets include:

```text
scoreform / answer_sheet_page / <record_id>
quillan   / response_page     / <record_id>
concord   / artifact_page     / <record_id>
```

The target must belong to the same module as the locator.

A locator with:

```text
module_id = concord
```

must resolve first to a Concord-owned target.

It must not directly target a ScoreForm or Quillan record.

The Concord-owned target may later contain references to records from other modules, but those references do not alter the ownership of the route itself.

Core validates the generic target-reference structure.

The owning module validates:

* target existence;
* target type;
* target lifecycle;
* expected page state;
* and the target’s complete semantic meaning.

Core does not interpret module-specific `record_kind` values.

### Separation of identities

The following concepts remain distinct:

```text
RouteLocator
ModuleWorkRef
ModuleRecordRef
student relationship
Artifact Author
Artifact Subject
student submission
evidence reference
Score target
```

They may refer to related records, but none is inferred universally from another.

In particular:

* `route_id` is not `student_id`;
* `route_id` is not a logical page number;
* a route target is not automatically an Author;
* a route target is not automatically a Subject;
* a Subject is not automatically a Score target;
* and a module work unit is not automatically a graded assignment.

A module may generate a route ID and page-record ID using related mechanisms, but the concepts remain separate.

The persisted route registration, not string equality, defines the relationship between a route and its target.

### Registration immutability and route history

After a page has been rendered or printed:

* its PDS2 locator must not change;
* its route ID must not be reused;
* and its registration must not be silently repointed to another target.

A route may later enter a non-active lifecycle state, such as:

* inactive;
* retired;
* superseded;
* cancelled;
* invalidated;
* or another explicitly defined state.

The precise lifecycle enumeration will be defined during implementation.

Regardless of the final vocabulary:

* historical registrations must be preserved;
* state changes must not erase the original locator-target relationship;
* old scanned pages must remain explainable;
* and corrections must use explicit lifecycle, supersession, or resolution records.

A route never silently changes meaning.

### Deterministic local-first lookup

PDS2 must support deterministic route-registration lookup without a global database and without recursively searching the workspace.

The module-qualified work root is:

```text
classes/<class_id>/modules/<module_id>/work/<work_id>/
```

The conceptual registration location is:

```text
classes/
  <class_id>/
    modules/
      <module_id>/
        work/
          <work_id>/
            routes/
              <route_id>.json
```

The four PDS2 locator fields are sufficient to calculate the registration location.

Core’s public path API must insulate modules from later internal changes such as route-directory sharding.

Modules must use Core path and persistence helpers rather than manually constructing shared registration paths.

### Exact locator matching

Finding a registration file at the calculated path is not sufficient for successful routing.

The loaded registration must match every locator component:

* QR schema;
* module ID;
* class ID;
* work ID;
* and route ID.

A mismatch is a route-integrity failure.

Core must not trust a registration solely because it exists at the expected path.

### Core and module ownership

Core owns:

* PDS2 grammar;
* shared identifier validation;
* module-qualified work identity;
* route-locator structure;
* route-registration structure;
* typed module-record reference structure;
* shared route-ID generation;
* deterministic registration paths;
* shared registration validation;
* module-profile integration contracts;
* source-scan identity and provenance;
* and generic routing-failure and resolution contracts.

The owning module owns:

* the meaning of its work unit;
* creation of module-owned page records;
* target existence and lifecycle;
* assignment, Activity, or equivalent semantics;
* student relationships;
* Group relationships;
* Authors and Subjects;
* document completeness;
* evidence filing;
* Review;
* scoring;
* feedback;
* reporting;
* and module-specific failure details.

Core may transport a typed reference to a module-owned record without understanding that record’s domain semantics.

### Source-scan retention and provenance

PDS2 changes route identity but does not weaken the existing active source-scan contract.

Paper Data Suite must continue to:

* retain a readable source before module-specific processing;
* leave the teacher’s external source untouched;
* retain every intake event independently;
* preserve source hashes;
* prevent silent source overwrite;
* keep retained sources separate from routed derivatives;
* and preserve provenance from every routed source page to its retained source.

The generalized relationship is:

```text
retained source scan
    -> source page
    -> PDS2 RouteLocator
    -> RouteRegistration
    -> module-owned page target
    -> module-owned evidence or reference
```

One retained source scan may contain pages for:

* ScoreForm;
* Quillan;
* Concord;
* and future modules.

Each source page receives its own route result, failure, resolution, or module evidence relationship while retaining the same source-scan identity.

Correcting routing, student attribution, Author, Subject, page relationships, or module filing must not modify the retained source bytes.

### Locator rather than authorization

A valid PDS2 payload proves only that the payload is syntactically valid.

It does not prove that:

* the physical page is authentic;
* a registration exists;
* the registration is active;
* the target exists;
* the target is valid;
* the expected person completed the page;
* Authors or Subjects are correct;
* evidence should be created;
* or the page may be scored.

Successful processing requires:

1. strict PDS2 parsing and validation;
2. resolution of a supported module profile;
3. loading a persisted route registration;
4. exact locator consistency;
5. validation of registration lifecycle;
6. validation of the module-owned target;
7. and the owning module’s normal Review or processing rules.

A checksum or cryptographic signature is not required for the initial PDS2 contract.

QR error correction handles ordinary physical scan corruption. Persisted registrations and exact-match validation provide the initial semantic-integrity boundary.

A later signed QR schema may be introduced through a separate architectural decision if a concrete threat model requires one.

### Human-readable fallback

Every generated PDS2 page must display a human-readable route fallback near its QR code.

For example:

```text
PDS2 · concord · english10_p3 · socratic_seminar_1 · rt_01j2m8h8x5z2
```

The fallback must:

* preserve enough information for deterministic manual route recovery;
* match the actual PDS2 locator;
* avoid student names;
* and avoid unnecessary personal information.

Modules may control the visual format, but the fallback must remain lossless.

### Identifier rules

All four PDS2 values use Core’s safe ASCII identifier character set:

```text
letters, numbers, underscores, and hyphens
```

The existing shared validation pattern remains conceptually:

```text
^[A-Za-z0-9_-]+$
```

`module_id` values should be lowercase by convention.

Identifiers must not contain:

* spaces;
* path separators;
* `..`;
* absolute paths;
* pipe characters;
* equals signs;
* URLs;
* shell syntax;
* or leading or trailing whitespace.

Field-specific maximum lengths may be introduced during implementation while preserving these shared safety requirements.

### Payload-size policy

The absolute serialized PDS2 payload limit is:

```text
256 ASCII bytes
```

Generators should target no more than:

```text
160 ASCII bytes
```

under normal operation.

All PDS2 values use safe ASCII characters, so byte length is deterministic.

The absolute limit protects scanners, QR density, parser behavior, and resource use.

The recommended target encourages readable, reliably printable QR codes.

### Independent contract versioning

The following versions are distinct:

* PDS2 QR schema version;
* route-registration schema version;
* Core package version;
* module-record contract version.

The first PDS2 route-registration JSON schema may use:

```text
schema_version = 1
```

The registration schema version is independent of the `PDS2` QR prefix.

Changing a route-registration record without changing the printed locator grammar does not automatically require PDS3.

Changing a module-owned page-record contract does not automatically require changing PDS2.

A new QR schema identifier is required only when the shared printed locator grammar or its semantics change materially.

### PDS1 and OMR1 disposition

PDS1 and OMR1 support will be removed.

Paper Data Suite will no longer:

* generate PDS1 payloads;
* parse PDS1 payloads;
* normalize PDS1 payloads;
* generate OMR1 payloads;
* parse OMR1 payloads;
* normalize OMR1 payloads;
* provide legacy adapters for either format;
* or guarantee compatibility with previously generated pages or data.

Existing PDS1 and OMR1 implementation code and tests will be deleted as part of the coordinated migration.

Historical design documents may remain in Git history or may be retained with an explicit supersession notice, but they do not describe supported runtime behavior.

A PDS1 or OMR1 QR encountered after this migration is an unsupported-schema failure.

The absence of backward compatibility is intentional because Paper Data Suite is not currently in active classroom use and no production workflow depends on the previous formats.

## Consequences

### Positive consequences

* Paper Data Suite gains one shared routing model for student and non-student pages.
* ScoreForm, Quillan, Concord, and future modules can use the same compact QR grammar.
* Student identity is no longer exposed unnecessarily in QR payloads.
* Page locators remain stable when student, Author, Subject, template, or scoring context changes.
* Arbitrary module metadata cannot accumulate in the shared QR envelope.
* QR size and print density are reduced.
* Every expected returned physical page has durable identity.
* Multi-page and continuation-page workflows receive explicit page-level routes.
* Module work units cannot collide merely because they share one `work_id`.
* Route lookup remains deterministic and local-first.
* Route history can be preserved without modifying printed pages.
* Mixed-module source scans can be routed page by page.
* Core remains independent of sibling-module domain models.
* Concord can route pages with no student Subject.
* Teacher-authored multi-subject records can remain one source Artifact rather than being duplicated into fabricated student routes.
* A future suite assignment registry can index `ModuleWorkRef` without changing the QR contract.
* PDS1 and OMR1 complexity is removed rather than carried indefinitely.

### Negative consequences

* PDS2 is a breaking contract.
* Existing PDS1 and OMR1 code and tests must be removed.
* ScoreForm and Quillan must be migrated before they can generate or route paper pages under the new contract.
* Every expected returned physical page requires a durable module-owned page record.
* Every expected returned physical page requires a persisted route registration before rendering.
* Routing introduces one persisted indirection layer between the QR and the module-owned page target.
* Missing or corrupt route registrations prevent automatic routing.
* Route lifecycle and supersession require explicit records and validation.
* Modules require integration code for route registration and target resolution.
* A syntactically valid QR is insufficient for routing without its persisted registration.
* Older printed pages become unsupported rather than automatically routable.

### Risks and mitigations

#### Missing registration before rendering

**Risk:** A module prints a QR for which no registration exists.

**Mitigation:** Registration persistence must complete successfully before rendering begins. Page generation must fail otherwise.

#### Route-ID reuse

**Risk:** One route ID is assigned to more than one target.

**Mitigation:** Core provides collision-resistant generation and exclusive registration creation. Existing route IDs cannot be overwritten or reused.

#### Silent registration repointing

**Risk:** An existing QR begins resolving to a different page target.

**Mitigation:** Locator and target identity are immutable. Corrections use lifecycle, supersession, or resolution records.

#### Semantic duplication in `module_details`

**Risk:** Modules duplicate student, Author, Subject, or page records inside the route registration.

**Mitigation:** `module_details` is limited to lightweight diagnostics or lookup support. The module-owned target remains authoritative.

#### Manual path construction

**Risk:** Modules bypass Core path validation or create incompatible registration layouts.

**Mitigation:** Core owns deterministic path helpers and safe persisted registration operations. Modules use the public Core API.

#### Treating QR validity as authenticity

**Risk:** A valid PDS2 string is treated as proof that a page is genuine or ready for scoring.

**Mitigation:** Successful processing requires registration lookup, exact matching, lifecycle validation, target validation, and normal module Review rules.

#### Unsupported old pages

**Risk:** A previously generated PDS1 or OMR1 page cannot be routed.

**Mitigation:** This consequence is accepted because Paper Data Suite has no active production users or required legacy data.

## Alternatives Considered

### Extend PDS1 with additional optional fields

Example:

```text
PDS1|module=...|class=...|aid=...|sid=...|page=...|target_type=...|target_id=...
```

Rejected because it would:

* preserve incompatible PDS1 semantics;
* keep student identity privileged;
* produce ambiguous combinations of old and new fields;
* increase QR density;
* retain arbitrary extension metadata;
* and make interpretation dependent on module-specific conventions.

### Make `student_id` optional

Rejected because it would:

* treat non-student routes as exceptions;
* preserve student identity as the presumed route target;
* fail to provide durable physical-page identity;
* fail to address unqualified assignment collisions;
* and fail to separate routing from semantic Subject identity.

### Use module-specific QR grammars

Rejected because it would:

* duplicate parser and validation logic;
* complicate mixed-module scans;
* produce inconsistent identifier and security rules;
* weaken shared Core infrastructure;
* and require every scanner to understand every module grammar.

### Encode the module-owned target directly in the QR

Example:

```text
PDS2|m=concord|target=artifact_page_...
```

Rejected because it would:

* couple the printed payload directly to module record semantics;
* remove the shared route-registration boundary;
* make route lifecycle and supersession harder;
* encourage module-specific QR fields;
* and conflate route identity with semantic record identity.

### Use one globally indexed route ID

Example:

```text
PDS2|r=rt_...
```

Rejected for the initial local-first design because it would:

* require a global route index or database;
* introduce an additional single point of lookup and repair;
* provide weaker diagnostics when the index is damaged;
* and abandon the existing class-oriented workspace structure.

The selected four-field envelope permits deterministic lookup directly from the workspace.

### Encode a destination path in the QR

Rejected because it would:

* permit untrusted physical input to propose filesystem destinations;
* create path-traversal and containment risks;
* couple printed pages to one storage layout;
* and prevent transparent path-layout changes.

### Permit arbitrary extension metadata

Rejected because it would:

* make payload meaning module-specific;
* increase QR size;
* duplicate mutable module data;
* create silent compatibility differences;
* and encourage semantic context to migrate back into the printed code.

### Use the module target record ID as the route without a registration

Rejected because it would:

* conflate route identity with semantic record identity;
* prevent route lifecycle from remaining independent;
* make correction and supersession harder;
* remove shared registration validation;
* and force the printed code to depend on module record design.

### Retain PDS1 or OMR1 parsing for compatibility

Rejected because:

* no production user requires compatibility;
* maintaining unused formats would increase testing and maintenance burden;
* legacy normalization would preserve student-oriented assumptions;
* and the compatibility layer could weaken the clarity of the new contract.

## Required Follow-Up

Implementation was completed through the following Core issues:

1. `Paper-Data-Suite/pds-core#137`
   Add generic routing identity models and route-ID generation.

2. `Paper-Data-Suite/pds-core#138`
   Implement strict PDS2 parsing and canonical serialization.

3. `Paper-Data-Suite/pds-core#139`
   Implement module-qualified workspace paths and route-registration persistence.

4. `Paper-Data-Suite/pds-core#140`
   Implement module profiles and dispatch.

5. `Paper-Data-Suite/pds-core#141`
   Generalize scan failure and resolution metadata.

6. `Paper-Data-Suite/pds-core#142`
   Revise Core documentation and release `pds-core v0.5.0`.

The coordinated downstream migrations are:

* `Paper-Data-Suite/pds-scoreform#137`
* `Paper-Data-Suite/pds-quillan#329`
* `Paper-Data-Suite/pds-concord#17`

The implementation work must remove active PDS1 and OMR1:

* parsing code;
* generation code;
* normalized payload assumptions;
* public APIs;
* tests;
* and supported-contract documentation.

## References

* `Paper-Data-Suite/pds-core#135`
* `Paper-Data-Suite/pds-core#136`
* `Paper-Data-Suite/pds-concord#10`
* `Paper-Data-Suite/pds-concord/docs/design/pds-core-integration-requirements.md`
* `docs/qr_payload_and_routing_contract.md`
* `docs/active_scan_contract.md`
* `pds_core/qr_payload.py`
* `pds_core/pds1.py`
* `pds_core/routes.py`
* `pds_core/identifiers.py`
* `Paper-Data-Suite/pds-scoreform#137`
* `Paper-Data-Suite/pds-quillan#329`
* `Paper-Data-Suite/pds-concord#17`

## Notes

This ADR establishes architectural invariants rather than final implementation names or serialized schemas.

The following details remain for the linked implementation issues:

* exact Python module layout;
* dataclass or model implementation;
* route-ID generation algorithm;
* field-specific identifier-length limits;
* exact route-registration JSON representation;
* exact lifecycle status enumeration;
* persistence helper names;
* filesystem sharding if later required;
* module-profile discovery mechanism;
* exception hierarchy;
* and generalized failure and resolution JSON schemas.

Those details must conform to the decisions recorded here.
