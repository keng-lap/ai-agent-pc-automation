<#
.SYNOPSIS
  Focused Phase 4 verification: T-402, T-403, T-404 and API security regression.
  Does not run the full project test suite.
#>

. (Join-Path $PSScriptRoot '_common.ps1')

Set-Location $script:RepoRoot

$venvPython = Get-VenvPython
$frontendDir = Join-Path $script:RepoRoot 'src/frontend'

Write-Host ''
Write-Host '=== Phase 4 Focused Verification ===' -ForegroundColor Cyan

# Preflight
if (-not (Test-Path $venvPython)) {
    throw 'Python virtual environment not found. Run scripts\setup.ps1 first.'
}
if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    throw 'Frontend dependencies not found. Run scripts\setup.ps1 first.'
}

Assert-Command 'npm' 'Install Node.js and npm first.'

$failed = $false

# Backend: T-402, T-403 and security regression
Write-Host ''
Write-Host '[1/3] Backend: T-402 / T-403 / Security' -ForegroundColor Cyan

Push-Location (Join-Path $script:RepoRoot 'src/backend')
try {
    Invoke-Checked $venvPython @(
        '-m', 'pytest', '-q',
        '../../tests/backend/test_tools.py',
        '../../tests/backend/test_chat.py',
        '../../tests/backend/test_security.py'
    )

    Write-Host 'Backend focused tests passed.' -ForegroundColor Green

    Write-Host ''
    Write-Host '[2/3] Backend lint: affected source and tests' -ForegroundColor Cyan

    Invoke-Checked $venvPython @(
        '-m', 'ruff', 'check',
        'agent_backend/tools.py',
        'agent_backend/agent_core.py',
        '../../tests/backend/test_tools.py',
        '../../tests/backend/test_chat.py',
        '../../tests/backend/test_security.py'
    )

    Write-Host 'Backend lint passed.' -ForegroundColor Green
}
finally {
    Pop-Location
}

# Frontend: T-404 Angular unit tests
Write-Host ''
Write-Host '[3/3] Frontend: T-404 Structured Agent Response' -ForegroundColor Cyan

Push-Location $frontendDir
try {
    Invoke-Checked 'npm' @('test', '--', '--watch=false')
    Write-Host 'Frontend tests passed.' -ForegroundColor Green
}
finally {
    Pop-Location
}

Write-Host ''
Write-Host '========================================' -ForegroundColor Green
Write-Host 'PHASE 4 VERIFICATION COMPLETED' -ForegroundColor Green
Write-Host 'All selected checks passed.' -ForegroundColor Green
