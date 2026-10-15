# Focused suite first; intentionally NOT the full Core repository validator.
[CmdletBinding()]
param([string] $Repo = '.')
$ErrorActionPreference = 'Stop'
Push-Location $Repo
try {
    python -m pytest -q tests/test_local_open.py tests/test_issue232_windows_viewer_alias.py
    if ($LASTEXITCODE -ne 0) { throw 'Core #232 focused pytest failed.' }
    python -m ruff check pds_core/local_open.py tests/test_local_open.py tests/test_issue232_windows_viewer_alias.py
    if ($LASTEXITCODE -ne 0) { throw 'Core #232 focused Ruff failed.' }
    python -m mypy pds_core/local_open.py
    if ($LASTEXITCODE -ne 0) { throw 'Core #232 focused Mypy failed.' }
    git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'Core #232 diff check failed.' }
    Write-Host 'Core #232 Slice 2 focused gate: PASS'
}
finally { Pop-Location }
