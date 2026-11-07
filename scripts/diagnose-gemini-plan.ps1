<#
.SYNOPSIS
  Runs isolated Gemini structured-output diagnostics.
.DESCRIPTION
  Uses the repository virtual environment and prompts for a Gemini API key
  with hidden input when GEMINI_API_KEY is not already set in this process.
  The key is never written to .env or printed. No agent plan is approved or
  dry-run, and no Windows settings or files are changed.
#>
. (Join-Path $PSScriptRoot '_common.ps1')

$python = Get-VenvPython
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Project virtual environment not found. Run scripts\setup.ps1 first.'
}

$diagnostic = Join-Path $PSScriptRoot 'diagnose-gemini-plan.py'
if (-not (Test-Path -LiteralPath $diagnostic)) {
    throw 'Diagnostic Python script is missing. Pull the latest main branch and retry.'
}

Write-Host ''
Write-Host 'Gemini Structured Plan Diagnostic' -ForegroundColor Cyan
Write-Host 'No plan approval, no dry-run, and no Windows changes.'
Write-Host 'If GEMINI_API_KEY is not set, Python will request it using hidden input.'
Write-Host ''

& $python $diagnostic
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Host ''
    Write-Host 'Diagnostic did not pass. Share the complete sanitized output.' -ForegroundColor Yellow
}
exit $exitCode
