param(
    [Parameter(Mandatory = $true)][string]$CertificateThumbprint,
    [string]$ExecutablePath = "dist\AgentBackend.exe"
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$thumbprint = ($CertificateThumbprint -replace "\s", "").ToUpperInvariant()
if ($thumbprint -notmatch "^[0-9A-F]{40,64}$") { throw "Certificate thumbprint must be a SHA-1 or SHA-256 hex thumbprint." }
$certificate = Get-Item -LiteralPath "Cert:\CurrentUser\My\$thumbprint" -ErrorAction Stop
if (-not $certificate.HasPrivateKey) { throw "The selected code-signing certificate has no private key in the current-user certificate store." }
$now = Get-Date
if ($now -lt $certificate.NotBefore -or $now -gt $certificate.NotAfter) { throw "The selected code-signing certificate is outside its validity period." }
$eku = @($certificate.Extensions | Where-Object { $_.Oid.Value -eq "2.5.29.37" } | ForEach-Object { $_.EnhancedKeyUsages } | ForEach-Object { $_.Value })
if ($eku -notcontains "1.3.6.1.5.5.7.3.3") { throw "The selected certificate does not contain the Code Signing EKU." }
$exe = (Resolve-Path -LiteralPath $ExecutablePath -ErrorAction Stop).Path
$kitsRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
$signTool = Get-ChildItem -LiteralPath $kitsRoot -Filter signtool.exe -Recurse -ErrorAction Stop | Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } | Sort-Object FullName -Descending | Select-Object -First 1
if (-not $signTool) { throw "Windows SDK SignTool (x64) was not found." }
& $signTool.FullName sign /fd SHA256 /sha1 $thumbprint $exe
if ($LASTEXITCODE -ne 0) { throw "Authenticode signing failed." }
$signature = Get-AuthenticodeSignature -LiteralPath $exe
if (-not $signature.SignerCertificate -or $signature.SignerCertificate.Thumbprint -ne $certificate.Thumbprint) { throw "Signed executable signer does not match the selected certificate." }
$sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
$certSha256 = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($certificate.RawData))
Write-Host "Signed executable: $exe"
Write-Host "File SHA-256: $sha256"
Write-Host "Pinned certificate SHA-256: $certSha256"
Write-Host "Authenticode status: $($signature.Status) ($($signature.StatusMessage))"
if ($signature.Status -ne "Valid") { Write-Warning "The signature is present and signer-pinned, but Windows does not currently report it as trusted. Do not provision until the administrator has explicitly enrolled the certificate into the required trust stores and verification reports Valid." }
Write-Warning "This script signs only the supplied Backend executable. It does not enroll trust, export private keys, provision policy, or enable Machine Scope."
