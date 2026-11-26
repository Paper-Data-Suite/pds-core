# Core #244-A — Consolidated release readiness audit

## Source and release identity

Published v0.6.6: tag commit 35af5d0642e84a625cd143285c4ef6de98dbcca4.
Merged #244 start: 12e6f761fb98f9ed7fc053c22f24dcbd1946e8d0.
The latter is eight commits ahead of the release and has the same tree as
qualified #242 PR head 103f0f12ebaf6e5a3bab51b20883375333587e01.
No runtime source or package version changes in this slice.

| Merged addition | Commit | Boundary |
| --- | --- | --- |
| #234 release documentation | bf3e6c0 | Published v0.6.6 history |
| #236 contract | bc9cff9 | Contract v1, distinct from distribution version |
| #237 terminal and parser | a0d5e1a | Additive, explicit opt-in |
| #239 workspace Notes | f5cf26b | New .pds/notes/v1/ collection, no old schema migration |
| #240 Notes menu and CLI | 6221e53 | New public menu/CLI, existing shortcuts retained |
| #249 exact-owner diagnosis | 3ff18cc | Additive public selection API; not authorization |
| #241 guarded roster edits | 3e4ea93 | Existing canonical roster and guarded CLI |
| #242 classroom menu | 12e6f76 | Option 6 and workspace menu, truthful receipts |

Source capability tokens are seven: terminal.header.v1,
terminal.notes_command.v1, notes.records.v1, notes.menu.v1, notes.cli.v1,
classroom.roster_edits.v1, classroom.menu.v1. notes.portability.v1 is
reserved and absent. Existing module-operations v1 is separate.
No deliberate breaking API, existing record migration, new runtime
dependency, Python floor change, or console-script rename identified.
Full installed compatibility evidence is still required.

## Version decision

Recommend **0.6.7**, not 0.7.0. Core is pre-1.0 and all six frozen v3
released-consumer rows declare an upper bound of <0.7. The latest
official released consumer tag source metadata checked 2026-11-25
independently confirms the same bound:

| Consumer | Latest released tag | Core requirement in tag pyproject |
| --- | --- | --- |
| ScoreForm | v0.13.0 | >=0.6.5,<0.7 |
| Quillan | v0.10.6 | >=0.6.5,<0.7 |
| Concord | v0.3.4 | >=0.6.6,<0.7 |
| Meridian | v0.4.3 | >=0.6.5,<0.7 |
| Vitrine | v0.4.0 | >=0.6.6,<0.7 |
| Suite | v0.1.0 | >=0.6.3,<0.7 |

0.7.0 would make these distributions dependency-incompatible even if
all Python APIs worked. 0.6.7 fits these requirements, but does not
automatically qualify an exact installed composition. The v0.1.0 Suite
backup/restore gate pins Core 0.6.3 in its bundled manifest; do not bypass
that admission. Stage C will inspect actual wheel METADATA and pinned
GitHub asset digests, not substitute source observations for wheel proof.
Preserve frozen fixture v1/v2/v3 and historical scripts/release notes.
Create a separately versioned fixture for the new candidate, covering
the existing six-row baseline and current release identities where
supported by the existing qualifier. Record any unsupported producer
surface explicitly, rather than asserting adoption.

## Version-sensitive implementation work for C

- pyproject.toml and pds_core/__init__.py, synchronized release version.
- .github/workflows/ci.yml: exact v066 artifact/installed probes,
  reader and Windows opener expected-version gates, hard-coded wheel
  filename and tracked-version checks, frozen v3 consumer fixture.
- scripts/verify_v066_release_artifacts.py,
  scripts/verify_v066_installed_acceptance.py,
  scripts/write_v066_release_checksums.py: retain historical tooling;
  introduce successor tooling rather than mutate archived evidence.
- scripts/released_consumer_compatibility.py supported candidate versions,
  qualifier fixture and tests; preserve historical pinned identities.
- tests/test_release_metadata.py, test_v065_release_documentation.py,
  test_v066_postrelease_documentation.py, test_v066_release_tooling.py,
  released-consumer qualification/documentation tests and all remaining
  hard-coded current-version references. Differentiate historical facts
  from active candidate/version assertions.
- CHANGELOG and README: published v0.6.6 remains current until actual
  publication; new release notes must remain candidate/pending until
  merged-source and uploaded artifact digests are verified.
- Run Notes #240 isolated wheel smoke, #241 installed edit probe,
  #242 exact wheel/sdist probe, #237 terminal smoke, #249 exact-owner
  installed negative/positive acceptance and legacy consumer regressions.
  Reuse existing gates; no early publish and no producer pin changes.

## Outstanding physical gates

See [Notes sync and backup protocol](issue244_notes_sync_backup_acceptance.md).
Real synchronization, stale/conflict refusal, actual Suite backup/restore
and owner confirmation of real-terminal behavior remain unexecuted in
this slice. No scope expansion to private OS storage or custom sync.
Historical D1/D2 evidence is not a current release attestation.
