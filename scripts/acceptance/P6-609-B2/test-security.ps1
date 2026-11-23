[CmdletBinding()]
param([string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..\\..")).Path)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "preflight.ps1") -RepoRoot $RepoRoot
if ($LASTEXITCODE -ne 0) { throw "Preflight failed; see the error above." }

$python = Join-Path $RepoRoot ".venv\\Scripts\\python.exe"

Push-Location (Join-Path $RepoRoot 'src\\backend')
try {
    & $python -m pytest ../../tests/backend/test_platform_storage.py -q -k "windows"
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        throw "Windows security regression suite FAIL (pytest exit code $code). Use the FAILED test and short error shown above for the chat report."
    }
    Write-Host "Windows security regression suite PASS."
}
finally { Pop-Location }
