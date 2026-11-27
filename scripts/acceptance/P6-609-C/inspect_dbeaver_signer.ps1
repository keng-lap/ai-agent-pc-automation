$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$releaseApi = 'https://api.github.com/repos/dbeaver/dbeaver/releases/latest'
$headers = @{
    Accept = 'application/vnd.github+json'
    'X-GitHub-Api-Version' = '2022-11-28'
    'User-Agent' = 'ai-agent-pc-automation-publisher-inspection/1.0'
}

$tempRoot = Join-Path $env:TEMP ('aiagent-dbeaver-signer-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null

try {
    Write-Host 'Reading the latest DBeaver Community release metadata from the official GitHub repository...'
    $release = Invoke-RestMethod -Uri $releaseApi -Headers $headers -Method Get
    $version = [string]$release.tag_name
    if ($version -notmatch '^[A-Za-z0-9][A-Za-z0-9._+!-]{0,79}$') {
        throw 'Official release tag was missing or malformed.'
    }

    $assetName = "dbeaver-ce-$version-windows-x86_64.exe"
    $matches = @($release.assets | Where-Object { $_.name -ceq $assetName })
    if ($matches.Count -ne 1) {
        throw "Expected exactly one official release asset named $assetName."
    }

    $asset = $matches[0]
    $assetUrl = [string]$asset.browser_download_url
    if ($assetUrl -cne "https://github.com/dbeaver/dbeaver/releases/download/$version/$assetName") {
        throw 'Official release asset URL did not match the expected DBeaver GitHub release path.'
    }
    $assetId = [long]$asset.id
    if ($assetId -lt 1) {
        throw 'Official release metadata did not provide a valid asset ID.'
    }
    $assetApiUrl = "https://api.github.com/repos/dbeaver/dbeaver/releases/assets/$assetId"

    $officialDigest = [string]$asset.digest
    if ($officialDigest -notmatch '^sha256:([0-9a-fA-F]{64})$') {
        throw 'GitHub release metadata did not provide a SHA-256 asset digest. Refusing to continue.'
    }
    $expectedHash = $Matches[1].ToLowerInvariant()

    $installerPath = Join-Path $tempRoot $assetName
    Write-Host "Downloading official installer for inspection only: $version"
    Invoke-WebRequest -Uri $assetApiUrl -Headers @{
        Accept = 'application/octet-stream'
        'X-GitHub-Api-Version' = '2022-11-28'
        'User-Agent' = $headers['User-Agent']
    } -OutFile $installerPath -UseBasicParsing

    $actualHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -cne $expectedHash) {
        throw 'Downloaded installer SHA-256 did not match the official GitHub release digest.'
    }

    $signature = Get-AuthenticodeSignature -FilePath $installerPath
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
        throw "Authenticode verification failed: $($signature.Status) $($signature.StatusMessage)"
    }
    $certificate = $signature.SignerCertificate
    if ($null -eq $certificate -or $certificate.Subject -notmatch '(?i)dbeaver') {
        throw 'The trusted Authenticode signer certificate did not identify DBeaver in its subject.'
    }

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $fingerprint = ([BitConverter]::ToString($sha.ComputeHash($certificate.RawData))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }

    [pscustomobject]@{
        Result = 'PASS_AUTHENTICODE_INSPECTION'
        Product = 'DBeaver Community'
        Version = $version
        OfficialAsset = $assetName
        OfficialAssetSha256 = $expectedHash
        DownloadedAssetSha256 = $actualHash
        SignatureStatus = [string]$signature.Status
        SignerSubject = $certificate.Subject
        SignerIssuer = $certificate.Issuer
        SignerNotBefore = $certificate.NotBefore.ToUniversalTime().ToString('o')
        SignerNotAfter = $certificate.NotAfter.ToUniversalTime().ToString('o')
        SignerCertificateSha256 = $fingerprint
    } | Format-List

    Write-Host ''
    Write-Host 'This command does NOT install or execute DBeaver.'
    Write-Host 'The certificate fingerprint is evidence for review only; no environment variable or per-package pin is required.'
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
