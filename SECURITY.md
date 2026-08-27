# Security Policy

## Project Status

PDS Core is the shared infrastructure and contract package for Paper Data Suite.

The current supported release line is `0.6.x`. The current released package version is `0.6.3`.

PDS Core is pre-1.0, local-first educational software. It is not a hosted service, an institutional identity provider, a legal-compliance certification, or a substitute for school or district security controls.

`main` is the active development branch and is not itself a supported release artifact.

Local-first operation reduces unnecessary remote data handling, but it does not eliminate the need for appropriate:

* filesystem access controls;
* device security;
* backup and recovery practices;
* encryption where required;
* authorization;
* retention and deletion practices;
* secure handling of exports and removable media; and
* compliance with applicable school, district, state, and federal requirements.

## Student Data and Privacy

Paper Data Suite workspaces may contain sensitive educational records owned by Core and installed modules.

Do not commit, upload, publish, attach, or otherwise expose real classroom data in this repository, public issues, pull requests, discussions, screenshots, CI logs, or other public development artifacts.

Do not publicly post:

* real student names;
* real student IDs or other identifiers;
* real class rosters;
* grades, scores, standards ratings, or proficiency information tied to real students;
* scanned, photographed, or transcribed student work;
* student writing or assessment responses;
* accommodations, intervention, support, behavioral, disciplinary, or attendance information;
* parent, guardian, or student contact information;
* production Core records;
* producer-native records;
* producer manifests;
* Publication Records or academic-work records containing real classroom information;
* production Paper Data Suite workspaces;
* workspace backups;
* exported classroom reports;
* private school or district documents;
* credentials, access tokens, secrets, private keys, or private configuration;
* diagnostic artifacts containing identifiable classroom information; or
* screenshots or logs that expose sensitive filesystem, account, or deployment information.

Repository examples, fixtures, tests, screenshots, demonstrations, and documentation examples must use synthetic data.

Synthetic test data should use clearly fictional names, identifiers, scores, records, and content. Do not transform or lightly pseudonymize real classroom records and then treat them as synthetic fixtures.

Before committing generated files, logs, examples, diagnostic output, or fixtures, verify that they contain no copied classroom information or identifying metadata.

## Local-First Data Handling

Core provides shared infrastructure used by local teacher-controlled applications.

Local-first does not mean that all files are automatically safe merely because they remain on a local filesystem.

Users should protect Paper Data Suite workspaces with deployment-appropriate controls, including:

* operating-system account security;
* appropriate filesystem permissions;
* full-disk or removable-media encryption where required;
* protected backup destinations;
* secure handling of externally synchronized folders;
* controlled access to shared or network storage;
* appropriate retention and disposal procedures; and
* deliberate review before exporting or sharing records.

Users remain responsible for following applicable school, district, state, and federal requirements when handling educational records.

## Repository and Workspace Separation

A production Paper Data Suite workspace must not be stored inside this source repository.

Repository ignore rules are a development safeguard, not a privacy boundary.

Do not rely on `.gitignore` to protect real classroom data.

Before committing changes:

1. inspect the staged file list;
2. review generated files and logs;
3. confirm that no production workspace material is present; and
4. confirm that all fixtures and examples are synthetic.

## Core Security Boundaries

PDS Core owns shared contracts and infrastructure. It does not grant semantic authority to downstream modules merely because data can be located, parsed, or discovered.

Security-sensitive integrations must preserve the following distinctions:

```text
filesystem access != authorization

record discoverability != permission to read record contents

publication discovery != authorization to consume evidence

manifest presence != permission to open referenced artifacts

path validation != access authorization

schema validity != semantic truth

successful parsing != trusted provenance

hash agreement != confidentiality

hash agreement != proof of authorship

package installation != deployment authorization
```

Core services must not silently collapse these distinctions.

### Ownership boundaries

Core may own shared infrastructure such as:

* workspace resolution;
* class and roster authority;
* durable shared identifiers;
* shared validation contracts;
* path and storage helpers;
* publication and registration infrastructure;
* shared compatibility contracts;
* authorization interfaces;
* suite-visible module and producer profiles; and
* other explicitly documented cross-module services.

Downstream modules remain responsible for their own canonical domain records, workflows, interpretations, outputs, and module-specific data handling unless an accepted Core contract explicitly assigns ownership to Core.

