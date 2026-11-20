[CmdletBinding()]
param([string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "preflight.ps1") -RepoRoot $RepoRoot
if ($LASTEXITCODE -ne 0) { throw "Preflight failed." }

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$outDir = Join-Path $RepoRoot "artifacts\P6-609-B2"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$log = Join-Path $outDir "test-security.log"

Push-Location $RepoRoot
try {
    & $python -m pytest tests/backend/test_platform_storage.py -q -k "windows" 2>&1 |
        Tee-Object -FilePath $log
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "B2 Windows security regressions failed with exit code $code. See $log" }
    Write-Host "Windows security regression suite PASS. Log: $log"
}
finally { Pop-Location }
