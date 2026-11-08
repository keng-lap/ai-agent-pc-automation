# P516-01 - Configure and verify local Google OAuth for the single Master User.
# Google Cloud client creation still requires the owner to sign in to Google Cloud.
[CmdletBinding()]
param()

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envPath = Join-Path $repoRoot ".env"
$bootstrapPath = Join-Path $PSScriptRoot "bootstrap-master-user.py"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$bootstrapRedirect = "http://127.0.0.1:8765/auth/google/callback"
$googleConsoleUrl = "https://console.cloud.google.com/auth/clients"

function Get-DotEnvValue {
    param(
        [string[]]$Lines,
        [string]$Name
    )

    $prefix = $Name + "="
    foreach ($line in $Lines) {
        if ($line.StartsWith($prefix, [System.StringComparison]::Ordinal)) {
            return $line.Substring($prefix.Length).Trim().Trim([char[]]@(34, 39))
        }
    }
    return ""
}

function Set-DotEnvValues {
    param(
        [string[]]$Lines,
        [System.Collections.IDictionary]$Values
    )

    $result = New-Object 'System.Collections.Generic.List[string]'
    $seen = @{}

    foreach ($line in $Lines) {
        $matchedName = $null
        foreach ($name in $Values.Keys) {
            if ($line.StartsWith(($name + "="), [System.StringComparison]::Ordinal)) {
                $matchedName = $name
                break
            }
        }

        if ($null -eq $matchedName) {
            $result.Add($line)
        }
        elseif (-not $seen.ContainsKey($matchedName)) {
            $result.Add($matchedName + "=" + [string]$Values[$matchedName])
            $seen[$matchedName] = $true
        }
    }

    foreach ($name in $Values.Keys) {
        if (-not $seen.ContainsKey($name)) {
            $result.Add($name + "=" + [string]$Values[$name])
        }
    }

    return $result.ToArray()
}

function Read-ClientSecret {
    $secureValue = Read-Host "Google OAuth Client Secret (hidden input)" -AsSecureString
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        if ($pointer -ne [IntPtr]::Zero) {
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
        if ($null -ne $secureValue) {
            $secureValue.Dispose()
        }
    }
}

function Write-DotEnvAtomically {
    param(
        [string]$Path,
        [string[]]$Lines
    )

    $fileToken = [Guid]::NewGuid().ToString("N")
    $tempPath = $Path + "." + $fileToken + ".tmp"
    $backupPath = $Path + "." + $fileToken + ".bak"
    $encoding = New-Object System.Text.UTF8Encoding($false)

    try {
        [System.IO.File]::WriteAllLines($tempPath, $Lines, $encoding)
        # Use an explicit backup path for .NET Framework compatibility.
        [System.IO.File]::Replace($tempPath, $Path, $backupPath)
    }
    finally {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force
        }
        if (Test-Path -LiteralPath $backupPath) {
            Remove-Item -LiteralPath $backupPath -Force
        }
    }
}

Write-Host "P516-01 Google OAuth setup - local Windows only" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
    throw "Missing .env. Run .\scripts\setup.ps1 first."
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Missing .venv Python. Run .\scripts\setup.ps1 first."
}
if (-not (Test-Path -LiteralPath $bootstrapPath -PathType Leaf)) {
    throw "Missing bootstrap helper: $bootstrapPath"
}

$lines = @(Get-Content -LiteralPath $envPath)
$localToken = Get-DotEnvValue -Lines $lines -Name "LOCAL_AGENT_TOKEN"
if ($localToken -notmatch '^[0-9a-f]{64}$') {
    throw "LOCAL_AGENT_TOKEN is missing or invalid. Run .\scripts\setup.ps1 first."
}

$clientId = Get-DotEnvValue -Lines $lines -Name "GOOGLE_OIDC_CLIENT_ID"
$clientSecret = Get-DotEnvValue -Lines $lines -Name "GOOGLE_OIDC_CLIENT_SECRET"
$masterSub = Get-DotEnvValue -Lines $lines -Name "MASTER_GOOGLE_SUB"

