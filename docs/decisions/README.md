# PDS Core Architecture Decision Records

This directory contains Architecture Decision Records for `pds-core`.

An Architecture Decision Record documents a significant architectural decision, the problem that required the decision, the selected approach, its consequences, and the principal alternatives considered.

Accepted ADRs govern later Core contracts, public APIs, schemas, storage conventions, module integrations, and implementation work.

## Naming Convention

ADR filenames use a four-digit sequence followed by a concise lowercase hyphenated title:

```text
NNNN-decision-name.md
```

Example:

```text
0001-adopt-pds2-page-locator-routing.md
```

ADR numbers are never reused, including when an ADR is later deprecated, rejected, or superseded.

## Current Decisions

| ADR                                             | Decision                        | Status   |
| ----------------------------------------------- | ------------------------------- | -------- |
| [0001](0001-adopt-pds2-page-locator-routing.md) | Adopt PDS2 Page-Locator Routing | Accepted; implemented in v0.5.0 |

## Standard ADR Structure

Each ADR should normally include:

```text
# ADR NNNN: Decision Title

Status
Date
Decision owners
Applies to
Related issue

Context
Decision
Consequences
Alternatives Considered
Required Follow-Up
References
Notes
```

The exact section structure may vary, but every ADR must clearly document:

* the architectural problem or design pressure;
* the accepted decision;
* the important invariants established by the decision;
* positive and negative consequences;
* credible alternatives considered;
* required follow-up work;
* and relevant supporting documentation or issues.

An ADR should address one coherent architectural decision.

It should not become a replacement for:

* a complete implementation plan;
* a full serialized schema specification;
* API reference documentation;
* detailed user-interface design;
* module-specific workflow documentation;
* or release notes.

Those materials may reference and elaborate on an ADR but must remain consistent with it.

## ADR Statuses

### Proposed

The decision is under consideration and does not yet govern implementation.

A new ADR may remain `Proposed` while its pull request is under review.

### Accepted

The decision has been approved and governs current architecture and implementation.

Implementation convenience must not silently override an accepted ADR.

### Deprecated

The decision is no longer recommended, but no single later ADR completely replaces it.

A deprecated ADR must explain why it is deprecated and identify any relevant later guidance.

### Superseded

A later ADR replaces the decision.

The superseded ADR must identify the replacing ADR and remain available as part of the project history.

### Rejected

The proposal was considered but not adopted.

Rejected ADRs may be retained when their reasoning is useful or likely to recur.

## Adding a New ADR

Before adding an ADR:

1. Confirm that the subject is an architectural decision rather than an ordinary implementation detail or documentation update.
2. Review existing ADRs for overlap or conflict.
3. Select the next unused four-digit sequence number.
4. Create the ADR using the filename convention.
5. Begin with `Proposed` unless the decision has already been explicitly accepted.
6. Explain the decision independently enough that a future maintainer can understand it without reconstructing the original discussion.
7. Document important consequences and credible rejected alternatives.
8. Link relevant issues, contracts, source files, and supporting design documents.
9. Add the ADR to the Current Decisions table in this file.
10. Check the complete ADR set for consistency.

A new ADR should normally be created when a change:

* replaces a shared QR or routing contract;
* changes foundational identity rules;
* changes module ownership or dependency direction;
* changes workspace or persistence architecture;
* changes source-retention or provenance requirements;
* introduces or removes a suite-wide compatibility obligation;
* changes the relationship between Core and module-owned records;
* or reverses an accepted architectural constraint.

## Editing an Accepted ADR

Accepted ADRs may be edited for limited non-semantic maintenance, including:

* correcting typographical errors;
* repairing links;
* improving formatting;
* clarifying wording without changing the decision;
* or adding references to later implementation or documentation.

An accepted ADR must not be silently edited to:

* reverse the decision;
* weaken an invariant;
* materially expand its scope;
* or introduce a conflicting architectural rule.

When the architecture changes materially, create a new ADR.

## Superseding an ADR

To supersede an accepted ADR:

1. Create a new ADR using the next unused number.

2. Set the new ADR to `Accepted`.

3. Explain what changed and why the earlier decision is no longer sufficient.

4. Identify the affected earlier ADR.

5. Change the earlier ADR status to:

   ```text
   Superseded by ADR NNNN
   ```

6. Add a prominent reference from the earlier ADR to the replacing ADR.

7. Update the Current Decisions table.

8. Preserve the original ADR text and reasoning.

Supersession is historical rather than destructive.

The earlier ADR remains part of the architectural record.

## Deprecating an ADR

Deprecation is appropriate when a decision should no longer guide new work but is not completely replaced by one later ADR.

To deprecate an ADR:

1. Change its status to `Deprecated`.
2. Add a concise explanation.
3. Link any relevant replacement guidance.
4. Update the Current Decisions table.
5. Preserve the original decision and rationale.

## Authority and Precedence

When Core documentation disagrees, use this precedence:

1. An accepted ADR governs the architectural decision.
2. An accepted shared contract governs detailed record, schema, or workflow requirements.
3. Public API documentation describes the supported implementation surface.
4. Implementation documentation describes current behavior.
5. Historical, superseded, exploratory, or migration documents provide context but do not override active decisions.

Source code that conflicts with an accepted ADR represents incomplete migration or a defect; it does not silently redefine the architecture.

## Relationship to Other Documentation

The primary `pds-core` documentation includes:

* [`../../README.md`](../../README.md) — repository overview and current capabilities;
* [`../qr_payload_and_routing_contract.md`](../qr_payload_and_routing_contract.md) — historical PDS1 QR and routing contract, superseded for new work by ADR 0001;
* [`../active_scan_contract.md`](../active_scan_contract.md) — active scan intake, retained-source, routing-review, failure, resolution, and provenance contract;
* [`../roster_workspace_contract.md`](../roster_workspace_contract.md) — shared class, roster, and workspace conventions;
* [`../standards_contract.md`](../standards_contract.md) — shared standards-management contract;
* and [`../module_standards_integration.md`](../module_standards_integration.md) — module-facing standards integration guidance.

ADR 0001 establishes the active architectural direction for:

* PDS2 QR payloads;
* durable expected-page route identity;
* persisted route registrations;
* module-qualified work identity;
* module-owned page targets;
* and the removal of PDS1 and OMR1 support.

That decision is implemented by `pds-core` v0.5.0. Active module guidance is
the [PDS2 module integration guide](../pds2_module_integration.md), together
with the accepted contracts it links. Issues under
`Paper-Data-Suite/pds-core#135` preserve the completed implementation history.

## Cross-Repository Decisions

Some Core decisions originate from design pressure discovered in another Paper Data Suite module.

A Core ADR may therefore reference design documents or accepted ADRs from:

* `pds-scoreform`;
* `pds-quillan`;
* `pds-concord`;
* or another PDS repository.

Those references provide requirements and rationale, but the Core ADR remains authoritative for the shared Core contract.

Consuming modules must conform to accepted Core ADRs when using Core-owned:

* QR formats;
* shared identity models;
* workspace paths;
* route registrations;
* source provenance;
* failure metadata;
* or module-integration interfaces.

Module-specific domain semantics remain under the authority of the owning module’s accepted ADRs and contracts.
