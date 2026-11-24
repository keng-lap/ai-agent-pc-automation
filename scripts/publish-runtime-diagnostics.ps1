[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [ValidateRange(1, 20000)][int]$Limit = 5000,
    [ValidatePattern('^[0-9a-f-]{36}$')][string]$RunId = [guid]::NewGuid().ToString()
)

$ErrorActionPreference = "Stop"
$resultsBranch = "diagnostics/runtime-logs"
$remote = "origin"

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
        $exportOutput = @(& $python $exporter --output $exportFile --limit $Limit 2>&1)
        $exportExitCode = $LASTEXITCODE
    }
    finally {
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

    $target = Join-Path $worktree "runs\$runId"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -LiteralPath $exportFile -Destination (Join-Path $target "events.jsonl")

    $summary = @"
# Runtime Diagnostics Run

- Events: $eventCount
- Source checkout commit: $sourceCommit
- Published at (UTC): $((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))
- Export: sanitized allowlisted fields only; raw local database and request bodies are not included.

"@
    Set-Content -LiteralPath (Join-Path $target "SUMMARY.md") -Value $summary -Encoding utf8

    $relativeRunPath = "runs/$runId"
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "add", "-f", "$relativeRunPath/events.jsonl")
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "add", "$relativeRunPath/SUMMARY.md")
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "-c", "user.name=Diagnostics Reporter", "-c", "user.email=diagnostics-reporter@users.noreply.github.com", "commit", "-m", "diagnostics: publish sanitized runtime run $runId")
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "push", $remote, "HEAD:refs/heads/$resultsBranch")

    Write-Host "LOG PUSHED: https://github.com/keng-lap/ai-agent-pc-automation/tree/$resultsBranch/$relativeRunPath"
}
finally {
    if (Test-Path -LiteralPath $worktree) {
        try {
            $null = Invoke-GitChecked -GitArguments @("-C", $RepoRoot, "worktree", "remove", "--force", $worktree)
            $null = Invoke-GitChecked -GitArguments @("-C", $RepoRoot, "worktree", "prune")
        }
        catch {
            Write-Warning "Could not fully clean the temporary diagnostics worktree."
        }
    }
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
)][string]$RunId = [guid]::NewGuid().ToString()
)

$ErrorActionPreference = "Stop"
$resultsBranch = "diagnostics/runtime-logs"
$remote = "origin"

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

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$exporter = Join-Path $RepoRoot "scripts\export-runtime-diagnostics.py"
if (-not (Test-Path -LiteralPath $python)) { throw "Project Python environment not found. Run scripts\setup.ps1 first." }
if (-not (Test-Path -LiteralPath $exporter)) { throw "Diagnostics exporter not found." }

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmssfff")
$runId = "$stamp-runtime"
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("ai-agent-diagnostics-" + [guid]::NewGuid().ToString("N"))
$exportFile = Join-Path $tempRoot "events.jsonl"
$worktree = Join-Path ([System.IO.Path]::GetTempPath()) ("ai-agent-diagnostics-worktree-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null

try {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $exportOutput = @(& $python $exporter --output $exportFile --limit $Limit 2>&1)
        $exportExitCode = $LASTEXITCODE
    }
    finally {
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

    $target = Join-Path $worktree "runs\$runId"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -LiteralPath $exportFile -Destination (Join-Path $target "events.jsonl")

    $summary = @"
# Runtime Diagnostics Run

- Events: $eventCount
- Source checkout commit: $sourceCommit
- Published at (UTC): $((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))
- Export: sanitized allowlisted fields only; raw local database and request bodies are not included.

"@
    Set-Content -LiteralPath (Join-Path $target "SUMMARY.md") -Value $summary -Encoding utf8

    $relativeRunPath = "runs/$runId"
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "add", "-f", "$relativeRunPath/events.jsonl")
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "add", "$relativeRunPath/SUMMARY.md")
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "-c", "user.name=Diagnostics Reporter", "-c", "user.email=diagnostics-reporter@users.noreply.github.com", "commit", "-m", "diagnostics: publish sanitized runtime run $runId")
    $null = Invoke-GitChecked -GitArguments @("-C", $worktree, "push", $remote, "HEAD:refs/heads/$resultsBranch")

    Write-Host "LOG PUSHED: https://github.com/keng-lap/ai-agent-pc-automation/tree/$resultsBranch/$relativeRunPath"
}
finally {
    if (Test-Path -LiteralPath $worktree) {
        try {
            $null = Invoke-GitChecked -GitArguments @("-C", $RepoRoot, "worktree", "remove", "--force", $worktree)
            $null = Invoke-GitChecked -GitArguments @("-C", $RepoRoot, "worktree", "prune")
        }
        catch {
            Write-Warning "Could not fully clean the temporary diagnostics worktree."
        }
    }
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
