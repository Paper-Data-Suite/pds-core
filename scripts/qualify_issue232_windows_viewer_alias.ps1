# Issue #232: interactive Windows junction viewer characterization.
# This script NEVER writes, moves, or modifies the selected source document.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $TargetPath
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') {
    throw 'This characterization requires Windows.'
}
if (-not $env:LOCALAPPDATA) {
    throw 'LOCALAPPDATA is unavailable; declining to create a viewer alias.'
}

$target = [System.IO.Path]::GetFullPath($TargetPath)
$targetIsFile = Test-Path -LiteralPath $target -PathType Leaf
$targetIsFolder = Test-Path -LiteralPath $target -PathType Container
if (-not ($targetIsFile -or $targetIsFolder)) {
    throw 'The selected file or folder does not exist.'
}

$root = Join-Path $env:LOCALAPPDATA 'PaperDataSuite\issue232-junction-probe'
New-Item -ItemType Directory -Path $root -Force | Out-Null
$probeId = [guid]::NewGuid().ToString('N')
$link = Join-Path $root ("a_$($probeId.Substring(0, 12))")
$parent = if ($targetIsFile) {
    [System.IO.Path]::GetDirectoryName($target)
} else {
    $target
}

$madeJunction = $false
$canCleanup = $false
$before = $null
$after = $null
$alias = $null
$viewerAnswer = 'not-checked'
try {
    # Avoid powershell/cmd command-string interpolation of the teacher's path.
    New-Item -ItemType Junction -Path $link -Target $parent | Out-Null
    $madeJunction = $true

    $alias = if ($targetIsFile) {
        Join-Path $link ([System.IO.Path]::GetFileName($target))
    } else {
        $link
    }

    if (-not (Test-Path -LiteralPath $alias)) {
        throw 'Created junction does not resolve to the expected target.'
    }
    if ($targetIsFile) {
        $before = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
        $aliasHash = (Get-FileHash -LiteralPath $alias -Algorithm SHA256).Hash
        if ($before -ne $aliasHash) {
            throw 'Junction alias content does not match the source document.'
        }
    }

    Write-Host ''
    Write-Host 'ISSUE #232 WINDOWS VIEWER HANDOFF CHARACTERIZATION'
    [pscustomobject]@{
        TargetKind = if ($targetIsFile) { 'file' } else { 'folder' }
        CanonicalPathLength = $target.Length
        AliasPathLength = $alias.Length
        SameSourceBytes = if ($targetIsFile) { $true } else { 'not-applicable' }
        AliasAccessible = $true
    } | Format-List | Out-Host

    if ($alias.Length -ge $target.Length) {
        throw 'The alias failed to shorten the target path.'
    }
    Write-Host 'Opening the alias through the normal Windows default application ...'
    Invoke-Item -LiteralPath $alias
    Write-Host ''
    Write-Host 'Inspect the viewer, then CLOSE THE VIEWER TAB/WINDOW USING THIS ALIAS.'
    $viewerAnswer = Read-Host 'Did the actual document/folder become accessible? (Y/N)'
    $canCleanup = $true

    if ($targetIsFile) {
        $after = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
        if ($before -ne $after) {
            throw 'Source document hash changed during characterization. Inspect it.'
        }
    }

    [pscustomobject]@{
        Result = if ($viewerAnswer.Trim().ToUpperInvariant() -eq 'Y') {
            'VIEWER-ACCESSIBLE'
        } else {
            'NOT-CONFIRMED'
        }
        CanonicalPathLength = $target.Length
        AliasPathLength = $alias.Length
        CanonicalBytesUnchanged = if ($targetIsFile) { $before -eq $after } else { 'not-applicable' }
        ViewerConfirmation = $viewerAnswer
    } | Format-List | Out-Host
}
finally {
    # Junction must be removed as a link only, never by recursive deletion.
    # If launch confirmation was interrupted, leave the junction alive rather
    # than invalidating a viewer still opening the file; report manual recovery.
    if ($madeJunction -and $canCleanup) {
        try {
            [System.IO.Directory]::Delete($link)
            Write-Host 'Temporary junction removed; authoritative source untouched.'
        } catch {
            Write-Warning 'Could not remove the temporary junction. Do not recursively delete its target.'
        }
    } elseif ($madeJunction) {
        Write-Warning "Viewer may still be using a temporary junction under $root."
        Write-Warning 'Once the viewer closes, delete the junction itself (not its target).'
    }
}
