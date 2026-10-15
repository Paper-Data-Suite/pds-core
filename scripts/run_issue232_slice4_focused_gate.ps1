param([string]$Repo = ".")
$ErrorActionPreference = "Stop"
Push-Location $Repo
try {
    python -m pytest -q tests/test_local_open.py tests/test_issue232_windows_viewer_alias.py
    if ($LASTEXITCODE -ne 0) { throw "Core #232 Slice 4 focused pytest failed." }

    python -m ruff check `
        pds_core/local_open.py `
        scripts/qualify_issue232_installed_opener.py `
        scripts/verify_v066_release_artifacts.py `
        scripts/verify_v066_installed_acceptance.py `
        scripts/write_v066_release_checksums.py
    if ($LASTEXITCODE -ne 0) { throw "Core #232 Slice 4 Ruff failed." }

    python -m mypy --strict `
        pds_core/local_open.py `
        scripts/qualify_issue232_installed_opener.py `
        scripts/verify_v066_release_artifacts.py `
        scripts/verify_v066_installed_acceptance.py `
        scripts/write_v066_release_checksums.py
    if ($LASTEXITCODE -ne 0) { throw "Core #232 Slice 4 MyPy failed." }

    git diff --check
    if ($LASTEXITCODE -ne 0) { throw "Core #232 Slice 4 Git diff check failed." }

    Write-Host "Core #232 Slice 4 release-preparation focused gate: PASS"
}
finally { Pop-Location }
