# Core #229 — v0.6.5 release qualification plan

**State:** Release preparation; **not released**. The Core package remains at 0.6.4 during this slice. No tag or GitHub Release is created.

## Release authority and identity

- Chosen version: **Core 0.6.5**, backward compatible with existing Core 0.6 publication contracts.
- Target change: optional manifest-bound public reader declarations, no consumer allowlist, schema migration or manifest interpretation in Core.
- Source: `229-producer-reader-contract-metadata`, with final SHA established after all release-preparation commits and subsequent merge.
- Feature branch installed-wheel smoke passed for a local Core 0.6.4-labeled development candidate; that SHA-256 is **not** a Core 0.6.5 release hash.
- Only the exact merge commit, final versioned wheel, source distribution, checksums, authenticated released consumers and passing CI can qualify a released Core 0.6.5 artifact.

## Preserve Core 0.6.4 history

Keep `tests/fixtures/released_consumers/v1/manifest.json`, `docs/releases/v0.6.4.md`, historical #226 release checks and pinned Core 0.6.4 SHA-256 evidence unchanged. The old fixture continues to target Core 0.6.4. Its reference SHA is the reviewed Git blob identity.

The new fixture is **separate**: `tests/fixtures/released_consumers/v2/manifest.json`. `load_compatibility_fixture()` now permits the two specifically reviewed candidate versions. The default `EXPECTED_CORE_VERSION` stays 0.6.4 while historical tests depend on it; qualification against 0.6.5 must always pass the fixture target explicitly to wheel inspection. No implicit latest-version inference.

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

## Remaining gates (future slices)

1. Add separate Core v0.6.5 wheel/sdist artifact inspection and checksum generation, reusing shared behavior where safe without overwriting v0.6.4 release scripts.
2. Add v0.6.5 installed package acceptance, including this ticket's reader metadata and baseline Core v0.6.4 compatibility surfaces.
3. Update release-specific documentation tests, CI package smoke and the released-consumer job so v0.6.5 is the active candidate, while previous v0.6.4 tests become clearly historical rather than requiring the current source version to be 0.6.4.
4. In that final activation slice, update `pyproject.toml` and `pds_core/__init__.py` **together** to 0.6.5, promote `[Unreleased]` notes to a pending v0.6.5 section and update current-release README guidance.
5. Run full pytest, repository-wide Ruff, strict mypy, clean wheel/sdist installs, artifact inspection, issue #229 installed smoke, released-consumer fixture v2 qualification and appropriate Issue #226 retained-provenance regression checks.
6. Merge only after the release-preparation PR passes. **Rebuild and independently requalify from the exact merge commit**, then record commit, `v0.6.5` tag, wheel/sdist SHA-256 and release asset digests before closing #229. Never treat feature-branch hashes as final release hashes.

No publication or release creation is performed by this slice.
