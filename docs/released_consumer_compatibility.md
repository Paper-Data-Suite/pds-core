# Released-consumer compatibility qualification

Core v0.6.3 is an additive release on the existing Core 0.6 compatibility line.
The released-consumer qualification machinery verifies one explicit Core wheel
against exact authenticated released consumers; it does not change the Paper
Data Suite exact release composition and does not publish Core itself.

## Current release sequence

The active release sequence is:

```text
#219
  set tracked Core version to 0.6.3
  build the exact release-preparation candidate wheel
  qualify that exact wheel against released consumers
  merge the release-preparation PR
  rebuild the final wheel from the exact merge commit
  rerun the same qualification against those exact final bytes
  tag and publish v0.6.3 only after all Core release gates pass

pds-paper-data-suite#44
  authenticate the published Core v0.6.3 wheel
  adopt the expanded framework-aware standards contracts
  update the suite's exact compatibility composition
  rerun combined installed-suite acceptance
```

The suite handoff is downstream of Core publication. Core does not modify the
suite compatibility manifest.

## Exact released-consumer matrix

The normative fixture is:

```text
tests/fixtures/released_consumers/v1/manifest.json
```

It pins these exact consumers:

| Consumer | Release | Core requirement | Routing profile | Publication profile |
| --- | --- | --- | --- | --- |
| ScoreForm | 0.10.0 | `pds-core>=0.6,<0.7` | yes | yes |
| Quillan | 0.9.0 | `pds-core>=0.6,<0.7` | yes | yes |
| Concord | 0.2.0 | `pds-core>=0.6,<0.7` | yes | yes |
| Meridian | 0.1.1 | `pds-core>=0.6,<0.7` | no | no |
| Vitrine | 0.2.0 | `pds-core>=0.6,<0.7` | no | no |

Provider absence is not incompatibility. None of these exact released artifacts
is required to implement the optional
`paper_data_suite.module_operations` contract merely because Core defines it.

The fixture records published release identities and authenticated SHA-256
values. ScoreForm, Quillan, Concord, and Vitrine use digests already
authenticated by the suite release-compatibility work; Meridian uses its
authenticated GitHub Release asset digest. Every networked qualification run
cross-checks GitHub release metadata and downloaded bytes against the pinned
identity.

`pds-paper-data-suite` is a development consumer with its own exact release
composition and is deliberately not one of these released-consumer fixtures.
Portia is not a released installable consumer in this matrix.

## Offline fixture validation

Normal pytest validation remains offline.

The fixture loader uses packaging requirement/specifier semantics to prove that
every exact consumer accepts candidate Core `0.6.3`. It also validates:

- the exact five-member matrix;
- normalized exact release versions and tags;
- pinned wheel identities and release download URLs;
- SHA-256 format and digest authority;
- consumer-specific provider expectations; and
- explicit intentional exclusions.

Network access is reserved for the explicit release-artifact qualification
path.

## Candidate-wheel inspection

Before any released consumer is installed beside a candidate, the supplied
wheel independently proves:

```text
distribution == pds-core
version == 0.6.3
Requires-Python == >=3.11
pds_core.__version__ == 0.6.3
pds-core console script == pds_core.cli:main
core console script == pds_core.core_menu:main
no unconditional runtime dependencies
required Core public modules are packaged
starter standards package data is present
```

The exact v0.6.3 release-artifact verifier separately requires the complete
four-resource starter payload and performs the release-specific package-content
gate.

The wheel SHA-256 is computed from the exact supplied bytes. Qualification must
never silently rebuild a different wheel when the caller supplies one.

## Explicit released-artifact qualification

Use:

```powershell
python scripts\qualify_released_consumers.py `
  --core-wheel "<path>\pds_core-0.6.3-py3-none-any.whl" `
  --evidence "<path>\released-consumer-qualification.json"
```

The qualification runner accepts an explicit Core wheel and never rebuilds it.

The runner never resolves `latest`, repository `main`, or an unconstrained
consumer package. For every fixture row it:

