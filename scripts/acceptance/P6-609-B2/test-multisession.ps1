[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet("Hold","Probe","VerifyReleased")][string]$Mode,
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path,
    [string]$DatabasePath = (Join-Path $env:LOCALAPPDATA "AI-Agent-PC-Automation\B2-Acceptance\jobs.sqlite3"),
    [int]$HoldSeconds = 90
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "preflight.ps1") -RepoRoot $RepoRoot
if ($LASTEXITCODE -ne 0) { throw "Preflight failed." }

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$helper = Join-Path $PSScriptRoot "windows_b2_mutex_probe.py"
$outDir = Join-Path $RepoRoot "artifacts\P6-609-B2"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$log = Join-Path $outDir ("multisession-" + $(if ($Mode -eq "VerifyReleased") { "verify" } else { $Mode.ToLowerInvariant() }) + ".log")

if (-not [System.IO.Path]::IsPathRooted($DatabasePath)) { throw "DatabasePath must be absolute." }
if ($Mode -eq "Hold") {
    Write-Host "SESSION A: Keep this window open. Switch to a second Windows logon session for the Probe command."
    Write-Host "Use the exact same repository path and DatabasePath in session B."
}

Push-Location $RepoRoot
try {
    $env:PYTHONPATH = (Join-Path $RepoRoot "src\backend")
    & $python $helper $(if ($Mode -eq "VerifyReleased") { "verify" } else { $Mode.ToLowerInvariant() }) --database $DatabasePath --hold-seconds $HoldSeconds 2>&1 |
        Tee-Object -FilePath $log
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "Cross-session $Mode probe failed with exit code $code. See $log" }
    Write-Host "Cross-session $Mode probe PASS. Log: $log"
}
finally {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Pop-Location
}
