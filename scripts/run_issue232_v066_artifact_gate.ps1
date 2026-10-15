param([string]$Repo = ".")
$ErrorActionPreference = "Stop"
$source = (Resolve-Path -LiteralPath $Repo).ProviderPath
$root = Join-Path $env:TEMP ("core232-v066-candidate-" + [guid]::NewGuid().ToString("N"))
$dist = Join-Path $root "dist"
$venv = Join-Path $root "wheel-venv"
$sdistVenv = Join-Path $root "sdist-venv"
New-Item -ItemType Directory -Path $dist -Force | Out-Null
Push-Location $source
try {
    python -m build --outdir $dist
    if ($LASTEXITCODE -ne 0) { throw "Core #232 distributions build failed." }
    $wheel = Join-Path $dist "pds_core-0.6.6-py3-none-any.whl"
    $sdist = Join-Path $dist "pds_core-0.6.6.tar.gz"
    foreach ($candidate in @($wheel,$sdist)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "Expected release artifact missing: $candidate"
        }
    }
    python .\scripts\verify_v066_release_artifacts.py --wheel $wheel --sdist $sdist
    if ($LASTEXITCODE -ne 0) { throw "Core #232 release artifact verification failed." }
    python .\scripts\write_v066_release_checksums.py --wheel $wheel --sdist $sdist --output (Join-Path $dist "SHA256SUMS.txt")
    if ($LASTEXITCODE -ne 0) { throw "Core #232 checksum generation failed." }

    python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Wheel virtual environment creation failed." }
    $wheelPython = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path $wheelPython)) { $wheelPython = Join-Path $venv "bin/python" }
    & $wheelPython -m pip --isolated install --no-index --no-deps $wheel
    if ($LASTEXITCODE -ne 0) { throw "Wheel installation failed." }
    & $wheelPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "Wheel pip check failed." }
    Push-Location $root
    try {
        & $wheelPython -I (Join-Path $source "scripts\verify_v066_installed_acceptance.py")
        if ($LASTEXITCODE -ne 0) { throw "Core #232 wheel legacy contract acceptance failed." }
        & $wheelPython -I (Join-Path $source "scripts\qualify_issue232_installed_opener.py") --forbidden-root $source
        if ($LASTEXITCODE -ne 0) { throw "Core #232 wheel viewer alias acceptance failed." }
    } finally { Pop-Location }

    python -m venv $sdistVenv
    if ($LASTEXITCODE -ne 0) { throw "Sdist virtual environment creation failed." }
    $sdistPython = Join-Path $sdistVenv "Scripts\python.exe"
    if (-not (Test-Path $sdistPython)) { $sdistPython = Join-Path $sdistVenv "bin/python" }
    & $sdistPython -m pip --isolated install --no-deps $sdist
    if ($LASTEXITCODE -ne 0) { throw "Sdist installation failed." }
    & $sdistPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw "Sdist pip check failed." }
    Push-Location $root
    try {
        & $sdistPython -I (Join-Path $source "scripts\verify_v066_installed_acceptance.py")
        if ($LASTEXITCODE -ne 0) { throw "Core #232 sdist legacy contract acceptance failed." }
    } finally { Pop-Location }

    Write-Host "Core #232 exact wheel/sdist + installed qualification: PASS"
    Write-Host "Release candidate artifacts (not published): $dist"
    Get-Content -LiteralPath (Join-Path $dist "SHA256SUMS.txt")
}
finally { Pop-Location }
