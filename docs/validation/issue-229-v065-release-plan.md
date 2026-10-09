# Core #229 — v0.6.5 release qualification plan

**State:** Post-merge release qualification; **not released**. The package version is now set to 0.6.5 on `main` after PR #230. No tag or GitHub Release has been created.

## Release authority and identity

- Chosen version: **Core 0.6.5**, backward compatible with existing Core 0.6 publication contracts.
- Target change: optional manifest-bound public reader declarations, no consumer allowlist, schema migration or manifest interpretation in Core.
- Implementation source: PR #230 was squash-merged to `main` at `03246532a6f35b5561729ad377240b9927217f73`. A subsequent documentation-only merge becomes the newer final release source commit and requires rebuilding its artifacts.
- Feature branch installed-wheel smoke passed for a local Core 0.6.4-labeled development candidate; that SHA-256 is **not** a Core 0.6.5 release hash.
- Only the final exact merge commit, final versioned wheel, source distribution, checksums, authenticated released consumers and passing CI can qualify a released Core 0.6.5 artifact.

## Preserve Core 0.6.4 history

Keep `tests/fixtures/released_consumers/v1/manifest.json`, `docs/releases/v0.6.4.md`, historical #226 release checks and pinned Core 0.6.4 SHA-256 evidence unchanged. The old fixture continues to target Core 0.6.4. Its reference SHA is the reviewed Git blob identity.

The new fixture is **separate**: `tests/fixtures/released_consumers/v2/manifest.json`. `load_compatibility_fixture()` now permits the two specifically reviewed candidate versions. The historical default `EXPECTED_CORE_VERSION` remains 0.6.4; qualification against 0.6.5 must always pass the fixture target explicitly to wheel inspection. No implicit latest-version inference.

## Published released-consumer matrix, verified October 8, 2026

| Consumer | Published wheel to qualify | Producer publication provider |
| --- | --- | --- |
| ScoreForm | `scoreform-0.12.1-py3-none-any.whl` | yes |
| Quillan | `quillan-0.10.5-py3-none-any.whl` | yes |
| Concord | `pds_concord-0.3.0-py3-none-any.whl` | yes |
| Meridian | `pds_meridian-0.3.1-py3-none-any.whl` | no |
| Vitrine | `pds_vitrine-0.3.0-py3-none-any.whl` | no |
| Paper Data Suite shell | `paper_data_suite-0.1.0-py3-none-any.whl` | no |

The matrix pins GitHub release asset SHA-256 digests and package requirements. It is a **frozen qualification snapshot for the Core v0.6.5 release**: it represents the released artifacts selected for this release gate, not a live or continuously updated module-version registry. A subsequent producer or consumer release does **not** require any Core change, fixture refresh, new Core release or new runtime dependency merely because the module version or implementation changes. Core changes only when its own shared contract needs to change or compatibility is genuinely broken; producer/consumer fixes remain owned by those modules.

Core has no runtime dependencies on sibling PDS modules. The isolated released-consumer qualification harness may fetch exact pinned published wheels solely to demonstrate backward compatibility; those wheels are **not** installed or imported by Core during ordinary operation. The matrix must never be used as an allowlist for reader compatibility or execution. Legacy ScoreForm/Quillan/Concord profiles continue to be valid with `reader_support=()`. Meridian/Vitrine do not automatically adopt newly declared reader contracts. Portia #66 is not a published release and is qualified with synthetic intervention profiles.

The existing six-way released-consumer script authenticates exact published GitHub assets before installing and probing each. Do not weaken the authentication or substitute local development wheels for released consumers. The suite shell's managed exact application composition remains suite-owned.

## Remaining post-merge release gates

1. Reconcile the release-candidate documentation on a narrowly scoped follow-up PR and verify all checks on the resulting final `main` commit. PR #230's implementation merge was `03246532a6f35b5561729ad377240b9927217f73`; that SHA alone is not final if another commit is merged.
2. Rebuild a fresh v0.6.5 wheel and source distribution from that final commit; run Twine checks, artifact inspection and checksum generation. Keep post-merge intermediate hashes separate from final release evidence.
3. Qualify both distributions in standalone environments, including the Core #229 installed reader-contract probe and the Core #226 retained-source regression baseline.
4. Re-run the authenticated six-consumer qualification against the explicit frozen `tests/fixtures/released_consumers/v2/manifest.json` fixture. Do not refresh that matrix to follow later sibling releases.
5. Verify repository-wide pytest, Ruff, strict mypy and CI gates against the final commit and confirm the tag does not already exist.
6. Tag the qualified commit `v0.6.5`, attach the exact verified wheel, source distribution and SHA256SUMS file to the GitHub Release, and record release identity, hashes and downstream handoff references before closing #229.

No publication or release creation is performed by this documentation-only reconciliation.
