# Producer reader-contract metadata (Core #229)

Core exposes **optional, producer-declared public reader metadata** through
`pds_core.publication_compatibility`. The declaration lets consumers such as
Meridian and Vitrine compare a producer's stable reader contract with their own
adapter support. It does not execute readers, grant access, or establish that a
consumer supports the declared contract.

This reference describes the new API on the Core #229 development branch.
Until a Core release containing it is published, this is **not** an API claim
about Core 0.6.4 or older released wheels.

Installed-wheel smoke and release qualification boundaries are documented in
[Issue #229 installed reader-contract qualification](validation/issue-229-installed-reader-contract-qualification.md).

## Separate identities and authorities

| Identity | Meaning | Owner |
| --- | --- | --- |
| Producer module ID | Core publication owner, e.g. `scoreform` | Producer / Core registry |
| Distribution name and exact installed version | Which Python implementation is installed and later ran | Packaging / consumer provenance |
| Manifest contract version | Format/semantics of exact serialized producer evidence | Producer |
| Reader contract version | Stable public read API, validation behavior, returned model and consumer-visible semantics | Producer |
| Core Publication Record schema and compatibility | Neutral published-record structure, capabilities and source-record support | Core |
| Consumer projection contract | How a validated producer model is interpreted in Meridian or Vitrine | Consumer |
| Exact release wheel and SHA-256 | Which artifact was independently qualified | Release qualification |

Changing a distribution version **does not itself** change the public reader
contract. Keeping a manifest contract version **does not prove** the reader's
public model is still compatible. An incompatible reader API or public-model
change requires a new reader contract even if the manifest schema stays the
same. An unchanged reader contract may span several compatible releases.

Exact distribution versions must remain available for consumer diagnostics,
provenance, and projection-cache/currentness identity where relevant. They are
not the semantic reader-contract compatibility gate. Release qualification
must still verify exact artifacts.

## Public API

`PublicationReaderSupport` is a frozen, slotted declaration with three fields:

- `manifest_contract_version`: one exact manifest contract supported by its
  enclosing `PublicationContractSupport` row.
- `distribution_name`: the providing Python distribution (canonical PEP 503
  spelling: lowercase letters/digits separated by **single hyphens**, e.g.
  `scoreform`, `quillan`, `pds-concord`, `pds-portia`; no automatic rewriting).
- `reader_contract_version`: a producer-owned, stable public reader contract ID.
  The grammar is a lowercase letter followed by lowercase letters, digits, or
  underscores, with a maximum length of 128 characters.

`manifest_contract_version` uses Core's existing path-safe contract identifier
validation; it is **not** a Standards ID or a package version.

`PublicationContractSupport.reader_support` is an optional trailing field of
`tuple[PublicationReaderSupport, ...]`, defaulting to `()`. Older positional and
keyword constructors remain valid. The collection is copied, sorted by exact
manifest contract, and frozen. At most **one** reader declaration may bind a
given manifest version within one publication-kind support row. A declaration
referencing a manifest absent from `manifest_contract_versions` is invalid.
Partial declarations are allowed: a supported manifest with no reader entry
remains **undeclared** rather than inheriting a reader for another manifest.

Invalid or ambiguous declarations raise `PublicationProducerProfileError`.
Profile revalidation, `PublicationProducerRegistry`, and installed profile
discovery preserve the same immutable declarations.

Use the pure lookup API:

```text
lookup_publication_reader_support(profile, publication_kind, manifest_contract_version)
    -> PublicationReaderSupport | None
```

Lookup matches the **exact** publication kind and manifest contract. `None`
means no reader declaration for that combination; it does **not** authorize a
fallback or establish compatibility. Invalid profile/kind/manifest inputs fail
with `PublicationProducerProfileError`.

## Producer examples (illustrative, not released producer declarations)

The following complete example runs with a Core build containing #229. It
constructs only metadata; it neither imports producer packages nor publishes a
manifest. The Portia-shaped profile is a synthetic design example for
[Portia #66](https://github.com/Paper-Data-Suite/pds-portia/issues/66), **not**
an assertion that Portia has already released its publication reader.

```python
from pds_core.publication_compatibility import (
    PublicationContractSupport,
    PublicationProducerProfile,
    PublicationReaderSupport,
    lookup_publication_reader_support,
)

scoreform_profile = PublicationProducerProfile(
    module_id="scoreform",
    display_name="Illustrative ScoreForm",
    supported_core_publication_schema_versions=frozenset({"1"}),
    supported_academic_work_contract_versions=frozenset(
        {"scoreform_academic_work_v1"}
    ),
    publication_contracts=(
        PublicationContractSupport(
            publication_kind="academic_result_set",
            manifest_contract_versions=frozenset(
                {"scoreform_academic_result_manifest_v1"}
            ),
            supported_capabilities=frozenset({"points"}),
            reader_support=(
                PublicationReaderSupport(
                    manifest_contract_version="scoreform_academic_result_manifest_v1",
                    distribution_name="scoreform",
                    reader_contract_version="scoreform_academic_result_reader_v1",
                ),
            ),
        ),
    ),
)

portia_profile = PublicationProducerProfile(
    module_id="portia_fixture",
    display_name="Synthetic Portia Intervention Producer",
    supported_core_publication_schema_versions=frozenset({"1"}),
    supported_academic_work_contract_versions=frozenset(),
    publication_contracts=(
        PublicationContractSupport(
            publication_kind="intervention_record_set",
            manifest_contract_versions=frozenset(
                {"portia_intervention_manifest_v1"}
            ),
            supported_capabilities=frozenset({"intervention_status"}),
            reader_support=(
                PublicationReaderSupport(
                    manifest_contract_version="portia_intervention_manifest_v1",
                    distribution_name="pds-portia",
                    reader_contract_version="portia_intervention_reader_v1",
                ),
            ),
        ),
    ),
)

assert lookup_publication_reader_support(
    scoreform_profile,
    "academic_result_set",
    "scoreform_academic_result_manifest_v1",
).reader_contract_version == "scoreform_academic_result_reader_v1"
assert lookup_publication_reader_support(
    portia_profile,
    "intervention_record_set",
    "portia_intervention_manifest_v1",
).distribution_name == "pds-portia"
assert lookup_publication_reader_support(
    portia_profile,
    "academic_result_set",
    "portia_intervention_manifest_v1",
) is None
```

The same metadata API serves `academic_result_set` and
`intervention_record_set`. Core's existing rule remains unchanged:
**academic-result** publications require their matching Academic Work
Registration; **intervention** publications must not carry one. No Grade Item,
proficiency, rating, or academic-result reader/model is implied for an
intervention publication. Portia's redaction and other privacy requirements
remain outside this metadata declaration.

## Producer implementation and discovery

Each producer independently documents and qualifies its own reader contract.
The declaration identifies the **public behavior**, not just the existence of
an importable function. Producer contract tests should cover at least:

- The stable public import/call surface and immutable manifest-bytes input.
- Manifest-contract validation and returned public model/fields used by consumers.
- Documented exception behavior and deterministic interpretation.
- No unexpected workspace I/O, publication mutation, hidden grading policy,
  or consumer-specific dependency.

The existing `paper_data_suite.publication_producers` entry-point group remains
the Core profile-discovery mechanism. The installed **profile provider** is
loaded and invoked; **the declared public reader is not imported or called**
by metadata validation, registry construction, exact lookup, or discovery.
Reader declarations contain no callbacks, import paths, filesystem paths, or
release-version allowlists. Core does not read manifests or workspaces while
inspecting the declaration.

Producer-specific identities under discussion for downstream integration:

| Producer | Distribution | Manifest | Proposed reader contract |
| --- | --- | --- | --- |
| ScoreForm | `scoreform` | `scoreform_academic_result_manifest_v1` | `scoreform_academic_result_reader_v1` |
| Quillan | `quillan` | `quillan_academic_result_manifest_v1` | `quillan_academic_result_reader_v1` |
| Concord | `pds-concord` | `concord_academic_result_manifest_v1` | `concord_academic_result_reader_v1` |
| Future Portia | `pds-portia` | Producer-defined intervention contract | Producer-defined intervention reader contract |

**These are planned declarations**, not declarations already present in those
released packages. Each producer must separately adopt, test, and publish its
own metadata. Concord's reader qualification must also account for its open
Standards-identity correction (#129).

## Consumer handoff (Meridian #111 and Vitrine #103)

For an authorized consumer with a canonical Core Publication Record:

1. Validate/reload the canonical publication and its applicable Core
   registration/profile metadata. Run the existing
   `evaluate_publication_compatibility(...)` check independently of reader
   compatibility.
2. Match the consumer's own adapter against the publication kind, producer
   module, manifest, capabilities, and other consumer-required contracts.
3. Call `lookup_publication_reader_support(profile, kind, manifest_contract)`.
4. If metadata **is declared**, accept it **only** when the selected consumer
   adapter explicitly supports that reader contract and distribution. If
   declared but unsupported, **fail closed**; never substitute a legacy
   version exception.
5. If metadata **is absent**, the consumer may independently apply its own
   **bounded exact-version legacy qualification list** for historical packages.
   No ranges, nearest-version inference, or automatic compatibility.
6. Resolve and retain the exact installed distribution version as execution
   provenance, separate from the reader-contract identity.
7. Separately enforce source-read authorization and Core manifest custody/
   digest validation before invoking the producer-owned public reader. Apply
   the consumer-owned projection contract to the validated public model.

Core does not implement steps 2, 4-7 as policy and does **not** ship Meridian
or Vitrine's legacy allowlist. In particular,
`evaluate_publication_compatibility(...)` intentionally returns the same
publication compatibility outcome whether valid reader metadata is present or
absent. Reader metadata is not publication validity, consumer support,
source-read authorization, or disclosure permission.

When Meridian or Vitrine first requires this API, that consumer should set its
minimum Core dependency to the **first actually released Core version** that
contains #229. Do not claim this API is present in the historical Core 0.6.4
wheel and do not rewrite historical qualification reports.

Portia #66 may adopt the same API later without introducing academic-only
contracts or automatically becoming supported by Meridian/Vitrine. Portia's
sensitive underlying records remain subject to separate producer authorization
and privacy-minimized publication rules.

## Scope and release qualification

Issue #229 changes producer-profile metadata only. It does not change the
persisted `PublicationRecord` schema, provider entry-point group, producer
manifest schemas, reader execution behavior, withdrawal/supersession semantics,
or consumer compatibility decisions. Existing profiles with
`reader_support=()` remain valid, discoverable, and Core-compatible.

Before publishing a Core release, qualify the built wheel against historical
released producer profiles and relevant installed Core consumers. Record the
exact source commit, wheel filename, version, tag and SHA-256. Keep historical
release evidence immutable; retain the exact installed producer distribution
version in consumer provenance even when a stable reader contract is accepted.
