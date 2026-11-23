param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._+-]{0,159}$')]
    [string]$PackageId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._+!-]{0,79}$')]
    [string]$Version,

    [ValidateRange(1, 15)]
    [int]$ExpiresInMinutes = 10
)

$ErrorActionPreference = 'Stop'

# This authorization is deliberately scoped to this PowerShell process.
# It is one-use, bound to one package/version, and expires within 15 minutes.
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $rng.GetBytes($bytes)
}
finally {
    $rng.Dispose()
}
$nonce = -join ($bytes | ForEach-Object { $_.ToString('x2') })
$expiresAt = [DateTime]::UtcNow.AddMinutes($ExpiresInMinutes).ToString('o')

$env:AI_AGENT_ENABLE_REAL_INSTALL = '1'
$env:AI_AGENT_REAL_INSTALL_RELEASE_TASK = 'P6-609-C'
$env:AI_AGENT_REAL_INSTALL_PACKAGE_ID = $PackageId
$env:AI_AGENT_REAL_INSTALL_VERSION = $Version
$env:AI_AGENT_REAL_INSTALL_EXPIRES_AT = $expiresAt
$env:AI_AGENT_REAL_INSTALL_NONCE = $nonce

Write-Host 'Real-install release authorization prepared for this PowerShell process.'
Write-Host "Task: P6-609-C"
Write-Host "Exact package: $PackageId"
Write-Host "Exact version: $Version"
Write-Host "Expires (UTC): $expiresAt"
Write-Host 'Start/restart the backend from this same PowerShell window before approving the matching install.'
Write-Host 'The release nonce is consumed once in the protected local SQLite store; it cannot authorize a second install.'
