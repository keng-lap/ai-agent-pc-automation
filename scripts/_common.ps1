# Shared helpers for the development scripts. Dot-source this file; do not run it directly.
# Compatible with Windows PowerShell 5.1 and PowerShell 7+.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:RepoRoot = Split-Path -Parent $PSScriptRoot
$script:IsWin = ($env:OS -eq 'Windows_NT')

# Minimum versions
$script:MinPython = [version]'3.11'
# Angular's own Node.js requirement: ^22.22.3 || ^24.15.0 || >=26.0.0
function Test-NodeSupported([version]$v) {
    return (($v.Major -eq 22 -and $v -ge [version]'22.22.3') -or
            ($v.Major -eq 24 -and $v -ge [version]'24.15.0') -or
            ($v.Major -ge 26))
}

function Get-VenvPython {
    if ($script:IsWin) { return (Join-Path $script:RepoRoot '.venv\Scripts\python.exe') }
    return (Join-Path $script:RepoRoot '.venv/bin/python')
}

function Assert-Command([string]$Name, [string]$Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "'$Name' was not found on PATH. $Hint"
    }
}

function Get-VersionFromText([string]$Text) {
    $m = [regex]::Match($Text, '\d+\.\d+(\.\d+)?')
    if (-not $m.Success) { throw "Could not read a version number from: $Text" }
    return [version]$m.Value
}

function Invoke-Checked([string]$FilePath, [string[]]$Arguments) {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $FilePath $($Arguments -join ' ')"
    }
}

function Assert-Toolchain {
    Assert-Command 'python' 'Install Python 3.11 or newer from https://www.python.org/ (tick "Add python.exe to PATH").'
    $py = Get-VersionFromText ((& python --version) 2>&1 | Out-String)
    if ($py -lt $script:MinPython) { throw "Python $py found; Python $($script:MinPython) or newer is required." }

    Assert-Command 'node' 'Install an LTS release of Node.js from https://nodejs.org/.'
    Assert-Command 'npm' 'npm ships with Node.js.'
    $node = Get-VersionFromText ((& node --version) 2>&1 | Out-String)
    if (-not (Test-NodeSupported $node)) {
        throw "Node.js $node found; the Angular CLI needs ^22.22.3, ^24.15.0 or >=26.0.0."
    }
    Write-Host "Python $py, Node.js $node" -ForegroundColor DarkGray
}

# Loads KEY=VALUE lines into the current process environment.
# Variables that are already set in the environment are not overwritten.
function Import-DotEnv([string]$Path) {
    foreach ($line in Get-Content -LiteralPath $Path) {
        $t = $line.Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        $i = $t.IndexOf('=')
        if ($i -lt 1) { continue }
        $key = $t.Substring(0, $i).Trim()
        $val = $t.Substring($i + 1).Trim().Trim('"').Trim("'")
        if (-not [Environment]::GetEnvironmentVariable($key, 'Process')) {
            [Environment]::SetEnvironmentVariable($key, $val, 'Process')
        }
    }
}

function Get-EnvOrDefault([string]$Name, [string]$Default) {
    $v = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ([string]::IsNullOrWhiteSpace($v)) { return $Default }
    return $v
}
