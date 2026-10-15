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