if (-not [string]::IsNullOrWhiteSpace($clientId) -and
    -not [string]::IsNullOrWhiteSpace($clientSecret)) {
    $reuseAnswer = (Read-Host "Reuse the Google OAuth client already in .env? [Y/n]").Trim()
    if ($reuseAnswer -and $reuseAnswer -notmatch '^(?i:y|yes)$') {
        $clientId = ""
        $clientSecret = ""
    }
}

$backendPort = Get-DotEnvValue -Lines $lines -Name "BACKEND_PORT"
if ([string]::IsNullOrWhiteSpace($backendPort)) {
    $backendPort = "8000"
}
if ($backendPort -notmatch '^\d{1,5}$') {
    throw "BACKEND_PORT in .env must be a valid TCP port."
}
$backendPortNumber = [int]$backendPort
if ($backendPortNumber -lt 1 -or $backendPortNumber -gt 65535) {
    throw "BACKEND_PORT in .env must be between 1 and 65535."
}
$loginRedirect = "http://127.0.0.1:$backendPortNumber/auth/google/callback"

if ([string]::IsNullOrWhiteSpace($clientId) -or
    [string]::IsNullOrWhiteSpace($clientSecret)) {
    Write-Host ""
    Write-Host "Create or open an OAuth Client ID with type Web application." -ForegroundColor Yellow
    Write-Host "Configure the OAuth consent screen and add your Gmail as a test user if the app is in Testing mode."
    Write-Host "Add these exact Authorized redirect URIs:"
    Write-Host ("  " + $loginRedirect)
    Write-Host ("  " + $bootstrapRedirect)
    Start-Process $googleConsoleUrl

    if ([string]::IsNullOrWhiteSpace($clientId)) {
        $clientId = (Read-Host "Google OAuth Client ID").Trim()
    }
    if ([string]::IsNullOrWhiteSpace($clientSecret)) {
        $clientSecret = Read-ClientSecret
    }
}

if ($clientId -notmatch '^[A-Za-z0-9._-]+\.apps\.googleusercontent\.com$') {
    throw "Google OAuth Client ID format is invalid."
}
if ($clientSecret -notmatch '^[A-Za-z0-9._-]{8,512}$') {
    throw "Google OAuth Client Secret is empty or contains unsupported characters."
}

# Pass credentials to the child process. Do not save them before verification.
$env:GOOGLE_OIDC_CLIENT_ID = $clientId
$env:GOOGLE_OIDC_CLIENT_SECRET = $clientSecret
$env:GOOGLE_OIDC_BOOTSTRAP_REDIRECT_URI = $bootstrapRedirect

Write-Host ""
Write-Host "Starting Google sign-in in your browser..."
$bootstrapOutput = & $python $bootstrapPath 2>&1
$bootstrapExitCode = $LASTEXITCODE
$bootstrapText = ($bootstrapOutput | ForEach-Object { [string]$_ }) -join [Environment]::NewLine

if ($bootstrapExitCode -ne 0) {
    foreach ($outputLine in $bootstrapOutput) {
        $safeLine = [string]$outputLine
        if ($safeLine -match '^(Opening Google sign-in|Open this URL manually:|Waiting up to|Google identity verification failed|Master User subject was not obtained|Set GOOGLE_OIDC_CLIENT_ID)') {
            Write-Host $safeLine
        }
    }
    Write-Host "Google verification failed. No .env changes were saved." -ForegroundColor Red
    throw "Master User bootstrap failed (exit $bootstrapExitCode)."
}

$emailMatch = [regex]::Match(
    $bootstrapText,
    '(?m)^Verified Google account:\s*(\S+)\s*$'
)
$subMatch = [regex]::Match(
    $bootstrapText,
    '(?m)^Stable Google sub:\s*(\S+)\s*$'
)
if (-not $emailMatch.Success -or -not $subMatch.Success) {
    throw "Google identity was not returned in the expected format. No .env changes were saved."
}

$verifiedEmail = $emailMatch.Groups[1].Value
$verifiedSub = $subMatch.Groups[1].Value
Write-Host ("Google verified account: " + $verifiedEmail) -ForegroundColor Green

