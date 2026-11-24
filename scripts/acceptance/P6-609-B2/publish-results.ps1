[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ResultFile,
    [Parameter(Mandatory=$true)][ValidateSet("Storage","Security")][string]$SuiteName,
    [Parameter(Mandatory=$true)][int]$ExitCode,
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
)

$ErrorActionPreference = "Stop"
# Git writes normal progress/status messages to stderr. In PowerShell 7.3+,
# prevent native stderr from becoming a terminating PowerShell error;
# every Git operation below is checked explicitly through $LASTEXITCODE.
$PSNativeCommandUseErrorActionPreference = $false
$resultsBranch = "acceptance-results/P6-609-B2"
$remote = "origin"
$sourceCommit = (& git -C $RepoRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "Cannot determine tested source commit." }
if (-not (Test-Path $ResultFile)) { throw "Test output file not found: $ResultFile" }

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmssfff")
$runId = "$stamp-$SuiteName"
$worktree = Join-Path ([System.IO.Path]::GetTempPath()) ("ai-agent-acceptance-" + [guid]::NewGuid().ToString("N"))
$null = & git -C $RepoRoot worktree add --detach $worktree $sourceCommit 2>&1
if ($LASTEXITCODE -ne 0) { throw "Could not create temporary Git worktree for publishing results." }

try {
    & git -C $worktree fetch $remote "refs/heads/$resultsBranch"
    if ($LASTEXITCODE -ne 0) { throw "Could not fetch results branch '$resultsBranch'; no log was pushed." }
    & git -C $worktree switch --force-create $resultsBranch "FETCH_HEAD"
    if ($LASTEXITCODE -ne 0) { throw "Could not switch temporary worktree to results branch." }

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

    & git -C $worktree add "acceptance-results/P6-609-B2/$runId"
    if ($LASTEXITCODE -ne 0) { throw "Git could not stage acceptance results." }
    & git -C $worktree -c user.name="Acceptance Reporter" -c user.email="acceptance-reporter@users.noreply.github.com" commit -m "test: record $SuiteName acceptance $status"
    if ($LASTEXITCODE -ne 0) { throw "Git could not commit acceptance results." }
    & git -C $worktree push $remote "HEAD:refs/heads/$resultsBranch"
    if ($LASTEXITCODE -ne 0) { throw "Git push failed; acceptance result remains local and was not uploaded." }

    Write-Host "LOG PUSHED: https://github.com/keng-lap/ai-agent-pc-automation/tree/$resultsBranch/acceptance-results/P6-609-B2/$runId"
}
finally {
    & git -C $RepoRoot worktree remove --force $worktree 2>$null
    & git -C $RepoRoot worktree prune
}
