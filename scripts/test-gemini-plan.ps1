<#
.SYNOPSIS
  Safely tests the local Gemini connection and Gemini-assisted plan endpoint.
.DESCRIPTION
  Read-only with respect to Windows/software. It sends one Gemini connection-test
  request and one plan-creation request. It NEVER approves a plan or invokes dry-run.
  Reads LOCAL_AGENT_TOKEN from the process environment or repository .env without
  printing it. Compatible with Windows PowerShell 5.1 and PowerShell 7+.
.PARAMETER RequestText
  Natural-language request sent to POST /api/plans.
.PARAMETER BackendUrl
  Local backend base URL.
#>
[CmdletBinding()]
param(
    [string]$RequestText = 'เตรียมเครื่องเพื่อพัฒนา Java',
    [string]$BackendUrl = 'http://127.0.0.1:8000'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repoRoot '.env'
$token = [Environment]::GetEnvironmentVariable('LOCAL_AGENT_TOKEN', 'Process')

if ([string]::IsNullOrWhiteSpace($token) -and (Test-Path -LiteralPath $envFile)) {
    $line = Get-Content -LiteralPath $envFile |
        Where-Object { $_ -match '^\s*LOCAL_AGENT_TOKEN\s*=' } |
        Select-Object -First 1
    if ($line) {
        $token = ($line -replace '^\s*LOCAL_AGENT_TOKEN\s*=', '').Trim().Trim('"').Trim("'")
    }
}

if ($token -notmatch '^[0-9a-f]{64}$') {
    throw 'LOCAL_AGENT_TOKEN is missing or invalid. Run scripts\setup.ps1 and confirm .env exists.'
}

$base = $BackendUrl.TrimEnd('/')
$headers = @{
    'x-local-agent-token' = $token
    'Origin' = 'http://127.0.0.1:4200'
}

function Invoke-LocalApi {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Path,
        [object]$Body
    )

    $uri = "$base$Path"
    try {
        $parameters = @{
            Uri = $uri
            Method = $Method
            Headers = $headers
            TimeoutSec = 30
            UseBasicParsing = $true
        }
        if ($null -ne $Body) {
            $parameters.ContentType = 'application/json; charset=utf-8'
            $parameters.Body = $Body | ConvertTo-Json -Depth 8 -Compress
        }
        $response = Invoke-WebRequest @parameters
        return [pscustomobject]@{
            StatusCode = [int]$response.StatusCode
            Body = [string]$response.Content
        }
    }
    catch {
        $statusCode = 0
        $responseBody = ''
        if ($_.Exception.Response) {
            try { $statusCode = [int]$_.Exception.Response.StatusCode } catch {}
            try {
                $stream = $_.Exception.Response.GetResponseStream()
                if ($stream) {
                    $reader = New-Object System.IO.StreamReader($stream)
                    $responseBody = $reader.ReadToEnd()
                    $reader.Dispose()
                }
            } catch {}
        }
        if ($statusCode -eq 0) {
            return [pscustomobject]@{
                StatusCode = 0
                Body = 'Cannot connect to backend. Confirm the backend is running.'
            }
        }
        return [pscustomobject]@{
            StatusCode = $statusCode
            Body = $responseBody
        }
    }
}

function Get-SafeDetail {
    param([string]$Body)
    if ([string]::IsNullOrWhiteSpace($Body)) { return '(empty response)' }
    try {
        $parsed = $Body | ConvertFrom-Json
        if ($parsed.detail -is [string]) { return $parsed.detail }
        if ($null -ne $parsed.detail) {
            return ($parsed.detail | ConvertTo-Json -Depth 5 -Compress)
        }
        return ($parsed | ConvertTo-Json -Depth 5 -Compress)
    } catch {
        return 'Response was not JSON.'
    }
}

