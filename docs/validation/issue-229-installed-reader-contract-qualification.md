# Core #229 — Installed reader-contract qualification

Core #229 introduces metadata-only reader contracts that Meridian #111 and Vitrine #103 can use independently of exact producer package versions. Portia #66 must be able to use the same contract for future `intervention_record_set` publications with **no Academic Work Registration**.

## A. Focused wheel smoke for the new public API

Build an explicit **pre-release development candidate** wheel from the current Core checkout. The version in `pyproject.toml` may still be `0.6.4`; this does not make the candidate the historical published Core 0.6.4 release. The candidate identity is its exact filename and SHA-256, not its version alone.

From the Core checkout:

```powershell
python -m build --wheel --no-isolation

$wheel = (Get-ChildItem .\dist\pds_core-*.whl | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

python scripts\qualify_issue229_reader_metadata_wheel.py `
  --core-wheel $wheel `
  --evidence "$HOME\Downloads\core-issue229-reader-qualification.json"
```

Use a clean `dist` directory or explicitly name the intended freshly built wheel when several are present. The script refuses to overwrite existing evidence.

The qualifier:

1. validates a local pds-core wheel and computes its exact SHA-256;
2. creates a disposable Python venv with no system site-packages;
3. installs **only that wheel**, offline, with `--no-deps`;
4. runs `pip check`;
5. invokes its public API probe under `python -I` from outside the checkout;
6. checks exact manifest-bound reader lookup, absence/legacy behavior, profile registration, and compatibility invariance;
7. exercises a **synthetic Portia-shaped intervention publication** without Academic Work Registration;
8. records deterministic, path-free JSON evidence labeled `pre_release_development_candidate`.

The synthetic profiles are *not* proof that ScoreForm, Quillan, Concord, or Portia have released reader-metadata declarations. The probe neither reads producer manifests nor executes producer readers.

## B. Separate released-consumer matrix

The existing `scripts/qualify_released_consumers.py` authenticates published consumer wheels and runs isolated installed probes. **That complete matrix remains a separate acceptance gate**. The existing v0.6.4 fixture (`tests/fixtures/released_consumers/v1/manifest.json`) explicitly identifies historical Core 0.6.4; do not rewrite it merely to make a Core #229 candidate pass.

At final release qualification, establish a *new* candidate-appropriate consumer matrix, based on **currently published**, authenticated producer and consumer artifacts; exercise exact legacy publication producer profiles, Core-facing providers, and relevant CLI surfaces. Include released Portia if it is available and compatible at that qualification point; otherwise qualify Portia's current Core-facing integration as development evidence and label it accurately. Preserve historical 0.6.4 evidence.

The broader qualification must account for the actual released ScoreForm, Quillan, Concord, Meridian, Vitrine, and Portia versions; it must not claim old versions are latest merely because an older fixture lists them. A changed candidate version must not be run against an unchanged fixture that hardcodes 0.6.4.

## C. Release boundary

Completing the development-wheel smoke is **not** release approval. Before a Core release, run complete pytest, Ruff, strict mypy, packaging checks, the refreshed authenticated released-consumer matrix, Portia compatibility as applicable, and independent verification of final wheel/sdist assets. Rebuild from the exact eventual merge commit and record the final tag, commit, wheel name, and SHA-256.

Neither a Core version bump nor a GitHub release is performed by the new scripts.