Core must not become an alternate canonical store for module-owned records merely because those records participate in shared workflows.

### Authorization boundaries

Core may expose authorization interfaces or authorization-gated services, but Core does not infer institutional permission from incidental technical facts.

The following must not be treated as authorization by themselves:

* possession of a path;
* possession of an identifier;
* catalog visibility;
* filesystem readability;
* package installation;
* module discovery;
* producer-profile compatibility;
* matching student identity;
* knowledge of a publication ID;
* knowledge of a manifest path;
* knowledge of a digest;
* successful validation; or
* a caller-provided purpose string.

Where authorization is required, missing authorization must fail closed.

### Validation boundaries

Core validation establishes only the guarantees explicitly defined by the relevant contract.

A valid record does not necessarily establish that:

* its claims are true;
* the person creating it had appropriate authority;
* referenced evidence may be disclosed;
* an educational judgment is correct;
* a score is a Grade;
* a standards observation establishes proficiency;
* a relationship establishes legal authority; or
* a publication may be consumed by every installed module.

Consumers must preserve producer meaning and apply their own explicitly authorized policy layers rather than deriving unsupported conclusions from Core validation success.

## Sensitive Shared Records

Core-owned and Core-governed records may contain or reference sensitive educational information.

Examples include:

* rosters;
* class membership;
* Academic Work Registrations;
* Publication Records;
* publication-series state;
* producer profiles;
* authorization decisions;
* standards references;
* shared identity relationships;
* workspace configuration;
* grouping-signal contracts;
* integration metadata; and
* manifests or producer records referenced through Core-governed workflows.

Such records must be handled according to their documented authority and privacy boundaries.

Producer manifests and producer-native records remain producer-owned even when Core stores or indexes publication metadata about them.

Do not publicly post production manifestations of these records.

## Paths, Filesystem Safety, and Storage

Core path helpers and persistence utilities may participate in security-sensitive workflows.

Implementations should:

* reject traversal outside intended roots;
* avoid treating string-prefix comparison as filesystem containment;
* avoid silently following unsafe redirection;
* preserve documented workspace ownership boundaries;
* fail safely when canonical paths cannot be established;
* avoid destructive overwrite unless explicitly part of the contract;
* preserve immutable or revisioned history where required;
* avoid exposing sensitive absolute paths in unnecessary user-facing output; and
* treat filesystem state as potentially changing between validation and mutation.

A valid path does not itself establish permission to read or modify the referenced data.

## Integrity, Digests, and Verification

SHA-256 and similar cryptographic hashes may be used by Core and other Paper Data Suite components to verify byte identity and detect changes.

A matching digest provides evidence that bytes agree with the expected digest.

It does not provide:

* encryption;
* confidentiality;
* access control;
* proof of legal authorization;
* proof of authorship;
* proof that the source was trustworthy;
* proof that a record is educationally correct; or
* a digital signature unless an explicitly documented signed-verification scheme is used.

Security-sensitive code must not describe ordinary hash verification as stronger assurance than it provides.

## Backups and External Storage

Whole-workspace backup and restore are suite-shell responsibilities, but Core owns the workspace authority those operations resolve.

Production workspaces and backups may contain sensitive educational records.

When a workspace or backup is placed in:

* OneDrive;
* Google Drive;
* Dropbox;
* a network share;
* removable media;
* institutionally managed cloud storage; or
* another externally synchronized location,

synchronization, encryption, retention, remote access, account compromise, sharing, and provider-specific recovery behavior belong to that external storage system.

Paper Data Suite does not make an external destination appropriate merely because it is technically writable.

Use only teacher-controlled or institutionally approved storage appropriate for the data involved.

## Dependencies and Release Artifacts

Core dependencies should remain minimal and deliberate.

Security-sensitive dependency changes should be reviewed, tested, and documented when they materially affect supported behavior.

Release artifacts should be produced and distributed through the documented Paper Data Suite release process.

Where published checksums or exact artifact identities are part of the release contract:

* verify the expected artifact;
* fail closed on mismatch;
* do not silently substitute a different package or source checkout; and
* do not treat a broadly compatible dependency range as evidence that an unqualified version has been release-tested.

Source development and supported release artifacts are distinct security and compatibility states.

## Reporting a Vulnerability

