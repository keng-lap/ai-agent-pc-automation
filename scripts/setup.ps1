<#
.SYNOPSIS
  One-time setup of the local development environment (Phase 1).
.DESCRIPTION
  Checks the toolchain, creates .env from .env.example, creates the Python
  virtual environment (.venv), installs backend and frontend dependencies.
  Safe to run again.
#>
. (Join-Path $PSScriptRoot '_common.ps1')

Assert-Toolchain
Set-Location $script:RepoRoot

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host 'Created .env from .env.example' -ForegroundColor Green
}

# Create a per-installation secret for the local Agent API. Keep it in .env only.
$envLines = Get-Content -LiteralPath '.env'
$tokenLine = $envLines | Where-Object { $_ -match '^LOCAL_AGENT_TOKEN=' } | Select-Object -First 1
$tokenValue = if ($tokenLine) { $tokenLine.Substring('LOCAL_AGENT_TOKEN='.Length) } else { '' }
if ($tokenValue -notmatch '^[0-9a-f]{64}
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $token = [BitConverter]::ToString($bytes).Replace("-", "").ToLowerInvariant()
    if ($tokenLine) {
        $envLines = $envLines | ForEach-Object {
            if ($_ -match '^LOCAL_AGENT_TOKEN=') { "LOCAL_AGENT_TOKEN=$token" } else { $_ }
        }
        [System.IO.File]::WriteAllLines((Join-Path $script:RepoRoot '.env'), $envLines, (New-Object System.Text.UTF8Encoding -ArgumentList $false))
    } else {
        Add-Content -LiteralPath '.env' -Value "LOCAL_AGENT_TOKEN=$token"
    }
    Write-Host 'Generated local Agent authorization token in .env' -ForegroundColor Green
}

$venvPython = Get-VenvPython
if (-not (Test-Path $venvPython)) {
    Write-Host 'Creating Python virtual environment (.venv)...'
    Invoke-Checked 'python' @('-m', 'venv', '.venv')
}

Write-Host 'Installing backend dependencies...'
Invoke-Checked $venvPython @('-m', 'pip', 'install', '-e', 'src/backend[dev]')

Write-Host 'Installing frontend dependencies...'
Push-Location 'src/frontend'
try { Invoke-Checked 'npm' @('ci') } finally { Pop-Location }

Write-Host ''
Write-Host 'Setup complete. Next: scripts\dev.ps1 (run) or scripts\test.ps1 (test).' -ForegroundColor Green
) {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $token = [BitConverter]::ToString($bytes).Replace("-", "").ToLowerInvariant()
    if ($tokenLine) {
        $envLines = $envLines | ForEach-Object {
            if ($_ -match '^LOCAL_AGENT_TOKEN=') { "LOCAL_AGENT_TOKEN=$token" } else { $_ }
        }
        [System.IO.File]::WriteAllLines((Join-Path $script:RepoRoot '.env'), $envLines, (New-Object System.Text.UTF8Encoding($false)))
    } else {
        Add-Content -LiteralPath '.env' -Value "LOCAL_AGENT_TOKEN=$token"
    }
    Write-Host 'Generated local Agent authorization token in .env' -ForegroundColor Green
}

$venvPython = Get-VenvPython
if (-not (Test-Path $venvPython)) {
    Write-Host 'Creating Python virtual environment (.venv)...'
    Invoke-Checked 'python' @('-m', 'venv', '.venv')
}

Write-Host 'Installing backend dependencies...'
Invoke-Checked $venvPython @('-m', 'pip', 'install', '-e', 'src/backend[dev]')

Write-Host 'Installing frontend dependencies...'
Push-Location 'src/frontend'
try { Invoke-Checked 'npm' @('ci') } finally { Pop-Location }

Write-Host ''
Write-Host 'Setup complete. Next: scripts\dev.ps1 (run) or scripts\test.ps1 (test).' -ForegroundColor Green
