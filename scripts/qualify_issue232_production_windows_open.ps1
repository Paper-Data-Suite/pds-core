# Real Windows viewer acceptance for Core #232. No authoritative-source writes.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $TargetPath,
    [string] $PythonExe = 'python'
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') {
    throw 'Physical viewer acceptance requires Windows.'
}

$target = [System.IO.Path]::GetFullPath($TargetPath)
$file = Test-Path -LiteralPath $target -PathType Leaf
$directory = Test-Path -LiteralPath $target -PathType Container
if (-not ($file -or $directory)) {
    throw 'Selected file/folder is not present.'
}

$before = if ($file) { (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash } else { $null }

Write-Host ''
Write-Host 'CORE #232 CANDIDATE — REAL WINDOWS VIEWER ACCEPTANCE'
Write-Host "Canonical path length: $($target.Length)"

# Arg passed separately; no interpolation of teacher paths into Python source.
$probe = @'
import importlib.metadata
import sys
from pathlib import Path
from pds_core.local_open import open_local_path
import pds_core.local_open as boundary

canonical = Path(sys.argv[1]).resolve(strict=True)
print("Core distribution:", importlib.metadata.version("pds-core"))
print("Imported opener:", boundary.__file__)
print("Canonical path length:", len(str(canonical)))
opened = open_local_path(canonical)
if opened != canonical:
    raise SystemExit("FAIL: opener returned an alias, not canonical source")
print("Launch request: ACCEPTED (external viewer not yet confirmed)")
'@

$probeFile = Join-Path $env:TEMP (
    "pds-core232-" + [guid]::NewGuid().ToString("N") + ".py"
)

try {
    $repoRoot = (Resolve-Path -LiteralPath (
        Join-Path $PSScriptRoot ".."
    )).ProviderPath

    $marker = 'from pds_core.local_open import open_local_path'
    if (-not $probe.Contains($marker)) {
        throw "Expected Python import marker not found."
    }

    $probe = $probe.Replace(
        $marker,
        "sys.path.insert(0, sys.argv[2])`n$marker"
    )

    [System.IO.File]::WriteAllText(
        $probeFile,
        $probe,
        [System.Text.UTF8Encoding]::new($false)
    )

    & $PythonExe $probeFile $target $repoRoot
}
finally {
    Remove-Item -LiteralPath $probeFile `
        -Force -ErrorAction SilentlyContinue
}
if ($LASTEXITCODE -ne 0) {
    throw 'Core candidate open request failed.'
}

Write-Host ''
$answer = Read-Host 'Did the actual content open correctly in the default viewer? (Y/N)'
$after = if ($file) { (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash } else { $null }
if ($file -and $before -ne $after) {
    throw 'FAIL: authoritative source hash changed; inspect it.'
}

[pscustomobject]@{
    TargetKind = if ($file) { 'file' } else { 'folder' }
    CanonicalPathLength = $target.Length
    ViewerResult = if ($answer.Trim().ToUpperInvariant() -eq 'Y') { 'VIEWER-ACCESSIBLE' } else { 'NOT-CONFIRMED' }
    CanonicalBytesUnchanged = if ($file) { $before -eq $after } else { 'not-applicable' }
} | Format-List | Out-Host

if ($answer.Trim().ToUpperInvariant() -ne 'Y') {
    throw 'Physical viewer acceptance was not confirmed.'
}

Write-Host 'Alias remains available for asynchronous viewer use; stale aliases are pruned later.'