Do not disclose sensitive vulnerability details in a public GitHub issue.

For suspected security vulnerabilities, use GitHub Private Vulnerability Reporting for this repository when that workflow is available.

A private report should include only the minimum information needed to reproduce and assess the issue:

* affected Core version, branch, or commit;
* affected component or service;
* concise description;
* reproduction steps;
* expected behavior;
* observed behavior;
* potential impact;
* prerequisites or required permissions;
* suggested mitigation, if known; and
* current disclosure status.

Do not include real student data, production workspace contents, credentials, private school or district material, or unrelated sensitive information in a vulnerability report.

If GitHub Private Vulnerability Reporting is unexpectedly unavailable, do not place exploit details or sensitive information in a public issue. Open only a non-sensitive issue stating that a private security-reporting channel is needed.

## Reporting Non-Sensitive Security or Privacy Concerns

Public GitHub Issues may be used for non-sensitive:

* security-hardening suggestions;
* privacy-design questions;
* documentation gaps;
* synthetic-data concerns;
* dependency-maintenance questions;
* data-safety design issues; and
* reports that contain no exploit-sensitive or private information.

Do not include real student data, credentials, production workspace contents, or sensitive deployment details in public issues.

## Security-Sensitive Areas

Reports are particularly appropriate for demonstrated problems involving:

* path traversal;
* unsafe filesystem containment;
* unintended file overwrite or deletion;
* authorization bypass;
* fail-open behavior where authorization should be required;
* publication or manifest access without required authorization;
* workspace escape;
* unsafe archive handling;
* package or artifact-verification bypass;
* dependency substitution;
* command injection;
* unsafe temporary-file behavior;
* canonical-record integrity violations;
* unintended mutation during import or diagnostic operations;
* privacy-sensitive information appearing in logs or diagnostics;
* accidental exposure of student records;
* record-ownership boundary violations;
* unsafe cross-module writes;
* incorrect digest verification;
* source-checkout shadowing that defeats qualified-package verification; or
* CI or release automation exposing credentials or sensitive data.

## Good-Faith Security Research

Good-faith testing should:

* use synthetic data;
* use environments and data you are authorized to access;
* minimize access to unrelated information;
* stop if real sensitive data is encountered;
* avoid modifying or destroying data unnecessarily;
* avoid disrupting classroom or institutional systems;
* report vulnerabilities privately;
* avoid public disclosure before maintainers have had a reasonable opportunity to investigate and correct the issue; and
* comply with applicable law and organizational policy.

Do not test against systems, accounts, workspaces, or data you do not have permission to access.

This policy does not authorize activity against third-party systems.

## Supported Versions

PDS Core is pre-1.0 and does not provide a long-term-support commitment.

For the current release family:

| Version                           | Status                                                    |
| --------------------------------- | --------------------------------------------------------- |
| `main`                            | Development only; not a supported release artifact        |
| latest released `0.6.x`           | Supported                                                 |
| older superseded `0.6.x` releases | Upgrade recommended; fixes may require the latest `0.6.x` |
| `<=0.5.x`                         | Unsupported                                               |

Security and maintenance fixes target the current supported release line.

A newer released `0.6.x` version may supersede an older patch release.

There is no guaranteed vulnerability-response SLA, maintenance window, or backport period.

Pre-1.0 fixes may require upgrading to the latest supported Core release.

## Scope

This policy applies to the `pds-core` repository, its released package artifacts, and Core-owned shared infrastructure.

It does not make Core responsible for the security implementation of every downstream module.

Each Paper Data Suite module remains responsible for documenting and protecting its own:

* canonical records;
* module-specific workflows;
* exports;
* scans or source artifacts;
* user-facing decisions;
* privacy-sensitive projections;
* retention behavior;
* integration surfaces; and
* domain-specific authorization requirements.

Cross-module behavior must preserve documented Core ownership, validation, authorization, provenance, and compatibility boundaries.

## Compliance

Paper Data Suite is software infrastructure, not a legal determination that a particular deployment satisfies FERPA, state student-privacy law, district policy, records-retention requirements, accessibility requirements, or other institutional obligations.

Teachers, administrators, developers, and deploying organizations remain responsible for determining and following the requirements applicable to their use.

This policy describes repository security intent and supported project practices. It is not legal advice.
