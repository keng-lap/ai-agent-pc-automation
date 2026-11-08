# P516-01 — Install Anthropic Frontend Design skill
# Source is pinned to an immutable upstream commit for reproducible installs.
[CmdletBinding()]
param(
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$skillName = "frontend-design"
$upstreamCommit = "2c5958ecac7cee2b583967a2c4981d0f4a75c579"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$target = Join-Path $repoRoot ".agents/skills/$skillName"
$sourceBase = "https://raw.githubusercontent.com/anthropics/skills/$upstreamCommit/skills/$skillName"
$files = @("SKILL.md", "LICENSE.txt")

if ((Test-Path $target) -and -not $Force) {
    throw "Skill already exists at '$target'. Re-run with -Force only if you intend to replace it."
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("p516-01-" + [guid]::NewGuid().ToString("N"))
$stage = Join-Path $tempRoot $skillName
$backup = Join-Path $tempRoot "previous-skill"

try {
    New-Item -ItemType Directory -Path $stage -Force | Out-Null

    foreach ($file in $files) {
        $uri = "$sourceBase/$file"
        $destination = Join-Path $stage $file
        Write-Host "Downloading $file from pinned Anthropic source..."
        Invoke-WebRequest -Uri $uri -OutFile $destination
        if (-not (Test-Path $destination) -or (Get-Item $destination).Length -eq 0) {
            throw "Download validation failed for $file."
        }
    }

    $skillText = Get-Content (Join-Path $stage "SKILL.md") -Raw
    if ($skillText -notmatch "(?m)^name:\s*frontend-design\s*$") {
        throw "Downloaded SKILL.md does not identify the expected frontend-design skill."
    }
    if ($skillText -notmatch "Frontend Design") {
        throw "Downloaded SKILL.md content validation failed."
    }

    $licenseText = Get-Content (Join-Path $stage "LICENSE.txt") -Raw
    if ($licenseText -notmatch "Apache License") {
        throw "Downloaded license validation failed."
    }

    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null

    if (Test-Path $target) {
        Move-Item -LiteralPath $target -Destination $backup
    }

    try {
        Move-Item -LiteralPath $stage -Destination $target
    }
    catch {
        if (Test-Path $backup) {
            Move-Item -LiteralPath $backup -Destination $target
        }
        throw
    }

    Write-Host ""
    Write-Host "P516-01 completed: Anthropic Frontend Design skill installed."
    Write-Host "Location: $target"
    Write-Host "Upstream commit: $upstreamCommit"
    Write-Host "No npm packages were installed and no application/runtime files were changed."
}
finally {
    if (Test-Path $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
