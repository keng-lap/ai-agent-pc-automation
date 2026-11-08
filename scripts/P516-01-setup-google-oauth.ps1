# P516-01 — Configure and verify local Google OAuth for the single Master User.
# Google Cloud client creation still requires the owner to sign in to Google Cloud.
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envPath = Join-Path $repoRoot ".env"
$bootstrapPath = Join-Path $PSScriptRoot "bootstrap-master-user.py"
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$bootstrapRedirect = "http://127.0.0.1:8765/auth/google/callback"
$googleConsoleUrl = "https://console.cloud.google.com/auth/clients"

function Get-DotEnvValue([string[]]$Lines, [string]$Name) {
    $prefix = "$Name="
    foreach ($line in $Lines) {
        if ($line.StartsWith($prefix, [StringComparison]::Ordinal)) {
            return $line.Substring($prefix.Length).Trim().Trim('"').Trim("'")
        }
    }
    return ""
}

function Set-DotEnvValues([string[]]$Lines, [System.Collections.IDictionary]$Values) {
    $result = [System.Collections.Generic.List[string]]::new()
    $seen = @{}
    foreach ($line in $Lines) {
        $matched = $false
        foreach ($name in $Values.Keys) {
            if ($line.StartsWith("$name=", [StringComparison]::Ordinal)) {
                if (-not $seen.ContainsKey($name)) {
                    $result.Add("$name=$($Values[$name])")
                    $seen[$name] = $true
                }
                $matched = $true
                break
            }
        }
        if (-not $matched) { $result.Add($line) }
    }
    foreach ($name in $Values.Keys) {
        if (-not $seen.ContainsKey($name)) {
            $result.Add("$name=$($Values[$name])")
        }
    }
    return ,$result.ToArray()
}

function Read-ClientSecret {
    $secure = Read-Host "Paste the Google OAuth Client Secret (input is hidden)" -AsSecureString
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
        if ($null -ne $secure) { $secure.Dispose() }
    }
}

function Write-DotEnvAtomically([string]$Path, [string[]]$Lines) {
    $tempPath = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    $encoding = [System.Text.UTF8Encoding]::new($false)
    try {
        [System.IO.File]::WriteAllLines($tempPath, $Lines, $encoding)
        if (Test-Path -LiteralPath $Path) {
            [System.IO.File]::Replace($tempPath, $Path, $null)
        }
        else {
            Move-Item -LiteralPath $tempPath -Destination $Path
        }
    }
    finally {
        if (Test-Path -LiteralPath $tempPath) {
            Remove-Item -LiteralPath $tempPath -Force
        }
    }
}

Write-Host "P516-01 Google OAuth setup — local Windows only" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Missing .env. Run .\scripts\setup.ps1 once, then run this script again."
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv Python. Run .\scripts\setup.ps1 once, then run this script again."
}
if (-not (Test-Path -LiteralPath $bootstrapPath)) {
    throw "Missing Master User bootstrap helper: $bootstrapPath"
}

$lines = @(Get-Content -LiteralPath $envPath)
$localToken = Get-DotEnvValue $lines "LOCAL_AGENT_TOKEN"
if ($localToken -notmatch '^[0-9a-f]{64}$') {
    throw "LOCAL_AGENT_TOKEN is missing or invalid. Run .\scripts\setup.ps1 first."
}

$clientId = Get-DotEnvValue $lines "GOOGLE_OIDC_CLIENT_ID"
$clientSecret = Get-DotEnvValue $lines "GOOGLE_OIDC_CLIENT_SECRET"
$masterSub = Get-DotEnvValue $lines "MASTER_GOOGLE_SUB"

