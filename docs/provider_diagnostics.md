# Core Provider Diagnostics

PDS Core exposes a read-only diagnostic surface for the provider contracts that
Core itself defines. The diagnostic API is intended for neutral health-check
consumers such as the Paper Data Suite shell. It does not replace Core's strict
runtime registries and does not turn Core into a suite package inventory or
application launcher.

The public module is:

```python
pds_core.provider_diagnostics
```

The diagnostic scope contains three Core-owned provider families:

```text
routing_module
  paper_data_suite.modules
  ModuleProfile

publication_producer
  paper_data_suite.publication_producers
  PublicationProducerProfile

module_operations
  paper_data_suite.module_operations
  ModuleOperationsProfile
```

Suite qualification, installed package versions, console scripts, launchability,
Python qualification, external prerequisites, and release composition remain
outside Core.

## Two diagnostic depths

The API deliberately separates metadata inspection from provider execution.
Callers must choose the deeper operation explicitly.

### Metadata-only inspection

```python
from pds_core.provider_diagnostics import inspect_core_provider_entry_points

rows = inspect_core_provider_entry_points()
```

`inspect_core_provider_entry_points(...)` enumerates entry-point metadata and
returns immutable `ProviderEntryPointMetadata` rows. It does not call
`EntryPoint.load()` and therefore does not import or execute optional provider
code merely to describe what is installed.

Each row contains only bounded diagnostic metadata:

```text
provider_kind
entry_point_group
entry_point_name
entry_point_target
distribution_name, when safely determinable
```

Untrusted display metadata is made single-line by replacing control, line, and
paragraph separators. Current display bounds are:

```text
entry-point name       256 characters
entry-point target    1024 characters
distribution name      256 characters
```

Longer display values are truncated with an ellipsis. These display values are
not an authorization or identity source. Provider validation uses the actual
entry-point identity and the returned Core profile.

The result order is deterministic by provider family and exposed metadata.
No installed candidates is a valid empty result.

### Explicit provider validation

```python
from pds_core.provider_diagnostics import diagnose_core_providers

results = diagnose_core_providers()
```

`diagnose_core_providers(...)` explicitly permits Core to load and invoke each
candidate provider. Each candidate is processed independently through the
applicable stages:

```text
load
call
profile_validation
identity_validation
compatibility
registry_conflict
valid
```

For a routing provider, compatibility means support for the active
`CORE_ROUTING_CONTRACT_VERSION`. For a publication producer, compatibility
means support for the active Core Publication Record schema version declared by
`PUBLICATION_RECORD_SCHEMA_VERSION`. For a module-operations provider,
compatibility means support for the active
`MODULE_OPERATIONS_CONTRACT_VERSION`.

The diagnostic path does not perform route dispatch, open a publication
manifest, evaluate a specific Publication Record, or call module-owned business
logic beyond the zero-argument profile provider itself. In particular,
diagnosing a `ModuleOperationsProfile` does not invoke its readiness or
attention capability.

## Result model

Each candidate produces an immutable `ProviderDiagnosticResult` containing:

```text
safe entry-point metadata
stage reached
stable diagnostic code
bounded safe message
whether loading was attempted/succeeded
whether provider invocation was attempted/succeeded
declared profile identity when safely available
profile-validation outcome
Core-compatibility outcome
registry-conflict state
validated Core profile on an unambiguous success
```

The initial stable diagnostic codes are:

```text
provider.entry_point_name_invalid
provider.load_failed
provider.not_callable
provider.call_failed
provider.profile_invalid
provider.identity_mismatch
provider.core_incompatible
provider.identity_conflict
provider.valid
```

Normal diagnostic messages do not include raw provider exception text or
tracebacks. The original exception is not serialized into the result. An
entry-point enumeration failure raises `ProviderEnumerationError` with bounded
Core-owned text and retains the underlying exception only as the Python
exception cause for callers that are explicitly handling the failure in-process.

