# Released-consumer compatibility qualification

Core v0.6.2 is an additive release on the existing Core 0.6 compatibility line.
Issue #195 provides reproducible qualification against exact released consumers;
it does not change the Paper Data Suite exact release composition and does not
publish Core v0.6.2.

## Release sequence

The qualification sequence is intentionally split:

```text
#195
  build reusable released-consumer fixtures and qualification tooling
  build a provisional 0.6.2 compatibility wheel from a temporary source copy
  qualify the complete intended v0.6.2 code against exact released consumers

#196
  set the repository/package version to 0.6.2
  build the exact final candidate wheel
  rerun the same released-consumer qualification against that exact wheel
  authenticate the final artifact and complete the release audit

pds-paper-data-suite#38
  authenticate the released Core v0.6.2 artifact
  update the suite's exact compatibility composition
  adopt appropriate new Core shared services
```

A passing #195 provisional candidate is compatibility evidence. It is not the
final Core release artifact and its SHA-256 must not be published as the final
v0.6.2 artifact hash.

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

Provider absence is not incompatibility. None of these released artifacts is
required to implement the new optional `paper_data_suite.module_operations`
contract merely because Core v0.6.2 defines it.

The fixture records published suite-manifest SHA-256 values for ScoreForm,
Quillan, Concord, and Vitrine. Meridian was not part of that suite manifest; its
SHA-256 is pinned from the authoritative GitHub Release asset digest authenticated
during the #195 qualification run. Every future run cross-checks the current
GitHub release metadata and downloaded bytes against these pinned identities.

Each consumer row also records the complete deterministic qualification probe
sequence and its known intentional exclusions. This keeps optional capability
absence explicit rather than inferring it from package presence or from a
passing smoke test.

`pds-paper-data-suite` is a development consumer with its own exact release
composition and is not one of these released-consumer fixtures. Portia is not a
released installable consumer at this baseline.

## Offline fixture validation

The fixture loader uses packaging requirement/specifier semantics to prove that
each exact released consumer accepts candidate Core `0.6.2`. It also validates:

- the exact five-member matrix;
- normalized exact release versions/tags;
- pinned wheel identities and release download URLs;
- SHA-256 format and digest authority;
- consumer-specific provider expectations; and
- the absence of invented module-operations expectations.

Normal `pytest` validation remains offline. Network access is reserved for the
explicit released-artifact qualification path added by #195.

## Historical #195 provisional candidate construction

Use:

```powershell
python scripts/build_v062_provisional_candidate.py `
  --outdir "$env:TEMP\pds-core-195-candidate"
```

The output directory must be outside the Core source tree.

The builder:

1. records the current Core Git commit;
2. computes a deterministic digest over package-relevant source bytes;
3. copies the repository to a temporary build tree;
4. changes only the package/version metadata in that temporary copy from
   `0.6.1` to `0.6.2`;
5. invokes the repository's normal wheel build backend;
6. checks that the real worktree version files are byte-for-byte unchanged;
7. inspects the produced wheel as an installed-artifact candidate; and
8. writes bounded evidence identifying the artifact as
   `provisional-non-release`.

The repository's committed package version remains `0.6.1` throughout #195.
The actual version bump belongs to #196.

After #196 changes tracked package metadata to `0.6.2`, this provisional builder
is historical #195 tooling and must not be used to construct the release
candidate. #196 uses the repository's normal tracked-version build path.

The provisional evidence records only:

```text
source commit
source runtime-tree SHA-256
source package version
effective candidate version
wheel filename
wheel SHA-256
provisional/non-release status
```

It does not record usernames, temporary absolute paths, virtual-environment
paths, workspace contents, or student data.

## Candidate-wheel inspection

Before any released consumer is installed beside a candidate, the candidate
wheel must independently prove:

```text
distribution == pds-core
version == 0.6.2
Requires-Python == >=3.11
pds_core.__version__ == 0.6.2
pds-core console script == pds_core.cli:main
core console script == pds_core.core_menu:main
```

The wheel SHA-256 is computed from the exact supplied bytes. Qualification must
never silently rebuild a different wheel when the caller supplies one.

## Explicit released-artifact qualification

Normal Core tests remain independent of GitHub and sibling repositories. The
networked qualification path is explicit:

```powershell
python scripts/qualify_released_consumers.py `
  --core-wheel "$env:TEMP\pds-core-195-candidate\pds_core-0.6.2-py3-none-any.whl" `
  --evidence "$env:TEMP\pds-core-195-candidate\released-consumer-qualification.json"
```

The runner never resolves `latest`, repository `main`, or an unconstrained
consumer package. For every fixture row it:

1. queries the exact GitHub Release tag;
2. requires exactly one asset with the pinned wheel filename;
3. requires GitHub's `sha256:<hex>` release-asset digest;
4. cross-checks that digest against a fixture SHA-256 when one is already
   authenticated by the suite compatibility manifest;
5. downloads the exact release asset and hashes its bytes again;
6. inspects wheel metadata and entry points before installation;
7. creates a separate virtual environment for that consumer;
8. installs the explicit Core candidate wheel and exact consumer wheel;
9. runs `pip check`;
10. imports Core and the consumer outside source checkouts;
11. validates the consumer's declared Core provider entry points through
    `pds_core.provider_diagnostics`; and
12. runs the installed consumer console script with `--help` and `--version`.

ScoreForm, Quillan, and Concord are expected to expose valid routing and
publication profiles. Meridian and Vitrine are expected to expose neither. All
five released artifacts are expected to have no
`paper_data_suite.module_operations` provider; absence is valid.

One consumer failure does not erase evidence for the others. The runner
continues through the complete deterministic matrix, records the failed stage
for the affected consumer, and returns a failing overall status if any required
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
avoid anonymous rate limits. The token is never written to evidence or command
output.

### CI boundary

The ordinary validation and package-smoke jobs stay offline with respect to
sibling release artifacts. During #195, the dedicated released-consumer job
used the provisional candidate builder. After #196 commits tracked version
`0.6.2`, that job must use the normal tracked-version build (`python -m build
--wheel`) and pass those exact bytes to the same qualification runner. Its
evidence remains a CI artifact, not a release checksum declaration.

## Handoff to #196

The qualification runner accepts an explicit Core wheel and never rebuilds it.
That same command is therefore the required handoff to #196. After #196 commits
the real `0.6.2` package version, its normal tracked-version build supplies the
exact candidate wheel to this qualifier. The qualifier is run once on the
release-preparation branch and again on the exact wheel rebuilt from the merged
release-preparation commit. A passing provisional #195 wheel is not a substitute
for either final-release run.

After Core v0.6.2 is released, `pds-paper-data-suite#38` owns exact suite
authentication/adoption of the released artifact before the suite's 12b
combined installed-suite acceptance.