if (-not [string]::IsNullOrWhiteSpace($clientId) -and -not [string]::IsNullOrWhiteSpace($clientSecret)) {
    $reuseClient = (Read-Host "Use the Google OAuth client already stored in .env? [Y/n]").Trim()
    if ($reuseClient -and $reuseClient -notmatch '^(?i:y|yes)
$backendPort = Get-DotEnvValue $lines "BACKEND_PORT"
if ([string]::IsNullOrWhiteSpace($backendPort)) { $backendPort = "8000" }
if ($backendPort -notmatch '^\d{1,5}$' -or [int]$backendPort -lt 1 -or [int]$backendPort -gt 65535) {
    throw "BACKEND_PORT in .env must be a valid TCP port."
}
$loginRedirect = "http://127.0.0.1:$backendPort/auth/google/callback"

if ([string]::IsNullOrWhiteSpace($clientId) -or [string]::IsNullOrWhiteSpace($clientSecret)) {
    Write-Host ""
    Write-Host "Google Cloud needs one OAuth Client ID of type Web application." -ForegroundColor Yellow
    Write-Host "The script cannot create Google credentials on your behalf."
    Write-Host "In the Google Cloud Console, configure the OAuth consent screen and add your Gmail as a test user if the app is in Testing mode."
    Write-Host "Add these exact Authorized redirect URIs:"
    Write-Host "  $loginRedirect"
    Write-Host "  $bootstrapRedirect"
    Start-Process $googleConsoleUrl
    if ([string]::IsNullOrWhiteSpace($clientId)) {
        $clientId = (Read-Host "Google OAuth Client ID").Trim()
    }
    if ([string]::IsNullOrWhiteSpace($clientSecret)) {
        $clientSecret = Read-ClientSecret
    }
}

if ($clientId -notmatch '^[A-Za-z0-9._-]+\.apps\.googleusercontent\.com$') {
    throw "Google OAuth Client ID format is invalid. Expected a Web application client ending in .apps.googleusercontent.com."
}
if ($clientSecret -notmatch '^[A-Za-z0-9._-]{8,512}$') {
    throw "Google OAuth Client Secret is empty or contains unsupported characters. Re-enter it from Google Cloud Console."
}

# Pass credentials through the child process environment. They are not written
# to .env until Google identity verification and owner confirmation pass.
$env:GOOGLE_OIDC_CLIENT_ID = $clientId
$env:GOOGLE_OIDC_CLIENT_SECRET = $clientSecret
$env:GOOGLE_OIDC_BOOTSTRAP_REDIRECT_URI = $bootstrapRedirect

Write-Host ""
Write-Host "Starting Google identity verification in your browser..."
$bootstrapOutput = @(& $python $bootstrapPath 2>&1)
$bootstrapExitCode = $LASTEXITCODE
$bootstrapText = ($bootstrapOutput | ForEach-Object { "$_" }) -join [Environment]::NewLine

if ($bootstrapExitCode -ne 0) {
    foreach ($line in $bootstrapOutput) {
        $safeLine = "$line"
        if ($safeLine -match '^(Opening Google sign-in|Waiting up to|Google identity verification failed|Master User subject was not obtained|Set GOOGLE_OIDC_CLIENT_ID)') {
            Write-Host $safeLine
        }
    }
    Write-Host "Google verification did not complete. No .env changes were saved." -ForegroundColor Red
    Write-Host "Check the OAuth consent screen, test-user list, client secret, and both redirect URIs."
    throw "Master User bootstrap failed (exit $bootstrapExitCode)."
}

$emailMatch = [regex]::Match($bootstrapText, '(?m)^Verified Google account:\s*(\S+)\s*$')
$subMatch = [regex]::Match($bootstrapText, '(?m)^Stable Google sub:\s*(\S+)\s*$')
if (-not $emailMatch.Success -or -not $subMatch.Success) {
    throw "Google identity was not returned in the expected format. No .env changes were saved."
}
$verifiedEmail = $emailMatch.Groups[1].Value
$verifiedSub = $subMatch.Groups[1].Value

Write-Host "Google verified account: $verifiedEmail" -ForegroundColor Green
if ($masterSub -and $masterSub -ne $verifiedSub) {
    Write-Host "This Google account differs from the currently configured Master User." -ForegroundColor Yellow
    $replace = (Read-Host "Replace the existing Master User with $verifiedEmail? Type YES to confirm").Trim()
    if ($replace -cne "YES") {
        throw "Master User was not changed. No .env changes were saved."
    }
}
elseif (-not $masterSub) {
    $confirm = (Read-Host "Set $verifiedEmail as the single Master User? Type YES to confirm").Trim()
    if ($confirm -cne "YES") {
        throw "Master User setup was not confirmed. No .env changes were saved."
    }
}

$sessionTtl = Get-DotEnvValue $lines "APP_SESSION_TTL_SECONDS"
if ($sessionTtl -notmatch '^\d+$' -or [int]$sessionTtl -lt 60 -or [int]$sessionTtl -gt 86400) {
    $sessionTtl = "1800"
}

$settings = @{
    GOOGLE_OIDC_CLIENT_ID = $clientId
    GOOGLE_OIDC_CLIENT_SECRET = $clientSecret
    GOOGLE_OIDC_REDIRECT_URI = $loginRedirect
    GOOGLE_OIDC_BOOTSTRAP_REDIRECT_URI = $bootstrapRedirect
    MASTER_GOOGLE_SUB = $verifiedSub
    APP_SESSION_TTL_SECONDS = $sessionTtl
    AUTHENTICATOR_SECRET_PATH = (Get-DotEnvValue $lines "AUTHENTICATOR_SECRET_PATH")
}

# Validate the complete configuration before persisting it.
$env:GOOGLE_OIDC_REDIRECT_URI = $loginRedirect
$env:MASTER_GOOGLE_SUB = $verifiedSub
$env:APP_SESSION_TTL_SECONDS = $sessionTtl
$env:AUTHENTICATOR_SECRET_PATH = $settings.AUTHENTICATOR_SECRET_PATH
$env:BACKEND_PORT = $backendPort
$env:LOCAL_AGENT_TOKEN = $localToken
$env:PYTHONPATH = Join-Path $repoRoot "src\backend"

& $python -c "from agent_backend.config import load_settings; s=load_settings(load_env_file=False); assert s.auth_enabled; print('Google OAuth configuration: valid')"
if ($LASTEXITCODE -ne 0) {
    throw "Local configuration validation failed. .env was not changed."
}

$newLines = Set-DotEnvValues $lines $settings
Write-DotEnvAtomically $envPath $newLines

$frontendPort = Get-DotEnvValue $lines "FRONTEND_PORT"
if ([string]::IsNullOrWhiteSpace($frontendPort)) { $frontendPort = "4200" }

Write-Host ""
Write-Host "Google OAuth is configured and the Master User identity was verified." -ForegroundColor Green
Write-Host "Restart the local app so the backend reloads .env:"
Write-Host "  Stop the current scripts\dev.ps1 window with Ctrl+C"
Write-Host "  .\scripts\dev.ps1"
Write-Host "Then open http://127.0.0.1:$frontendPort/ and click Login with Google."
Write-Host "No SMS, recovery codes, Proxy settings, or real Windows actions were added."
) {
        $clientId = ""
        $clientSecret = ""
    }
}
$backendPort = Get-DotEnvValue $lines "BACKEND_PORT"
if ([string]::IsNullOrWhiteSpace($backendPort)) { $backendPort = "8000" }
if ($backendPort -notmatch '^\d{1,5}$' -or [int]$backendPort -lt 1 -or [int]$backendPort -gt 65535) {
    throw "BACKEND_PORT in .env must be a valid TCP port."
}
$loginRedirect = "http://127.0.0.1:$backendPort/auth/google/callback"