Write-Host ''
Write-Host 'AI Agent - Gemini Plan Pipeline Test' -ForegroundColor Cyan
Write-Host "Backend: $base"
Write-Host 'Safety: no approval, no dry-run, no Windows changes.'
Write-Host ''

$health = Invoke-LocalApi -Method 'GET' -Path '/health' -Body $null
if ($health.StatusCode -ne 200) {
    Write-Host "[FAIL] Backend health: HTTP $($health.StatusCode) - $(Get-SafeDetail $health.Body)" -ForegroundColor Red
    throw 'Backend is not healthy. Start it with scripts\dev.ps1, then run this test again.'
}
Write-Host '[PASS] Backend health endpoint' -ForegroundColor Green

$status = Invoke-LocalApi -Method 'GET' -Path '/api/settings/gemini' -Body $null
if ($status.StatusCode -ne 200) {
    Write-Host "[FAIL] Gemini settings endpoint: HTTP $($status.StatusCode) - $(Get-SafeDetail $status.Body)" -ForegroundColor Red
    throw 'Could not read Gemini settings status.'
}
$statusObject = $status.Body | ConvertFrom-Json
if (-not $statusObject.configured) {
    Write-Host '[FAIL] Gemini API key is not configured in this backend process.' -ForegroundColor Red
    throw 'Configure the Gemini key in the app, then run this script again.'
}
Write-Host "[PASS] Gemini configured (model: $($statusObject.model))" -ForegroundColor Green

$connection = Invoke-LocalApi -Method 'POST' -Path '/api/settings/gemini/test' -Body @{}
if ($connection.StatusCode -eq 200) {
    Write-Host '[PASS] Gemini connection test' -ForegroundColor Green
} else {
    Write-Host "[FAIL] Gemini connection test: HTTP $($connection.StatusCode) - $(Get-SafeDetail $connection.Body)" -ForegroundColor Red
}

$plan = Invoke-LocalApi -Method 'POST' -Path '/api/plans' -Body @{
    request = $RequestText
    language = 'th'
}

if ($plan.StatusCode -eq 200) {
    try {
        $planObject = $plan.Body | ConvertFrom-Json
        if ($planObject.approved -eq $false -and $null -eq $planObject.tool_result) {
            Write-Host '[PASS] Gemini plan created; no approval or tool execution occurred.' -ForegroundColor Green
            if ($planObject.questions) {
                Write-Host 'Clarification questions:'
                foreach ($question in $planObject.questions) { Write-Host " - $question" }
            }
            if ($planObject.dry_run_plan) {
                Write-Host "Plan ID: $($planObject.dry_run_plan.plan_id)"
                Write-Host "Plan mode: $($planObject.dry_run_plan.mode)"
            }
        } else {
            Write-Host '[WARN] API returned 200 but response did not match the expected unapproved plan shape.' -ForegroundColor Yellow
            Write-Host (Get-SafeDetail $plan.Body)
        }
    } catch {
        Write-Host '[FAIL] Plan endpoint returned invalid JSON.' -ForegroundColor Red
    }
} else {
    $detail = Get-SafeDetail $plan.Body
    Write-Host "[FAIL] POST /api/plans: HTTP $($plan.StatusCode) - $detail" -ForegroundColor Red
    if ($plan.StatusCode -eq 502 -and $detail -match 'Internal server error') {
        Write-Host 'Hint: update to the branch/PR that includes safe plan-error diagnostics, then rerun.' -ForegroundColor Yellow
    }
    if ($plan.StatusCode -eq 404) {
        Write-Host 'Hint: verify that this backend build includes the /api/plans router.' -ForegroundColor Yellow
    }
}

Write-Host ''
if ($connection.StatusCode -eq 200 -and $plan.StatusCode -eq 200) {
    Write-Host 'RESULT: Gemini connection and plan creation both passed.' -ForegroundColor Green
    exit 0
}
Write-Host 'RESULT: One or more checks failed. Send the complete output above; it contains sanitized status details only.' -ForegroundColor Yellow
exit 1
