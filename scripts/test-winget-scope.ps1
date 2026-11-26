#requires -Version 5.1
<#
.SYNOPSIS
  Baseline WinGet User/Machine scope test for DBeaver Community.
.DESCRIPTION
  Default mode is read-only. Pass -Install to perform a real installation.
  Run once with -Scope User and once with -Scope Machine. This script does not
  elevate itself, uninstall software, change policy, or modify the application.
  WinGet may display its normal UAC prompt for Machine scope.
#>
[CmdletBinding()]
param(
    [ValidateSet('User', 'Machine')]
    [string]$Scope = 'User',

    [switch]$Install,

    [string]$PackageId = 'DBeaver.DBeaver.Community'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Section([string]$Title) {
    Write-Host ''
    Write-Host ('=' * 72) -ForegroundColor DarkCyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ('=' * 72) -ForegroundColor DarkCyan
}

function Invoke-WinGetCapture {
    param(
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$OutputFile
    )

    Write-Host ('> winget ' + ($Arguments -join ' ')) -ForegroundColor Gray
    $captured = @(& $script:WinGetPath @Arguments 2>&1)
    $nativeExitCode = $LASTEXITCODE
    $captured | ForEach-Object { "$_" } | Set-Content -LiteralPath $OutputFile -Encoding UTF8
    $captured | ForEach-Object { Write-Host "$_" }
    return [pscustomobject]@{
        ExitCode = [int]$nativeExitCode
        Output = @($captured | ForEach-Object { "$_" })
    }
}

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logDirectory = Join-Path $env:TEMP "WinGet-Scope-Test-$timestamp"
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$transcriptPath = Join-Path $logDirectory 'session.txt'
Start-Transcript -Path $transcriptPath -Force | Out-Null

$result = [ordered]@{
    StartedAt = (Get-Date).ToString('o')
    ComputerName = $env:COMPUTERNAME
    UserName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    UserSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    IsAdministrator = ([Security.Principal.WindowsPrincipal]::new(
        [Security.Principal.WindowsIdentity]::GetCurrent()
    )).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    WindowsVersion = [Environment]::OSVersion.Version.ToString()
    PackageId = $PackageId
    RequestedScope = $Scope.ToLowerInvariant()
    InstallRequested = [bool]$Install
    WinGetVersionExitCode = $null
    PackageShowExitCode = $null
    InstallExitCode = $null
    LogDirectory = $logDirectory
}

try {
    Write-Section '1. Windows identity and WinGet availability'
    Write-Host "Computer : $($result.ComputerName)"
    Write-Host "User     : $($result.UserName)"
    Write-Host "SID      : $($result.UserSid)"
    Write-Host "Admin    : $($result.IsAdministrator)"
    Write-Host "OS       : $($result.WindowsVersion)"
    Write-Host "Logs     : $logDirectory"

    $command = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $command) {
        throw 'WinGet command was not found in the current PowerShell command path. Install/update App Installer from Microsoft Store, then retry.'
    }
    # Do not pin a per-user WindowsApps alias path. Packaged-app aliases can
    # resolve to another profile path while the command remains callable here.
    $script:WinGetPath = 'winget.exe'
    Write-Host "WinGet   : $($command.Source)"
    Write-Host 'Invocation: current-session command resolution'

    $version = Invoke-WinGetCapture -Arguments @('--version') -OutputFile (Join-Path $logDirectory 'winget-version.txt')
    $result.WinGetVersionExitCode = $version.ExitCode
    if ($version.ExitCode -ne 0) { throw "winget --version failed with exit code $($version.ExitCode)" }

    Write-Section '2. Verify package and manifest visibility'
    $show = Invoke-WinGetCapture -Arguments @(
        'show', '--id', $PackageId, '--exact', '--source', 'winget',
        '--accept-source-agreements'
    ) -OutputFile (Join-Path $logDirectory 'package-show.txt')
    $result.PackageShowExitCode = $show.ExitCode
    if ($show.ExitCode -ne 0) {
        throw "winget show failed with exit code $($show.ExitCode). Check PackageId/source and inspect package-show.txt."
    }

    Write-Section '3. Scope test'
    if (-not $Install) {
        Write-Host 'READ-ONLY CHECK COMPLETE. No software was installed.'
        Write-Host "To perform the real $Scope installation, rerun with -Install."
    } else {
        Write-Host "About to install $PackageId with explicit --scope $($Scope.ToLowerInvariant())." -ForegroundColor Yellow
        Write-Host 'This changes the machine. No uninstall or rollback will be performed automatically.' -ForegroundColor Yellow
        $confirmation = Read-Host "Type INSTALL-$($Scope.ToUpperInvariant()) to continue"
        if ($confirmation -cne "INSTALL-$($Scope.ToUpperInvariant())") {
            Write-Host 'Cancelled by user. No install command was started.' -ForegroundColor Yellow
            $result.InstallCancelled = $true
        } else {
            $installArgs = @(
                'install', '--id', $PackageId, '--exact', '--source', 'winget',
                '--scope', $Scope.ToLowerInvariant(),
                '--accept-source-agreements', '--accept-package-agreements',
                '--verbose-logs'
            )
            $install = Invoke-WinGetCapture -Arguments $installArgs -OutputFile (Join-Path $logDirectory "install-$($Scope.ToLowerInvariant()).txt")
            $result.InstallExitCode = $install.ExitCode
            if ($install.ExitCode -ne 0) {
                Write-Host "WinGet install returned exit code $($install.ExitCode)." -ForegroundColor Red
            } else {
                Write-Host 'WinGet install command completed with exit code 0.' -ForegroundColor Green
            }
        }
    }
}
catch {
    $result.Error = $_.Exception.Message
    Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
}
finally {
    $result.FinishedAt = (Get-Date).ToString('o')
    $jsonPath = Join-Path $logDirectory 'result.json'
    $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $jsonPath -Encoding UTF8
    Stop-Transcript | Out-Null
    Write-Host ''
    Write-Host "Result JSON : $jsonPath"
    Write-Host "Transcript  : $transcriptPath"
}

if ($result.Contains('Error')) { exit 1 }
if ($Install -and $result.InstallExitCode -ne $null -and $result.InstallExitCode -ne 0) { exit [int]$result.InstallExitCode }
exit 0
