# Released-consumer compatibility qualification

## Active Core v0.6.5 qualification (#229)

The Core v0.6.5 release candidate has merged into `main` through PR #230.
Its frozen release-qualification fixture is
`tests/fixtures/released_consumers/v2/manifest.json`, not the historical
v0.6.4 `v1` fixture. The matrix contains authenticated published wheels for
ScoreForm 0.12.1, Quillan 0.10.5, Concord 0.3.0, Meridian 0.3.1,
Vitrine 0.3.0 and the Paper Data Suite 0.1.0 shell.

The current CI gate supplies the v2 fixture explicitly to the generic
qualifier. For manual qualification of a final v0.6.5 Core wheel:

```powershell
python scripts\qualify_released_consumers.py `
  --core-wheel "<path>\pds_core-0.6.5-py3-none-any.whl" `
  --fixture "tests/fixtures/released_consumers/v2/manifest.json" `
  --evidence "<path>\released-consumer-qualification.json"
```

This is a frozen release-time compatibility check, not a package dependency,
a runtime reader allowlist or a module-release registry. New releases of
sibling modules do not by themselves require a Core update. The exact final
release source commit and artifacts are qualified after documentation merges.

## Historical Core v0.6.4 qualification (#226)

Core v0.6.4 is a backward-compatible patch on the existing Core 0.6
compatibility line. The release gate verifies one explicit Core candidate wheel
against exact authenticated published consumers. Core does not rewrite the Paper
Data Suite shell's exact application composition and does not publish itself.

## Historical #226 release sequence

The active release sequence is:

```text
#226
  build the tracked Core 0.6.4 candidate artifacts
  qualify exact wheel/sdist and installed Core behavior
  authenticate the current published consumer wheels
  qualify Core-facing package/provider/CLI contracts
  characterize retained-source compatibility that is specific to #226
  resolve any real downstream blocker rather than weakening the test
  merge the release-preparation PR
  rebuild from the exact merge commit
  rerun every release gate
  tag and publish v0.6.4 only after all required gates pass
```

The normal tracked-version build is the current release path. Historical #195
provisional machinery remains historical only.

## Historical v0.6.4 released-consumer matrix

The normative fixture is:

```text
tests/fixtures/released_consumers/v1/manifest.json
```

It pins these exact published wheels:

| Consumer | Release | Core requirement | Routing | Publication | Module operations |
| --- | --- | --- | --- | --- | --- |
| ScoreForm | `0.11.0` | `pds-core>=0.6.2,<0.7` | yes | yes | yes |
| Quillan | `0.10.4` | `pds-core>=0.6.2,<0.7` | yes | yes | yes |
| Concord | `0.3.0` | `pds-core>=0.6.3,<0.7` | yes | yes | yes |
| Vitrine | `0.3.0` | `pds-core>=0.6.3,<0.7` | no | no | yes |
| Meridian | `0.2.0` | `pds-core>=0.6.3,<0.7` | no | no | yes |
| Paper Data Suite | `0.1.0` | `pds-core>=0.6.3,<0.7` | no | no | no |

Portia has no published release and is intentionally absent.

Paper Data Suite v0.1.0 is included only as a released Core-facing package
consumer. Its exact managed application composition remains suite-owned. Core
qualification does not rewrite the shell's immutable v0.1.0 composition or
claim that its older module pins have been re-released.

All six wheel SHA-256 values are pinned from GitHub Release asset digests. Every
networked qualification run re-queries the exact tag, verifies the exact wheel
asset name and GitHub `sha256:<hex>` release-asset digest, downloads the wheel,
and hashes the downloaded bytes again.

## Offline fixture validation

Normal pytest remains offline. Fixture validation proves:

- candidate Core identity is exactly `0.6.4`;
- the matrix contains exactly the six consumers above;
- every declared Core requirement admits `0.6.4`;
- wheel distribution/version/tag/download URL are exact;
- SHA-256 values are lowercase and pinned;
- provider presence/absence matches the published entry points; and
- intentional exclusions are explicit where a provider is absent.

## Explicit released-artifact qualification

Use:

```powershell
python scripts\qualify_released_consumers.py `
  --core-wheel "<path>\pds_core-0.6.4-py3-none-any.whl" `
  --evidence "<path>\released-consumer-qualification.json"
```

The qualification runner accepts an explicit Core wheel and never rebuilds it.
The generic runner is `scripts/qualify_released_consumers.py`.

For each exact consumer it authenticates the release asset, inspects metadata
and entry points, installs Core plus that exact wheel in a separate environment,
runs `pip check`, imports outside source checkouts, validates declared providers
through `pds_core.provider_diagnostics`, and runs the installed CLI with
`--help` and `--version`. The standalone installed probe receives the already
inspected candidate Core version explicitly from the qualifier; it does not
carry a second hard-coded Core release version.

One consumer failure does not erase evidence for the others. The runner records
each completed probe and returns failing overall status if any required matrix
row fails.

## Issue #226 Quillan retained-provenance qualification

The generic package/provider matrix is necessary but not sufficient for #226.

Released Quillan 0.10.3 reproduced the historical compatibility defect: fresh
Core 0.6.4 compact provenance passed, while valid Core 0.6.3 long-name retained
provenance was rejected after Quillan reconstructed identity through the current
Core writer. That result remains historical release-blocker evidence.

Released Quillan 0.10.4 fixes the consumer boundary. Persisted historical
`source_scan_id` and retained-source path provenance are authoritative; Quillan
does not require historical identity to be regenerated by the current writer.

The current passing gate therefore requires both:

```text
fresh long-name intake written by Core 0.6.4
-> Quillan 0.10.4 validates the bounded retained event
-> pass

historical long-name intake written by Core 0.6.3
-> Quillan 0.10.4 validates the persisted legacy event without migration
-> pass
```

Qualify the exact published Quillan 0.10.4 wheel with:

```powershell
python scripts\characterize_issue226_quillan_release.py `
  --core-wheel "<path>\pds_core-0.6.4-py3-none-any.whl" `
  --evidence "<path>\issue226-quillan-0.10.4-qualification.json"
```

The script authenticates the exact GitHub Release wheel and fails unless both
fresh and historical provenance pass with `release_blocker=false`. This is the
current passing gate that clears the Quillan blocker for Core #226.

## CI boundary

For the historical Core 0.6.4 release, the `released-consumer-compatibility`
CI job used the v1 six-row fixture and tracked Core 0.6.4 candidate. The
active Core 0.6.5 job uses the v2 fixture and a 0.6.5 candidate instead.

The Quillan retained-provenance qualification remains separate from the generic
matrix because it exercises #226-specific historical behavior. With released
Quillan 0.10.4 it is now a required passing release gate.

## Historical release machinery

Historical #195 used a `provisional-non-release` Core 0.6.2 wheel built by
`scripts/build_v062_provisional_candidate.py`. That path remains testable
historical evidence and is not used by active CI.

Core v0.6.3 used the same explicit-wheel qualification model during #219. The
historical suite handoff was `pds-paper-data-suite#44`. Those references remain
documentation of prior release evidence; they are not the current #226 gate.

## Release evidence boundary

Candidate hashes from a feature branch are not final release hashes. After the
release-preparation PR is merged, Core must rebuild wheel and sdist from the
exact merge commit and rerun installed acceptance, exact current-consumer
qualification, and all issue-specific compatibility gates before publication.
