# Security Policy

## Project Status

PDS Core is a supported, pre-1.0 shared infrastructure package for Paper Data
Suite. It is local-first, is not a hosted service, and v0.5.0 is not described
as production-stable or permanently API-stable.

## Student Data and Privacy

Do not commit or publicly post:

- real student data;
- real rosters;
- real student IDs;
- scanned student work;
- production classroom records;
- private school or district documents;
- secrets, credentials, tokens, or private configuration.

Repository examples and test data should be synthetic.

Paper Data Suite tools are intended to support local, teacher-controlled
workflows, but users are responsible for following applicable school,
district, state, and federal requirements when handling student information.

## Reporting a Concern

Use GitHub Issues for non-sensitive security, privacy, or data-safety concerns.

Do not include real student data, private school data, credentials, or
sensitive district information in a public issue. For a concern involving
sensitive details, describe the issue generally and request a private
follow-up channel.

## Scope

PDS Core owns shared contracts, validation, path helpers, and infrastructure
utilities. Downstream modules remain responsible for their own workflows,
outputs, and local data handling.

Teachers and other users are responsible for complying with applicable school,
district, state, and federal requirements.

## Supported Versions

Unless otherwise documented, only the latest pre-1.0 minor line receives
security and maintenance fixes.

| Version | Supported |
| --- | --- |
| 0.5.x | Yes |
| < 0.5 | No |

Never post real student data, sensitive school or district information,
credentials, or other private records in a public issue.
