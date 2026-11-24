[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ResultFile,
    [Parameter(Mandatory=$true)][ValidateSet("Storage","Security")][string]$SuiteName,
    [Parameter(Mandatory=$true)][int]$ExitCode,
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
)

$ErrorActionPreference = "Stop"
# Windows PowerShell 5.1 promotes native stderr records to errors when the
# caller uses ErrorActionPreference=Stop. Run Git with Continue locally,
# capture its output, and always validate the native exit code explicitly.
function Invoke-GitChecked {
    param([Parameter(Mandatory=$true)][string[]]$GitArguments)

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& git @GitArguments 2>&1)
        $gitExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($gitExitCode -ne 0) {
        $details = ($output | ForEach-Object { "$_" }) -join [Environment]::NewLine
        throw ("Git command failed (exit " + $gitExitCode + "): git " + ($GitArguments -join " ") + [Environment]::NewLine + $details)
    }
    return $output
}

$resultsBranch = "acceptance-results/P6-609-B2"
$remote = "origin"
$sourceCommit = (Invoke-GitChecked -GitArguments @("-C", $RepoRoot, "rev-parse", "HEAD") | Select-Object -First 1).ToString().Trim()
if (-not (Test-Path $ResultFile)) { throw "Test output file not found: $ResultFile" }

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmssfff")
$runId = "$stamp-$SuiteName"
$worktree = Join-Path ([System.IO.Path]::GetTempPath()) ("ai-agent-acceptance-" + [guid]::NewGuid().ToString("N"))
$null = Invoke-GitChecked -GitArguments @("-C", $RepoRoot, "worktree", "add", "--detach", $worktree, $sourceCommit)

try {
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "fetch", $remote, "refs/heads/$resultsBranch")
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "switch", "--force-create", $resultsBranch, "FETCH_HEAD")

    $target = Join-Path $worktree "acceptance-results\P6-609-B2\$runId"
    New-Item -ItemType Directory -Force -Path $target | Out-Null

    $log = Get-Content -LiteralPath $ResultFile -Raw
    $profile = [regex]::Escape($env:USERPROFILE)
    if ($profile) { $log = [regex]::Replace($log, $profile, "%USERPROFILE%", "IgnoreCase") }
    $log = [regex]::Replace($log, '(?i)(authorization\s*:\s*bearer\s+)[^\s]+', '$1[REDACTED]')
    $log = [regex]::Replace($log, '(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|client[_-]?secret)\s*[:=]\s*)["'']?[^\s"'']+', '$1[REDACTED]')

    Set-Content -LiteralPath (Join-Path $target "$SuiteName.log") -Value $log -Encoding utf8
    $status = if ($ExitCode -eq 0) { "PASS" } else { "FAIL" }
    $summary = @"
# $SuiteName Acceptance

- Result: **$status**
- Exit code: $ExitCode
- Tested source commit: $sourceCommit
- Recorded at (UTC): $((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))

The accompanying log is sanitized for the current user's profile path and common credential patterns. Review before sharing; do not add secrets or personal files.
"@
    Set-Content -LiteralPath (Join-Path $target "SUMMARY.md") -Value $summary -Encoding utf8

    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "add", "acceptance-results/P6-609-B2/$runId")
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "-c", "user.name=Acceptance Reporter", "-c", "user.email=acceptance-reporter@users.noreply.github.com", "commit", "-m", "test: record $SuiteName acceptance $status")
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "push", $remote, "HEAD:refs/heads/$resultsBranch")

    Write-Host "LOG PUSHED: https://github.com/keng-lap/ai-agent-pc-automation/tree/$resultsBranch/acceptance-results/P6-609-B2/$runId"
}
finally {
    & git -C $RepoRoot worktree remove --force $worktree 2>$null
    & git -C $RepoRoot worktree prune
}