1. queries the exact GitHub Release tag;
2. requires exactly one asset with the pinned wheel filename;
3. requires GitHub's `sha256:<hex>` release-asset digest;
4. cross-checks that digest against the pinned fixture identity;
5. downloads the exact release asset and hashes its bytes again;
6. inspects wheel metadata and entry points before installation;
7. creates an independent virtual environment for that consumer;
8. installs the explicit Core candidate wheel and exact consumer wheel;
9. runs `pip check`;
10. imports Core and the consumer outside source checkouts;
11. validates declared provider entry points through
    `pds_core.provider_diagnostics`; and
12. runs the installed consumer console script with `--help` and `--version`.

ScoreForm, Quillan, and Concord are expected to expose valid routing and
publication profiles. Meridian and Vitrine are expected to expose neither.
All five are expected to have no module-operations provider at this exact
release baseline.

One consumer failure does not erase evidence for the others. The runner
continues through the deterministic matrix, records the failed stage for the
affected consumer, and returns a failing overall status if any required
consumer fails.

The normalized evidence contains only:

```text
candidate wheel filename/version/SHA-256
consumer exact release identity
authenticated consumer wheel SHA-256
completed probe names
path-free installed public-contract results
bounded failure stage/message when applicable
overall pass/fail
```

It deliberately excludes temporary virtual-environment paths, usernames, home
directories, credentials, workspace contents, and student data.

### GitHub authentication

Public release qualification does not require a token. When `GITHUB_TOKEN` is
present, the runner uses it only for GitHub API release-metadata requests to
avoid anonymous rate limits. The token is never written to evidence or normal
command output.

## CI boundary

The ordinary validation and package-smoke jobs remain offline with respect to
sibling release artifacts.

The dedicated `released-consumer-compatibility` job uses the normal tracked-version build
for the current `0.6.3` source and passes those exact candidate bytes to:

```text
scripts/qualify_released_consumers.py
```

Its evidence is a CI artifact, not the final release checksum declaration.

After the release-preparation PR is squash-merged, #219 repeats qualification
against the exact wheel rebuilt from that merge commit before tagging.

## Historical #195 provisional v0.6.2 machinery

Issue #195 predated the tracked v0.6.2 version bump. It therefore required a
temporary, explicitly non-release builder that copied the then-`0.6.1` source,
changed version metadata only in the disposable copy, and built a provisional
`0.6.2` compatibility wheel.

That historical path remains:

```text
scripts/build_v062_provisional_candidate.py
```

and the shared compatibility module retains the distinct historical constants
needed to test that behavior:

```text
source version: 0.6.1
provisional target: 0.6.2
```

It is not the current v0.6.3 build path and must not be invoked by active CI.

The historical evidence status remains:

```text
provisional-non-release
```

A historical provisional wheel or its hash is never valid v0.6.3 release
evidence.

## Relationship to v0.6.2 release evidence

Issue #196 used the same explicit-wheel qualification runner against the real
tracked v0.6.2 candidate and final wheel.

The v0.6.2 release notes and `verify_v062_*` scripts remain historical evidence.
They are not rewritten to claim v0.6.3 behavior.

Current #219 release preparation adds separate `verify_v063_*` tooling and
qualifies v0.6.3 from its own tracked source.

## Paper Data Suite handoff

After Core v0.6.3 is published, `pds-paper-data-suite#44` owns exact suite
authentication and adoption.

Core release qualification answers whether the exact released Core consumers
continue to work with v0.6.3 and whether the Core artifact itself matches the
approved release surface.

Suite #44 separately answers whether the exact Paper Data Suite v0.1.0
composition qualifies those published Core bytes and correctly consumes the
expanded framework-aware standards contract.

The Core release should therefore record at minimum:

```text
release source commit
tag v0.6.3
pds_core-0.6.3-py3-none-any.whl
wheel SHA-256
pds_core-0.6.3.tar.gz
sdist SHA-256
```

The suite must independently authenticate the published artifact rather than
trust a local Core candidate hash.
