$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "==> $Name"
    & $Command

    if ($LASTEXITCODE -ne 0) {
        $exitCode = $LASTEXITCODE
        Write-Host ""
        Write-Host "FAILED: $Name"
        exit $exitCode
    }
}

Invoke-Step "Run pytest" {
    python -m pytest
}

Invoke-Step "Run Ruff" {
    python -m ruff check .
}

Invoke-Step "Run mypy" {
    python -m mypy .
}

Invoke-Step "Check diff whitespace" {
    git diff --check
}

Write-Host ""
Write-Host "All validation checks passed."
