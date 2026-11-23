[CmdletBinding()]
param([string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path)

$ErrorActionPreference = "Stop"
$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$log = Join-Path ([System.IO.Path]::GetTempPath()) ("P6-609-B2-security-" + [guid]::NewGuid().ToString("N") + ".log")

Push-Location $RepoRoot
try {
    $preflightCode = 0
    try {
        & (Join-Path $PSScriptRoot "preflight.ps1") -RepoRoot $RepoRoot 2>&1 | Tee-Object -FilePath $log
    }
    catch {
        $_ | Out-String | Tee-Object -FilePath $log -Append
        $preflightCode = 1
    }
    if ($preflightCode -ne 0) {
        & (Join-Path $PSScriptRoot "publish-results.ps1") -RepoRoot $RepoRoot -ResultFile $log -SuiteName Security -ExitCode $preflightCode
        throw "Preflight FAIL. The actual error is shown above; check the uploaded Security log."
    }

    Push-Location (Join-Path $RepoRoot 'src\backend')
    try {
        & $python -m pytest ../../tests/backend/test_platform_storage.py -q -k "windows" 2>&1 | Tee-Object -FilePath $log -Append
        $code = $LASTEXITCODE
    }
    finally { Pop-Location }

    & (Join-Path $PSScriptRoot "publish-results.ps1") -RepoRoot $RepoRoot -ResultFile $log -SuiteName Security -ExitCode $code
    if ($code -ne 0) { throw "Windows security regression suite FAIL (pytest exit code $code). See the FAILED test and error above or open the uploaded log." }
    Write-Host "Windows security regression suite PASS."
}
finally {
    if (Test-Path $log) { Remove-Item -LiteralPath $log -Force }
    Pop-Location
}