if ([string]::IsNullOrWhiteSpace($clientId) -or [string]::IsNullOrWhiteSpace($clientSecret)) {
    Write-Host ""
    Write-Host "Google Cloud needs one OAuth Client ID of type Web application." -ForegroundColor Yellow
    Write-Host "The script cannot create Google credentials on your behalf."
    Write-Host "In the Google Cloud Console, configure the OAuth consent screen and add your Gmail as a test user if the app is in Testing mode."
    Write-Host "Add these exact Authorized redirect URIs:"
    Write-Host "  $loginRedirect"
    Write-Host "  $bootstrapRedirect"
    Start-Process $googleConsoleUrl
    if ([string]::IsNullOrWhiteSpace($clientId)) {
        $clientId = (Read-Host "Google OAuth Client ID").Trim()
    }
    if ([string]::IsNullOrWhiteSpace($clientSecret)) {
        $clientSecret = Read-ClientSecret
    }
}

if ($clientId -notmatch '^[A-Za-z0-9._-]+\.apps\.googleusercontent\.com$') {
    throw "Google OAuth Client ID format is invalid. Expected a Web application client ending in .apps.googleusercontent.com."
}
if ($clientSecret -notmatch '^[A-Za-z0-9._-]{8,512}$') {
    throw "Google OAuth Client Secret is empty or contains unsupported characters. Re-enter it from Google Cloud Console."
}

# Pass credentials through the child process environment. They are not written
# to .env until Google identity verification and owner confirmation pass.
$env:GOOGLE_OIDC_CLIENT_ID = $clientId
$env:GOOGLE_OIDC_CLIENT_SECRET = $clientSecret
$env:GOOGLE_OIDC_BOOTSTRAP_REDIRECT_URI = $bootstrapRedirect