## Failure isolation

One broken candidate does not hide unrelated candidate observations.
For example, an environment containing one valid routing provider and another
whose entry point raises during load produces one `provider.valid` result and
one `provider.load_failed` result.

This behavior is intentionally different from runtime registry construction.
Diagnostics may describe a partially broken installed environment; runtime code
must not treat that description as a partially trusted registry.

Duplicate identities are reported without erasing the individual candidates.
If two validated providers in the same provider family claim one Core identity,
each candidate receives:

```text
stage: registry_conflict
code: provider.identity_conflict
```

The candidates retain their own entry-point target and owning-distribution
metadata so a diagnostic consumer can explain the conflict. A module may
legitimately expose routing, publication, and module-operations providers with
the same `module_id`; identities conflict only within the same Core provider
family.

## Strict runtime registries remain authoritative

The existing runtime APIs retain fail-closed semantics:

```python
from pds_core.module_profiles import (
    build_module_registry,
    discover_module_profiles,
)
from pds_core.publication_compatibility import (
    build_publication_producer_registry,
    discover_publication_producer_profiles,
)
```

Those functions continue to reject malformed, mismatched, or conflicting
installed providers rather than silently omitting them. The diagnostic API is
not a substitute for either registry and must not be used to construct a
partial routing or publication registry after a diagnostic failure.

In particular:

```text
diagnostic observation != runtime authorization
diagnostic success     != suite qualification
diagnostic presence    != launchability
```

## Workspace independence and import behavior

Provider metadata/profile diagnostics require no PDS workspace. They do not:

```text
resolve or create a workspace
read classes or rosters
read student evidence
read route registrations
read retained scans
read module work roots
read Publication Records
open or hash publication manifests
```

Metadata-only inspection does not load optional applications. Explicit provider
validation may import provider code only through the installed Core-defined
entry point being diagnosed. Core does not hard-code imports for ScoreForm,
Quillan, Concord, Meridian, Vitrine, Portia, or any other sibling application.

Importing `pds_core` itself remains side-effect free.

## Privacy and safety

The provider diagnostic surface is infrastructure diagnostics, not a bulk-data
API. It does not require or normally expose:

```text
student names or identifiers
student answers or writing
scores or ratings
teacher feedback
behavior narratives
portfolio content
raw scans
QR payload bodies
workspace file listings
environment dumps
credentials or secrets
raw tracebacks
```

Provider profile objects may contain the existing Core contract callables and
compatibility metadata because those are already part of the Core provider
contract. Consumers should present the bounded diagnostic fields rather than
serializing arbitrary Python object representations.

## Ownership boundary and `pds doctor`

Core owns:

```text
Core provider entry-point groups
Core provider profile validation
Core compatibility checks for those profiles
Core provider-identity conflicts
bounded provider diagnostic outcomes
```

The Paper Data Suite shell owns:

```text
release-qualified component inventory
exact package and wheel versions
Python qualification
console-script expectations
application launchability
external prerequisites
PASS / WARN / FAIL / SKIP presentation
teacher-facing remediation and overall health
```

Therefore a suite health command may consume these results, but Core does not
encode suite doctor policy. A missing provider is not automatically an unhealthy
installed application unless the suite's own release contract says that
provider is required.

## Module-operations capability invocation is separate

The module-operations provider family is now defined in
[`module_operations.md`](module_operations.md). Provider diagnostics cover only
entry-point metadata and zero-argument profile validation.

Actual readiness and attention evaluation is a separate, explicit operation
through:

```python
invoke_module_readiness(...)
invoke_module_attention(...)
invoke_module_operations(...)
```

Those calls use their own bounded invocation result codes so a valid profile
whose module-owned readiness callable later fails is not confused with an
entry-point/profile load failure.

In particular:

```text
provider.valid
!=
readiness evaluated

provider.valid
!=
attention evaluated

module_operations.provider_failed
!=
provider.call_failed
```
