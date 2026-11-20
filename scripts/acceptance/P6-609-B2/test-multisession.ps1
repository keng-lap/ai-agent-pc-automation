[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet("Hold","Probe","VerifyReleased")][string]$Mode,
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..\\..")).Path,
    [string]$DatabasePath = (Join-Path $env:LOCALAPPDATA "AI-Agent-PC-Automation\\acceptance\\P6-609-B2\\jobs.sqlite3"),
    [int]$HoldSeconds = 90
)

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "preflight.ps1") -RepoRoot $RepoRoot
if ($LASTEXITCODE -ne 0) { throw "Preflight failed." }

$python = Join-Path $RepoRoot ".venv\\Scripts\\python.exe"
$helper = Join-Path $PSScriptRoot "windows_b2_mutex_probe.py"
$outDir = Join-Path $RepoRoot "artifacts\\P6-609-B2"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$log = Join-Path $outDir ("multisession-" + $(if ($Mode -eq "VerifyReleased") { "verify" } else { $Mode.ToLowerInvariant() }) + ".log")

# This runner provisions ancestors before invoking Python. Require a drive-rooted
# path (for example C:\\Users\\...); IsPathRooted alone also accepts
# root-relative (\\Users\\...) and drive-relative (C:folder) paths.
if ($DatabasePath -notmatch '^[A-Za-z]:\\') {
    throw "DatabasePath must be fully qualified with a drive root (for example C:\\Users\\...)."
}

# The adapter creates the final protected state directory (DatabasePath's
# parent). Its immediate parent and all higher ancestors must already exist
# so the adapter can pin and validate them before creating that directory.
$databaseDirectory = Split-Path -Parent $DatabasePath
$requiredAncestor = Split-Path -Parent $databaseDirectory
if ([string]::IsNullOrWhiteSpace($databaseDirectory) -or [string]::IsNullOrWhiteSpace($requiredAncestor)) {
    throw "DatabasePath must include a dedicated state directory beneath an existing parent."
}

# Find the first existing ancestor, then reject reparse points/non-directories
# throughout the existing chain before creating any missing intermediate path.
$missingAncestors = @()
$cursor = $requiredAncestor
while ($cursor -and -not (Test-Path -LiteralPath $cursor)) {
    $missingAncestors += $cursor
    $parent = Split-Path -Parent $cursor
    if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $cursor) { break }
    $cursor = $parent
}
if (-not $cursor -or -not (Test-Path -LiteralPath $cursor)) {
    throw "Could not find an existing ancestor for the acceptance directory."
}

$existingCursor = $cursor
while ($existingCursor) {
    $item = Get-Item -LiteralPath $existingCursor -Force -ErrorAction Stop
    if (-not $item.PSIsContainer -or ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "Acceptance path ancestor is not a regular directory: $existingCursor"
    }
    $parent = Split-Path -Parent $existingCursor
    if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $existingCursor) { break }
    $existingCursor = $parent
}

# Create only missing intermediate ancestors. Do not create DatabasePath's
# parent: WindowsSecureStorage owns creation and validation of that directory.
[array]::Reverse($missingAncestors)
foreach ($directory in $missingAncestors) {
    New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
}
if ($Mode -eq "Hold") {
    Write-Host "SESSION A: Keep this window open. Start the probe in a distinct Windows session for the same user SID."
    Write-Host "Use the exact same repository path and DatabasePath in session B."
    Write-Host "Persistent test files will be created under: $DatabasePath"
}

Push-Location $RepoRoot
try {
    $env:PYTHONPATH = (Join-Path $RepoRoot "src\\backend")
    & $python $helper $(if ($Mode -eq "VerifyReleased") { "verify" } else { $Mode.ToLowerInvariant() }) --database $DatabasePath --hold-seconds $HoldSeconds 2>&1 |
        Tee-Object -FilePath $log
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "Cross-session $Mode probe failed with exit code $code. See $log" }
    Write-Host "Cross-session $Mode probe PASS. Log: $log"
}
finally {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Pop-Location
}