if ($masterSub -and $masterSub -ne $verifiedSub) {
    Write-Host "This account differs from the configured Master User." -ForegroundColor Yellow
    $replaceAnswer = (Read-Host ("Replace the Master User with " + $verifiedEmail + "? Type YES to confirm")).Trim()
    if ($replaceAnswer -ine "YES") {
        throw "Master User was not changed. No .env changes were saved."
    }
}
elseif (-not $masterSub) {
    $confirmAnswer = (Read-Host ("Set " + $verifiedEmail + " as the single Master User? Type YES to confirm")).Trim()
    if ($confirmAnswer -ine "YES") {
        throw "Master User setup was not confirmed. No .env changes were saved."
    }
}

$sessionTtl = Get-DotEnvValue -Lines $lines -Name "APP_SESSION_TTL_SECONDS"
if ($sessionTtl -notmatch '^\d+$') {
    $sessionTtl = "1800"
}
else {
    $sessionTtlNumber = [int]$sessionTtl
    if ($sessionTtlNumber -lt 60 -or $sessionTtlNumber -gt 86400) {
        $sessionTtl = "1800"
    }
}

$authenticatorPath = Get-DotEnvValue -Lines $lines -Name "AUTHENTICATOR_SECRET_PATH"
$settings = @{
    GOOGLE_OIDC_CLIENT_ID = $clientId
    GOOGLE_OIDC_CLIENT_SECRET = $clientSecret
    GOOGLE_OIDC_REDIRECT_URI = $loginRedirect
    MASTER_GOOGLE_SUB = $verifiedSub
    APP_SESSION_TTL_SECONDS = $sessionTtl
    AUTHENTICATOR_SECRET_PATH = $authenticatorPath
}

# Validate the exact values that will be written before changing .env.
$env:GOOGLE_OIDC_REDIRECT_URI = $loginRedirect
$env:MASTER_GOOGLE_SUB = $verifiedSub
$env:APP_SESSION_TTL_SECONDS = $sessionTtl
$env:AUTHENTICATOR_SECRET_PATH = $authenticatorPath
$env:BACKEND_PORT = [string]$backendPortNumber
$env:LOCAL_AGENT_TOKEN = $localToken
$env:PYTHONPATH = Join-Path $repoRoot "src\backend"

$validationScriptPath = Join-Path ([System.IO.Path]::GetTempPath()) ("p516-oauth-validation-" + [Guid]::NewGuid().ToString("N") + ".py")
$validationLines = @(
    'from agent_backend.config import load_settings'
    'settings = load_settings(load_env_file=False)'
    'assert settings.auth_enabled'
    'print("Google OAuth configuration: valid")'
)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
try {
    [System.IO.File]::WriteAllLines($validationScriptPath, $validationLines, $utf8NoBom)
    & $python $validationScriptPath
    $validationExitCode = $LASTEXITCODE
}
finally {
    if (Test-Path -LiteralPath $validationScriptPath) {
        Remove-Item -LiteralPath $validationScriptPath -Force
    }
}
if ($validationExitCode -ne 0) {
    throw "Local configuration validation failed. .env was not changed."
}

$newLines = Set-DotEnvValues -Lines $lines -Values $settings
Write-DotEnvAtomically -Path $envPath -Lines $newLines

$frontendPort = Get-DotEnvValue -Lines $lines -Name "FRONTEND_PORT"
if ([string]::IsNullOrWhiteSpace($frontendPort)) {
    $frontendPort = "4200"
}

Write-Host ""
Write-Host "Google OAuth is configured and the Master User identity was verified." -ForegroundColor Green
Write-Host "Restart the local app:"
Write-Host "  Stop scripts\dev.ps1 with Ctrl+C"
Write-Host "  Run .\scripts\dev.ps1"
Write-Host ("Then open http://127.0.0.1:" + $frontendPort + "/ and select Login with Google.")
Write-Host "No SMS, recovery codes, proxy settings, or Windows actions were added."
