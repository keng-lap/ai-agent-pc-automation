[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [ValidateRange(1, 20000)][int]$Limit = 5000,
    [string]$RunId = "",
    [Parameter(Mandatory=$true)][string]$SessionId,
    [ValidateRange(1, 365)][int]$RetentionDays = 7
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($RunId)) { $RunId = [guid]::NewGuid().ToString() }
if ($RunId -notmatch '^[0-9a-f-]{36}$') { throw "RunId must be a GUID." }
if ($SessionId -notmatch '^[0-9a-f-]{36}$') { throw "SessionId must be a capture session GUID." }

$resultsBranch = "diagnostics/runtime-logs"
$remote = "origin"

function Invoke-GitChecked {
    param([Parameter(Mandatory=$true)][string[]]$GitArguments)
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = @(& git @GitArguments 2>&1)
        $gitExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($gitExitCode -ne 0) {
        $details = ($output | ForEach-Object { "$_" }) -join [Environment]::NewLine
        throw ("Git command failed (exit " + $gitExitCode + "): git " + ($GitArguments -join " ") + [Environment]::NewLine + $details)
    }
    return $output
}

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$exporter = Join-Path $RepoRoot "scripts\export-runtime-diagnostics.py"
if (-not (Test-Path -LiteralPath $python)) { throw "Project Python environment not found. Run scripts\setup.ps1 first." }
if (-not (Test-Path -LiteralPath $exporter)) { throw "Diagnostics exporter not found." }

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("ai-agent-diagnostics-" + [guid]::NewGuid().ToString("N"))
$exportFile = Join-Path $tempRoot "events.jsonl"
$worktree = Join-Path ([System.IO.Path]::GetTempPath()) ("ai-agent-diagnostics-worktree-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null

try {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $exportOutput = @(& $python $exporter --output $exportFile --limit $Limit --session-id $SessionId 2>&1)
        $exportExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exportExitCode -ne 0) {
        $details = ($exportOutput | ForEach-Object { "$_" }) -join [Environment]::NewLine
        throw ("Diagnostics export failed (exit " + $exportExitCode + "). " + $details)
    }

    $sourceCommit = (Invoke-GitChecked -GitArguments @("-C", $RepoRoot, "rev-parse", "HEAD") | Select-Object -First 1).ToString().Trim()
    $eventCount = @(Get-Content -LiteralPath $exportFile).Count
    if ($eventCount -lt 1) { throw "No diagnostic events are available to publish." }

    $null = Invoke-GitChecked -GitArguments @("-C", $RepoRoot, "worktree", "add", "--detach", $worktree, $sourceCommit)
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "fetch", $remote, "refs/heads/$resultsBranch")
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "switch", "--force-create", $resultsBranch, "FETCH_HEAD")

    # Move published bundles older than RetentionDays to archive/runs; do not delete them.
    $cutoff = (Get-Date).ToUniversalTime().AddDays(-$RetentionDays)
    $runsRoot = Join-Path $worktree "runs"
    if (Test-Path -LiteralPath $runsRoot) {
        foreach ($oldRun in Get-ChildItem -LiteralPath $runsRoot -Directory) {
            $oldSummary = Join-Path $oldRun.FullName "SUMMARY.md"
            if (-not (Test-Path -LiteralPath $oldSummary)) { continue }
            $summaryText = Get-Content -LiteralPath $oldSummary -Raw
            if ($summaryText -match '(?m)^- Published at \(UTC\): (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$') {
                $publishedAt = [DateTime]::ParseExact($Matches[1], "yyyy-MM-ddTHH:mm:ssZ", [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal)
                if ($publishedAt.ToUniversalTime() -lt $cutoff) {
                    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "mv", "runs/$($oldRun.Name)", "archive/runs/$($oldRun.Name)")
                }
            }
        }
    }

    $target = Join-Path $worktree "runs\$runId"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -LiteralPath $exportFile -Destination (Join-Path $target "events.jsonl")
    $summary = @"
# Runtime Diagnostics Run

- Events: $eventCount
- Source checkout commit: $sourceCommit
- Capture session: $SessionId
- Published at (UTC): $((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))
- Retention: active runs $RetentionDays days; older bundles moved to archive/runs.
- Export: sanitized allowlisted fields only; raw local database and request bodies are not included.

"@
    Set-Content -LiteralPath (Join-Path $target "SUMMARY.md") -Value $summary -Encoding utf8

    $relativeRunPath = "runs/$runId"
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "add", "-A")
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "-c", "user.name=Diagnostics Reporter", "-c", "user.email=diagnostics-reporter@users.noreply.github.com", "commit", "-m", "diagnostics: publish sanitized runtime run $runId")
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "push", $remote, "HEAD:refs/heads/$resultsBranch")
    Write-Host "LOG PUSHED: https://github.com/keng-lap/ai-agent-pc-automation/tree/$resultsBranch/$relativeRunPath"
} finally {
    if (Test-Path -LiteralPath $worktree) {
        try {
            $null = Invoke-GitChecked -GitArguments @("-C", $RepoRoot, "worktree", "remove", "--force", $worktree)
            $null = Invoke-GitChecked -GitArguments @("-C", $RepoRoot, "worktree", "prune")
        } catch {
            Write-Warning "Could not fully clean the temporary diagnostics worktree."
        }
    }
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
}
