[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
)

$ErrorActionPreference = "Stop"
$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if ($env:OS -ne "Windows_NT") { throw "This acceptance suite requires Windows." }
if (-not (Test-Path $python)) { throw "Project venv not found at $python. Run scripts\setup.ps1 first." }

$version = [Environment]::OSVersion.Version
if ($version.Build -lt 22000) { throw "Windows 11 is required; detected build $($version.Build)." }

$probe = @'
import json, platform, sys
print(json.dumps({
    "python": sys.version,
    "architecture": platform.architecture()[0],
    "machine": platform.machine(),
    "is_64_bit": sys.maxsize > 2**32,
}))
import pytest, win32api, win32security
print("DEPENDENCIES_OK")
'@
Push-Location $RepoRoot
try {
    $result = & $python -c $probe 2>&1
    if ($LASTEXITCODE -ne 0) { $result | ForEach-Object { Write-Host $_ }; throw "Python/pywin32/pytest preflight failed." }
    $result | ForEach-Object { Write-Host $_ }
    Write-Host "OS: $([Environment]::OSVersion.VersionString)"
    Write-Host "Repo: $RepoRoot"
    Write-Host "Preflight PASS. No storage, installer, or worker execution was started."
}
finally { Pop-Location }