Write-Host ""
Write-Host "Starting Google identity verification in your browser..."
$bootstrapOutput = @(& $python $bootstrapPath 2>&1)
$bootstrapExitCode = $LASTEXITCODE
$bootstrapText = ($bootstrapOutput | ForEach-Object { "$_" }) -join [Environment]::NewLine

if ($bootstrapExitCode -ne 0) {
    Write-Host "Google verification did not complete. No .env changes were saved." -ForegroundColor Red
    Write-Host "Check that the OAuth consent screen, test-user list, client secret, and both redirect URIs are correct."
    throw "Master User bootstrap failed (exit $bootstrapExitCode)."
}

$emailMatch = [regex]::Match($bootstrapText, '(?m)^Verified Google account:\s*(\S+)\s*$')
$subMatch = [regex]::Match($bootstrapText, '(?m)^Stable Google sub:\s*(\S+)\s*$')
if (-not $emailMatch.Success -or -not $subMatch.Success) {
    throw "Google identity was not returned in the expected format. No .env changes were saved."
}
$verifiedEmail = $emailMatch.Groups[1].Value
$verifiedSub = $subMatch.Groups[1].Value

Write-Host "Google verified account: $verifiedEmail" -ForegroundColor Green
if ($masterSub -and $masterSub -ne $verifiedSub) {
    Write-Host "This Google account differs from the currently configured Master User." -ForegroundColor Yellow
    $replace = (Read-Host "Replace the existing Master User with $verifiedEmail? Type YES to confirm").Trim()
    if ($replace -cne "YES") {
        throw "Master User was not changed. No .env changes were saved."
    }
}
elseif (-not $masterSub) {
    $confirm = (Read-Host "Set $verifiedEmail as the single Master User? Type YES to confirm").Trim()
    if ($confirm -cne "YES") {
        throw "Master User setup was not confirmed. No .env changes were saved."
    }
}

$sessionTtl = Get-DotEnvValue $lines "APP_SESSION_TTL_SECONDS"
if ($sessionTtl -notmatch '^\d+$' -or [int]$sessionTtl -lt 60 -or [int]$sessionTtl -gt 86400) {
    $sessionTtl = "1800"
}

$settings = @{
    GOOGLE_OIDC_CLIENT_ID = $clientId
    GOOGLE_OIDC_CLIENT_SECRET = $clientSecret
    GOOGLE_OIDC_REDIRECT_URI = $loginRedirect
    GOOGLE_OIDC_BOOTSTRAP_REDIRECT_URI = $bootstrapRedirect
    MASTER_GOOGLE_SUB = $verifiedSub
    APP_SESSION_TTL_SECONDS = $sessionTtl
    AUTHENTICATOR_SECRET_PATH = (Get-DotEnvValue $lines "AUTHENTICATOR_SECRET_PATH")
}

# Validate the complete configuration before persisting it.
$env:GOOGLE_OIDC_REDIRECT_URI = $loginRedirect
$env:MASTER_GOOGLE_SUB = $verifiedSub
$env:APP_SESSION_TTL_SECONDS = $sessionTtl
$env:AUTHENTICATOR_SECRET_PATH = $settings.AUTHENTICATOR_SECRET_PATH
$env:BACKEND_PORT = $backendPort
$env:LOCAL_AGENT_TOKEN = $localToken
$env:PYTHONPATH = Join-Path $repoRoot "src\backend"

& $python -c "from agent_backend.config import load_settings; s=load_settings(load_env_file=False); assert s.auth_enabled; print('Google OAuth configuration: valid')"
if ($LASTEXITCODE -ne 0) {
    throw "Local configuration validation failed. .env was not changed."
}

$newLines = Set-DotEnvValues $lines $settings
Write-DotEnvAtomically $envPath $newLines

$frontendPort = Get-DotEnvValue $lines "FRONTEND_PORT"
if ([string]::IsNullOrWhiteSpace($frontendPort)) { $frontendPort = "4200" }

Write-Host ""
Write-Host "Google OAuth is configured and the Master User identity was verified." -ForegroundColor Green
Write-Host "Restart the local app so the backend reloads .env:"
Write-Host "  Stop the current scripts\dev.ps1 window with Ctrl+C"
Write-Host "  .\scripts\dev.ps1"
Write-Host "Then open http://127.0.0.1:$frontendPort/ and click Login with Google."
Write-Host "No SMS, recovery codes, Proxy settings, or real Windows actions were added."
