[CmdletBinding()]
param([string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "preflight.ps1") -RepoRoot $RepoRoot
if ($LASTEXITCODE -ne 0) { throw "Preflight failed." }

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$outDir = Join-Path $RepoRoot "artifacts\P6-609-B2"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$log = Join-Path $outDir "test-storage.log"

Push-Location (Join-Path $RepoRoot 'src\backend')
try {
    & $python -m pytest ../../tests/backend/test_platform_storage.py ../../tests/backend/test_job_store.py -q 2>&1 |
        Tee-Object -FilePath $log
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "B2 storage pytest failed with exit code $code. See $log" }
    Write-Host "Storage acceptance PASS. Log: $log"
}
finally { Pop-Location }
