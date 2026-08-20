# Module Operations Provider Contract

PDS Core defines one neutral, versioned provider contract for module-owned
operational readiness and teacher-attention summaries.

The public implementation is:

```python
pds_core.module_operations
```

The installed entry-point group is:

```text
paper_data_suite.module_operations
```

The active contract version is:

```text
1
```

This contract exists so a neutral consumer such as the Paper Data Suite shell
can ask an installed module for bounded operational facts without importing
module-private implementation code or reading the module's private store.

The ownership boundary is:

```text
Core
  contract models
  structural validation
  provider-profile compatibility
  bounded capability invocation results

module
  readiness meaning
  attention meaning
  module-owned codes and labels
  action meaning
  private data access required to evaluate its own state

Paper Data Suite shell
  expected-component policy
  aggregation and presentation
  PASS / WARN / FAIL / SKIP mapping
  remediation wording
  application launch policy
```

Core does not rank educational work, implement module repairs, or define what
ScoreForm, Quillan, Concord, Meridian, Vitrine, Portia, or another module should
consider ready or attention-worthy.

## Provider profile

An installed module exposes a zero-argument entry-point provider returning:

```python
ModuleOperationsProfile(
    module_id=...,
    supported_core_operations_contract_versions=...,
    readiness_provider=...,
    attention_provider=...,
)
```

`module_id` is a lowercase Core identifier. The profile must expose at least one
of `readiness_provider` or `attention_provider`. Each supplied capability must be
callable.

Compatibility is explicit:

```python
MODULE_OPERATIONS_CONTRACT_VERSION = "1"
```

A profile may be structurally valid while not supporting the active Core
operations contract. Provider diagnostics report that state as Core
incompatibility rather than misclassifying the profile as malformed.

The operations profile is independent from:

```text
paper_data_suite.modules
paper_data_suite.publication_producers
application launchability
suite release qualification
package version
console-script identity
```

The same `module_id` may legitimately expose routing, publication, and
module-operations profiles. Duplicate identity conflicts are scoped to one
provider family.

## Request context

Capability invocation accepts one immutable `ModuleOperationsRequest` with
optional:

```text
workspace_root
active_school_year
class_id
```

`workspace_root`, when supplied, must be an absolute `pathlib.Path`.
`active_school_year` uses Core's `YYYY-YYYY` consecutive-year validation.
`class_id` uses Core identifier validation.

The request does not contain:

```text
whole rosters
student records
suite report objects
database handles
module stores
raw scans
publication bodies
arbitrary environment mappings
```

Creating or validating a request does not inspect the filesystem or create a
workspace. A capability may use an explicitly supplied workspace internally to
evaluate module-owned state, but the v1 operations contract is read-only.

## Readiness

Readiness asks:

```text
Can this module meaningfully operate in the supplied context?
```

A `ModuleReadinessReport` contains:

```text
evaluation
ready
notices
```

`evaluation` is exactly:

```text
evaluated
unavailable
```

The invariant is:

```text
evaluation == evaluated
  -> ready is exactly True or False

evaluation == unavailable
  -> ready is None
```

Therefore:

```text
unable to evaluate
!=
evaluated and not ready
```

A readiness notice is a bounded `ModuleOperationsNotice` containing:

```text
code
summary
optional ModuleOwnerActionRef
```

Notice codes are module-owned. Core validates their syntax and bounds but does
not interpret their domain meaning.

## Attention

Attention asks:

```text
Does this module currently have teacher work needing attention?
```

A `ModuleAttentionReport` contains:

```text
evaluation
summaries
notices
```

When `evaluation == "unavailable"`, `summaries` must be empty.

When `evaluation == "evaluated"`, an empty `summaries` tuple means the module
successfully evaluated the supplied context and found no attention summaries.

Therefore:

```text
successful empty attention
!=
evaluation unavailable
!=
provider failure
!=
invalid provider result
```

Each `ModuleAttentionSummary` contains only bounded neutral fields:

```text
code
label
optional count
optional class_id
optional ModuleWorkRef
optional ModuleOwnerActionRef
```

`count` is an aggregate count, not a score. It is bounded and nonnegative.

If both `class_id` and `work_ref` are present, their class identities must
match. When the caller requested a particular `class_id`, returned attention
summaries may not contradict that requested class.

If a `work_ref` is present, its `module_id` must match the provider owner during
invocation validation.

## Owner-routed actions

`ModuleOwnerActionRef` contains exactly:

```text
module_id
action_id
```

It is an inert module-owned reference for preserving a future handoff to the
owning application.

It is not:

```text
a shell command
a command-line fragment
an executable path
a filesystem path
a URL
a Python import target
a callable name
serialized code
an eval/exec payload
```

Core validates ownership and structure only. The operations contract does not
execute actions and does not authorize mutation.

An action included in a provider result must belong to the reporting module.
The v1 contract does not define cross-owner actions.

## Boundedness

The v1 shared limits are:

```text
readiness/attention notices     16
attention summaries            32
code/action identifier length  64 characters
attention label length        160 characters
notice/invocation text        240 characters
aggregate count          0..1,000,000
```

Codes and action IDs use Core identifier syntax. Human-readable labels and
summaries must be nonblank, single-line safe text; control, line-separator, and
paragraph-separator characters are rejected.

The contract intentionally has no generic arbitrary payload field.

The contract also does not define a cross-module urgency score. A module owns
its domain facts; Core does not establish universal educational priority or
rank one module's work against another module's work.

