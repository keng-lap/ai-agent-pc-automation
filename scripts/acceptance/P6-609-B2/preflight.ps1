[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..\\..")).Path
)

$ErrorActionPreference = "Stop"
$python = Join-Path $RepoRoot ".venv\\Scripts\\python.exe"

if ($env:OS -ne "Windows_NT") { throw "This acceptance suite requires Windows." }
if (-not (Test-Path $python)) { throw "Project venv not found at $python. Run scripts\\setup.ps1 first." }

$version = [Environment]::OSVersion.Version
if ($version.Build -lt 22000) { throw "Windows 11 is required; detected build $($version.Build)." }
$caption = (Get-CimInstance Win32_OperatingSystem).Caption
if ($caption -notmatch "Windows 11.*Home") { throw "Target acceptance is scoped to Windows 11 Home; detected '$caption'." }

$probe = @'
import json, platform, sys
assert sys.version_info >= (3, 11), "Python 3.11 or newer is required"
assert sys.maxsize > 2**32, "64-bit Python is required for native Windows ABI validation"
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
    $result = $probe | & $python - 2>&1
    $code = $LASTEXITCODE
    $result | ForEach-Object { Write-Host $_ }
    if ($code -ne 0) { throw "Python/pywin32/pytest preflight failed with exit code $code." }
    Write-Host "OS: $caption ($([Environment]::OSVersion.VersionString))"
    Write-Host "Repo: $RepoRoot"
    Write-Host "Preflight PASS. No storage, installer, or worker execution was started."
}
finally { Pop-Location }
