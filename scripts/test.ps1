<#
.SYNOPSIS
  Runs backend (pytest + ruff) and frontend (Angular unit tests) checks.
#>
. (Join-Path $PSScriptRoot '_common.ps1')

Set-Location $script:RepoRoot
$venvPython = Get-VenvPython
if (-not (Test-Path $venvPython) -or -not (Test-Path 'src/frontend/node_modules')) {
    throw 'Dependencies are not installed. Run scripts\setup.ps1 first.'
}

Write-Host '== Backend: pytest ==' -ForegroundColor Cyan
Push-Location 'src/backend'
try {
    Invoke-Checked $venvPython @('-m', 'pytest', '-q')
    Write-Host '== Backend: ruff ==' -ForegroundColor Cyan
    Invoke-Checked $venvPython @('-m', 'ruff', 'check', '.', '../../tests/backend')
} finally { Pop-Location }

Write-Host '== Frontend: ng test ==' -ForegroundColor Cyan
Push-Location 'src/frontend'
try { Invoke-Checked 'npm' @('test', '--', '--watch=false') } finally { Pop-Location }

Write-Host ''
Write-Host 'All checks passed.' -ForegroundColor Green
