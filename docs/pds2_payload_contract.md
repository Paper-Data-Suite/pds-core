# PDS2 Page-Locator Payload Contract

PDS Core implements the strict PDS2 QR payload text contract in
`pds_core.pds2`. The payload carries only the identity needed to locate a
persisted route registration:

```text
PDS2|m=<module_id>|c=<class_id>|w=<work_id>|r=<route_id>
```

Parsing establishes valid locator syntax and identity. It does not prove that
a class, work item, route registration, target, or filesystem path exists, and
it does not authorize processing, evidence creation, or scoring.

This contract implements
[ADR 0001](decisions/0001-adopt-pds2-page-locator-routing.md) and produces the
[`RouteLocator`](routing_identity_models.md#routelocator) model owned by
`pds_core.routing_models`.

## Grammar and field mapping

```text
payload    = "PDS2" "|" field "|" field "|" field "|" field
field      = key "=" identifier
key        = "m" | "c" | "w" | "r"
identifier = one or more ASCII letters, digits, "_" or "-"
```

Each key must occur exactly once. A parser accepts the four fields in any
order, but the serializer always emits `m`, `c`, `w`, `r` order.

| QR key | `RouteLocator` value |
| --- | --- |
| `m` | `work.module_id` |
| `c` | `work.class_id` |
| `w` | `work.work_id` |
| `r` | `route_id` |

Keys and the `PDS2` schema identifier are case-sensitive. Values are used
exactly as supplied: Core does not trim, case-fold, decode, unquote, unescape,
or otherwise normalize them. `module_id` is lowercase under the shared routing
model contract; the other identifiers may contain uppercase ASCII letters.

Unknown fields, long-form aliases, legacy PDS1 keys, repeated fields, empty
segments, empty keys or values, extra `=` delimiters, percent encoding,
whitespace, and arbitrary metadata are invalid.

## Size and encoding

The entire payload must be ASCII and no more than 256 ASCII bytes. Because all
accepted content is ASCII, its encoded byte count equals its character count.
The hard size limit is checked before detailed segment parsing.

The recommended operational target is 160 ASCII bytes to leave room for
practical QR density and rendering choices. This is guidance, not a validation
limit: payloads from 161 through 256 bytes remain valid.

## Initial module examples

All modules use the same exact four-field grammar and canonical field order.
Module-specific meaning is resolved through the route registration and the
module-owned target record, not by adding fields to the QR.

### ScoreForm

```text
PDS2|m=scoreform|c=english9_p2|w=rj_act1_quiz|r=rt_0123456789abcdef0123456789abcdef
```

ScoreForm's `work_id` may correspond to its module-owned assignment
identifier. The QR does not carry student identity, a logical page number, or
answer-sheet semantics.

### Quillan

```text
PDS2|m=quillan|c=english12_p4|w=personal_narrative|r=rt_1123456789abcdef0123456789abcdef
```

Page number, continuation relationships, submission ownership, and template
information remain behind the route registration and Quillan's module-owned
response-page record.

### Concord

```text
PDS2|m=concord|c=english10_p3|w=socratic_seminar_1|r=rt_2123456789abcdef0123456789abcdef
```

Author, Subject, Group, Session, Activity Event, Artifact, and scoring
relationships are not encoded in the QR. Concord resolves those relationships
through its registered module-owned records.

## Public API

```python
from pds_core.pds2 import (
    PDS2_FIELD_ORDER,
    PDS2_MAX_PAYLOAD_BYTES,
    PDS2_RECOMMENDED_PAYLOAD_BYTES,
    PDS2_REQUIRED_FIELDS,
    Pds2PayloadError,
    parse_pds2_payload,
    serialize_pds2_payload,
)
```

The fixed constants are:

```python
PDS2_FIELD_ORDER = ("m", "c", "w", "r")
PDS2_REQUIRED_FIELDS = frozenset({"m", "c", "w", "r"})
PDS2_MAX_PAYLOAD_BYTES = 256
PDS2_RECOMMENDED_PAYLOAD_BYTES = 160
```

The module imports `PDS2_SCHEMA` from `pds_core.routing_models`; it does not
define a second schema constant.

### Parsing

```python
from pds_core.pds2 import parse_pds2_payload

payload_text = (
    "PDS2|m=concord|c=english10_p3|w=socratic_seminar_1|"
    "r=rt_0123456789abcdef0123456789abcdef"
)
locator = parse_pds2_payload(payload_text)

assert locator.module_id == "concord"
assert locator.class_id == "english10_p3"
assert locator.work_id == "socratic_seminar_1"
```

The result is a validated `RouteLocator` composed with a `ModuleWorkRef`. It is
not a dictionary, route registration, module record, or route resolution.

### Serialization

```python
from pds_core.pds2 import serialize_pds2_payload

canonical = serialize_pds2_payload(locator)
assert canonical == payload_text
```

Serialization accepts only a `RouteLocator`, revalidates it, emits the fixed
field order, and applies the same ASCII and 256-byte limits. Mappings, strings,
work references, registrations, resolutions, and arbitrary objects are not
accepted as convenience inputs.

## Errors

Expected parse and serialization failures raise `Pds2PayloadError`, a
`ValueError` subclass. Messages identify the relevant schema, encoding, size,
segment, field, or identifier problem. When shared routing-model validation
fails, the original `RoutingModelError` is retained as the exception cause.

There is no permissive fallback or automatic recovery. In particular, PDS1
and OMR1 strings are unsupported-schema failures when passed to the PDS2
parser.

## Deliberately excluded data

A PDS2 payload contains no student ID, assignment ID, logical page number,
page count, template, form, document type, Author, Subject, Group, destination,
Score target, or module metadata. Those values cannot be inferred from the QR
text. Module-owned meaning belongs behind the separate persisted registration
and target contracts.

This module performs no filesystem access, registration lookup, QR image
generation or decoding, logging, warning emission, dispatch, or module-owned
record loading.
