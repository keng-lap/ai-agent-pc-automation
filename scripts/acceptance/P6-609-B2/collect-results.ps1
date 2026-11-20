[CmdletBinding()]
param([string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path)

$ErrorActionPreference = "Stop"
$outDir = Join-Path $RepoRoot "artifacts\P6-609-B2"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$summary = Join-Path $outDir "environment.txt"

@(
    "Collected: $(Get-Date -Format o)"
    "Computer: $env:COMPUTERNAME"
    "User: $env:USERNAME"
    "OS: $([Environment]::OSVersion.VersionString)"
    "OSVersion: $([Environment]::OSVersion.Version)"
    "PowerShell: $($PSVersionTable.PSVersion)"
    "Repo: $RepoRoot"
    "Git HEAD:"
    (& git -C $RepoRoot rev-parse HEAD 2>&1)
    "Git status:"
    (& git -C $RepoRoot status --short 2>&1)
    "Python:"
    (& (Join-Path $RepoRoot ".venv\Scripts\python.exe") --version 2>&1)
    "Volume:"
    (Get-Volume -DriveLetter ([System.IO.Path]::GetPathRoot($env:LOCALAPPDATA).Substring(0,1)) |
        Select-Object DriveLetter,FileSystem,DriveType,HealthStatus | Format-List | Out-String)
) | Set-Content -Encoding UTF8 $summary

$zip = Join-Path $outDir ("P6-609-B2-evidence-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".zip")
Compress-Archive -Path (Join-Path $outDir "*") -DestinationPath $zip -Force
Write-Host "Evidence summary: $summary"
Write-Host "Evidence archive: $zip"