If a module has more underlying records than the shared result can represent,
the provider should aggregate them into bounded summaries rather than copy the
records into Core.

## Provider metadata and profile diagnostics

Module-operations entry points participate in
[`provider_diagnostics.md`](provider_diagnostics.md).

Metadata-only inspection:

```python
inspect_core_provider_entry_points(provider_kind="module_operations")
```

enumerates bounded entry-point metadata but does not:

```text
load provider code
call the zero-argument profile provider
invoke readiness
invoke attention
require a workspace
```

Explicit provider diagnosis:

```python
diagnose_core_providers(provider_kind="module_operations")
```

may load the entry point and call the zero-argument profile provider, then
checks:

```text
profile structure
entry-point/profile identity
active operations-contract compatibility
same-family duplicate identity
```

It still does not invoke readiness or attention.

Module operations reuse the existing provider-diagnostic failure vocabulary:

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

A valid diagnostic result is not suite qualification or launch authorization.

## Capability invocation

After a caller has an unambiguous compatible `ModuleOperationsProfile`, Core
provides:

```python
invoke_module_readiness(profile, request)
invoke_module_attention(profile, request)
invoke_module_operations(profile, request)
```

The combined function invokes readiness first and attention second and returns
two independent results.

Each capability produces a `ModuleOperationsInvocationResult` with:

```text
module_id
capability
code
safe message
provider_call_attempted
provider_call_succeeded
result_validation
validated report, on success/unavailable evaluation
```

Stable invocation codes are:

```text
module_operations.capability_absent
module_operations.evaluation_unavailable
module_operations.evaluated
module_operations.provider_failed
module_operations.result_invalid
```

The distinctions are intentional.

### Capability absent

```text
module_operations.capability_absent
```

means the valid profile does not expose that optional capability. No capability
call occurred.

### Evaluation unavailable

```text
module_operations.evaluation_unavailable
```

means the capability ran successfully and returned a valid report explicitly
saying it could not evaluate the supplied context.

### Evaluated

```text
module_operations.evaluated
```

means the capability ran and its returned report passed Core validation. For
attention, that report may legitimately contain zero summaries.

### Provider failed

```text
module_operations.provider_failed
```

means module-owned capability code raised while evaluating. Core does not place
the raw provider exception or traceback in the normal shared result.

### Result invalid

```text
module_operations.result_invalid
```

means the provider call returned but its result did not satisfy the shared
contract.

Core never converts either failure into:

```text
ready
not ready
no attention
```

## Failure isolation

Operations capabilities are independent.

A readiness failure does not imply an attention failure, and an attention
failure does not erase a successful readiness result.

Across modules, consumers should preserve the same isolation. A broken
ScoreForm operations provider, for example, must not hide an unrelated valid
Quillan or Concord provider observation.

Provider-profile conflicts are also family-scoped. Core does not arbitrarily
select one of two module-operations entry points claiming the same `module_id`.

## Privacy

The shared operations surface is deliberately not a bulk-data API.

It does not require or normally expose:

```text
student names
student answers or writing
scores or percentages
standards-rating bodies
teacher feedback bodies
behavior narratives
portfolio artifacts
raw scans
QR payload bodies
grouping-signal band values
whole rosters
whole module records
Publication Record bodies
credentials or secrets
raw tracebacks
```

A module may inspect its own private state internally to calculate a bounded
readiness or attention result. That does not authorize Core or the suite shell
to receive the private source records.

Routine shared invocation failures use Core-owned bounded messages rather than
arbitrary provider exception text.

## `pds doctor`

A suite health command may consume module readiness.

Core does not own:

```text
DoctorReport
DiagnosticCheck
PASS / WARN / FAIL / SKIP
overall health
teacher remediation wording
expected installed component inventory
package-version qualification
external prerequisite policy
```

A missing operations provider or missing readiness capability is not
automatically a Core health failure. The active suite release contract decides
whether and how to present that absence.

## Launcher separation

The operations provider is not an application launcher contract.

Do not infer:

```text
operations provider present
  -> application is launchable

application is launchable
  -> operations provider is present
```

Console-script expectations, installed distribution identity, suite-supported
versions, and launch routing remain suite-owned.

`ModuleOwnerActionRef` does not weaken that boundary because it is inert and is
not interpreted by Core as an executable target.

## Grouping-signal separation

The module-operations contract is independent from
[`grouping_signal_set_v1.md`](grouping_signal_set_v1.md).

Grouping signals are contextual ordinal planning interchange. They are not:

```text
readiness
attention
health
diagnostic severity
teacher priority
owner-routed actions
```

Ordinary operations reports must not expose grouping-signal band values.

## Downstream implementation rule

A sibling module implementing this contract should:

1. register `paper_data_suite.module_operations` under its exact lowercase
   `module_id`;
2. return a valid zero-argument `ModuleOperationsProfile`;
3. advertise operations contract version `"1"`;
4. expose only the capabilities it genuinely supports;
5. keep readiness and attention domain meaning inside the module;
6. return bounded privacy-minimal reports;
7. use owner-routed action IDs only as inert module-local references;
8. preserve `unavailable` instead of inventing false negative state when
   required context cannot be evaluated;
9. never treat a provider exception as an empty attention result; and
10. keep module operations separate from launchability, routing, publication,
    grading, grouping, repair, and private-store access by the suite shell.

Core unit tests use synthetic providers. Core has no hard-coded runtime import
of sibling PDS applications.
